import asyncio
import logging
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.models import DocumentUploadResponse
from app.security import harden_upload, require_api_key
from app.services.document_parser import parse_upload
from app.services.local_index import local_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])
MAX_FILE_SIZE = 75 * 1024 * 1024

# In-memory job tracker {document_id -> status_dict}
_upload_jobs: dict[str, dict] = {}
# Original uploaded bytes are kept only in memory so the user can reindex with Vision/OCR
# during the same backend session. API keys and .env are not changed by this flow.
_document_blobs: dict[str, tuple[str, bytes]] = {}


async def _process_document_background(filename: str, content: bytes, document_id: str) -> None:
    """Process document in background - parse all artifacts and update index."""
    try:
        from fastapi import UploadFile
        import io
        # Create a minimal file-like object for the parser
        fake_file = UploadFile(filename=filename, file=io.BytesIO(content))
        artifacts = await parse_upload(fake_file)
        local_index.add_artifacts(filename, artifacts, document_id=document_id)
        counts = Counter(a.artifact_type for a in artifacts)
        _upload_jobs[document_id] = {
            "status": "ready",
            "artifacts": len(artifacts),
            "tables": counts.get("table", 0),
            "figures": counts.get("figure", 0),
            "maps": counts.get("map", 0),
            "message": f"Готово: {len(artifacts)} артефактов из «{filename}».",
        }
        logger.info("Background parse done: %s → %d artifacts", filename, len(artifacts))
    except Exception as exc:
        logger.exception("Background parse failed for %s", filename)
        _upload_jobs[document_id] = {
            "status": "error",
            "message": f"Ошибка обработки: {type(exc).__name__}: {exc}",
        }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    filename = await harden_upload(file, MAX_FILE_SIZE)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Файл пустой.")

    from pathlib import Path
    suffix = Path(filename).suffix.lower()

    # For small/fast files (Excel, CSV, DOCX, images) — process synchronously
    fast_formats = {".xlsx", ".xls", ".csv", ".docx", ".txt", ".md",
                    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    if suffix in fast_formats:
        try:
            import io as _io
            from fastapi import UploadFile as _UF
            fake = _UF(filename=filename, file=_io.BytesIO(content))
            artifacts = await parse_upload(fake)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Ошибка при обработке '%s'", filename)
            raise HTTPException(status_code=500, detail=f"Ошибка: {type(exc).__name__}") from exc

        document_id = local_index.add_artifacts(filename, artifacts)
        _document_blobs[document_id] = (filename, content)
        counts = Counter(a.artifact_type for a in artifacts)
        return DocumentUploadResponse(
            document_id=document_id,
            filename=filename,
            status="indexed",
            message=(
                f"Готово: {len(artifacts)} артефактов из «{filename}». "
                f"Таблиц: {counts.get('table', 0)}, рисунков: {counts.get('figure', 0)}."
            ),
            artifacts=len(artifacts),
            tables=counts.get("table", 0),
            figures=counts.get("figure", 0),
            maps=counts.get("map", 0),
        )

    # For large PDFs — register immediately + parse in background
    import uuid
    document_id = str(uuid.uuid4())
    _upload_jobs[document_id] = {"status": "processing", "message": f"Обрабатывается «{filename}»…"}
    _document_blobs[document_id] = (filename, content)
    # Register placeholder so the document appears in the list immediately
    local_index.add_placeholder(filename, document_id)
    background_tasks.add_task(_process_document_background, filename, content, document_id)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status="processing",
        message=f"«{filename}» принят в обработку. Обновите список через несколько секунд.",
        artifacts=0,
        tables=0,
        figures=0,
        maps=0,
    )


@router.get("/status/{document_id}")
async def document_status(document_id: str) -> dict:
    """Poll processing status for async uploads."""
    job = _upload_jobs.get(document_id)
    if not job:
        # Already completed and cleaned up, or not found
        doc = local_index.get_document_info(document_id)
        if doc:
            return {"status": "ready", **doc}
        raise HTTPException(status_code=404, detail="Документ не найден")
    return {"document_id": document_id, **job}


@router.get("/list")
async def list_documents() -> dict[str, list[dict]]:
    docs = local_index.list_documents()
    # Enrich with processing status
    for doc in docs:
        job = _upload_jobs.get(doc.get("id", ""))
        if job and job.get("status") == "processing":
            doc["processing"] = True
    return {"documents": docs}


@router.post("/{document_id}/reindex", response_model=DocumentUploadResponse)
async def reindex_document(background_tasks: BackgroundTasks, document_id: str) -> DocumentUploadResponse:
    stored = _document_blobs.get(document_id)
    if not stored:
        raise HTTPException(
            status_code=404,
            detail="Исходный файл для переиндексации не найден. Загрузите документ заново и включите Vision/OCR.",
        )

    filename, content = stored
    local_index.remove_document(document_id)
    local_index.add_placeholder(filename, document_id)
    _upload_jobs[document_id] = {
        "status": "processing",
        "message": f"Переиндексация «{filename}» с Vision/OCR запущена…",
    }
    background_tasks.add_task(_process_document_background, filename, content, document_id)
    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        status="processing",
        message=f"Переиндексация «{filename}» с Vision/OCR запущена. Через несколько секунд задайте вопрос ещё раз.",
        artifacts=0,
        tables=0,
        figures=0,
        maps=0,
    )


@router.delete("/{document_id}")
async def delete_document(document_id: str) -> dict[str, str]:
    _upload_jobs.pop(document_id, None)
    _document_blobs.pop(document_id, None)
    removed = local_index.remove_document(document_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return {"status": "deleted", "document_id": document_id}

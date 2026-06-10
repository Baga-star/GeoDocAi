import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque

from fastapi import Depends, Header, HTTPException, Request, UploadFile

from app.config import Settings, get_settings

ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls",
    ".csv", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp",
}

_IMAGE_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".webp": (b"RIFF",),
}

_RATE_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)


def api_key_is_enabled(settings: Settings) -> bool:
    return bool(settings.api_key and settings.api_key != "replace-me")


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Optional API-key guard.

    Local demo remains frictionless when GEODOC_API_KEY/API_KEY is unset. In any
    shared/staging deployment, setting the key immediately protects upload,
    list and chat endpoints with either `Authorization: Bearer ...` or
    `X-API-Key: ...`.
    """
    if not api_key_is_enabled(settings):
        return

    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    provided = x_api_key or bearer
    if provided != settings.api_key:
        raise HTTPException(status_code=401, detail="Требуется корректный API key.")


async def rate_limit(request: Request, settings: Settings) -> None:
    """Small in-memory quota guard for demo/staging.

    It is intentionally simple and should be replaced with Redis/API gateway
    limits for multi-process production deployments.
    """
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    client = forwarded or (request.client.host if request.client else "unknown")
    key = f"{client}:{request.url.path}"
    now = time.monotonic()
    bucket = _RATE_BUCKETS[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Слишком много запросов. Повторите позже.")
    bucket.append(now)


def safe_filename(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "").strip()
    allowed = []
    for ch in name:
        if ch.isalnum() or ch in {".", "-", "_", " ", "(", ")"}:
            allowed.append(ch)
        else:
            allowed.append("_")
    cleaned = "".join(allowed).strip(" .")
    return cleaned[:180] or "document"


def validate_upload_bytes(filename: str, content: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Формат «{suffix or 'без расширения'}» не поддерживается. "
                "Поддерживаются PDF, DOCX, Excel, CSV, TXT/MD и изображения."
            ),
        )
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой или не удалось прочитать содержимое.")

    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="Файл имеет расширение PDF, но не похож на настоящий PDF.")

    if suffix in {".docx", ".xlsx"} and not content.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=422, detail="Файл Office должен быть валидным ZIP/OOXML-документом.")

    if suffix == ".xls" and not (content.startswith(b"\xd0\xcf\x11\xe0") or content.startswith(b"PK\x03\x04")):
        raise HTTPException(status_code=422, detail="Файл XLS не похож на валидный Excel-документ.")

    if suffix in _IMAGE_MAGIC:
        markers = _IMAGE_MAGIC[suffix]
        if suffix == ".webp":
            ok = content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        else:
            ok = any(content.startswith(marker) for marker in markers)
        if not ok:
            raise HTTPException(status_code=422, detail="Файл изображения не совпадает с заявленным форматом.")


async def harden_upload(file: UploadFile, max_file_size: int) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Имя файла не указано.")
    filename = safe_filename(file.filename)
    content = await file.read(max_file_size + 1)
    if len(content) > max_file_size:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой (макс. {max_file_size // (1024 * 1024)} МБ).")
    validate_upload_bytes(filename, content[:8192] if len(content) > 8192 else content)
    # Reset for the parser, which reads UploadFile itself.
    await file.seek(0)
    file.filename = filename
    return filename

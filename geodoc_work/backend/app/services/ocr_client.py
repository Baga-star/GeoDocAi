"""DeepSeek OCR client through an OpenAI-compatible chat-completions endpoint."""
import base64
import json

import httpx

from app.prompts.geology import OCR_STRUCTURING_PROMPT

OCR_TEXT_PROMPT = (
    "Извлеки весь текст с этой странице геологического документа. "
    "Сохрани структуру таблиц, заголовки, числа с единицами измерения, "
    "номера скважин, названия пластов и горизонтов. Верни только извлечённый текст."
)


def _data_url(image_bytes: bytes, mime_type: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


async def ocr_image_bytes(
    image_bytes: bytes,
    api_key: str,
    api_url: str,
    model: str = "deepseek-ocr",
    mime_type: str = "image/png",
    structured: bool = True,
) -> str:
    """Send a single image to OCR and return either structured JSON or plain text."""
    prompt = OCR_STRUCTURING_PROMPT if structured else OCR_TEXT_PROMPT
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(image_bytes, mime_type)}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"]


async def ocr_pdf_bytes(
    pdf_bytes: bytes,
    api_key: str,
    api_url: str,
    model: str = "deepseek-ocr",
    max_pages: int = 30,
    structured: bool = True,
) -> str:
    """Render PDF pages and OCR them. Structured mode returns a JSON array string."""
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("Для OCR PDF установите pymupdf") from exc

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total = min(len(doc), max_pages)
        # Pre-render all pages (CPU-bound) before firing async OCR calls.
        rendered: list[tuple[int, bytes]] = []
        for page_num in range(total):
            page = doc[page_num]
            mat = fitz.Matrix(180 / 72, 180 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            rendered.append((page_num, pix.tobytes("png")))
    finally:
        doc.close()

    # WHY: OCR calls were sequential — N pages × ~10s = minutes.
    # asyncio.gather sends all pages to the OCR endpoint concurrently.
    import asyncio as _asyncio

    async def _ocr_one(page_num: int, png_bytes: bytes) -> str | None:
        text = await ocr_image_bytes(
            png_bytes,
            api_key=api_key,
            api_url=api_url,
            model=model,
            mime_type="image/png",
            structured=structured,
        )
        if not text.strip():
            return None
        if structured:
            return _force_page_number(text, page_num + 1)
        return f"[Страница {page_num + 1}]\n{text.strip()}"

    raw_outputs = await _asyncio.gather(*[_ocr_one(pn, pb) for pn, pb in rendered])
    outputs: list[str] = [o for o in raw_outputs if o is not None]

    if not structured:
        return "\n\n".join(outputs)
    # If OCR returned JSON per page, expose a single JSON array to the parser.
    items = []
    for output in outputs:
        try:
            parsed = json.loads(_strip_code_fence(output))
            if isinstance(parsed, list):
                items.extend(parsed)
            else:
                items.append(parsed)
        except Exception:
            items.append({"page": None, "texts": [{"title": None, "text": output}], "tables": [], "figures": [], "maps": []})
    return json.dumps(items, ensure_ascii=False)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _force_page_number(text: str, page: int) -> str:
    try:
        parsed = json.loads(_strip_code_fence(text))
        if isinstance(parsed, dict):
            parsed["page"] = parsed.get("page") or page
            return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        pass
    return text

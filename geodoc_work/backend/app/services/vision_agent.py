"""Vision agent for geological figures, maps and scanned PDF pages.

This module converts visual content into searchable, evidence-first artifacts.
It deliberately returns structured JSON instead of prose so the RAG answer agent
can cite map/figure observations without inventing details.

Strategy for maximising deepseek-ocr quality without external APIs:
1. High-DPI render (220 dpi, configured in Settings).
2. Pre-processing: contrast enhancement + sharpening via Pillow.
3. Chain-of-Thought prompt (VISUAL_GEOLOGY_ANALYSIS_PROMPT) that forces
   the model to analyse the image in 9 explicit steps.
4. Multi-crop second pass: for map artifacts, crop legend / title / well-cluster
   regions and analyse them separately with VISUAL_REGION_ANALYSIS_PROMPT,
   then merge the richer text back into the primary payload.
5. Payload merging: structured crops fill gaps left by the full-image pass.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings
from app.prompts.geology import VISUAL_GEOLOGY_ANALYSIS_PROMPT, VISUAL_REGION_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


# ── Image helpers ─────────────────────────────────────────────────────────────

def image_data_url(image_bytes: bytes, mime_type: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def _enhance_for_ocr(image_bytes: bytes) -> bytes:
    """Apply contrast/sharpness enhancement so deepseek-ocr reads small labels better.

    Uses only Pillow (already a project dependency). Returns original bytes on
    any failure so the caller can always continue.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # 1. Slightly increase contrast — helps isolines and thin labels.
        img = ImageEnhance.Contrast(img).enhance(1.25)
        # 2. Mild sharpening — improves edge legibility without introducing
        #    artefacts that confuse the vision model.
        img = ImageEnhance.Sharpness(img).enhance(1.4)
        # 3. Unsharp-mask for fine lines (contours, well markers).
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=80, threshold=3))

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=False)
        return out.getvalue()
    except Exception as exc:
        logger.debug("Image enhancement failed (non-fatal): %s", exc)
        return image_bytes


def _crop_region(image_bytes: bytes, box_frac: tuple[float, float, float, float]) -> bytes:
    """Crop a fraction-based bounding box (left, top, right, bottom) from the image."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        left, top, right, bottom = box_frac
        box = (int(left * w), int(top * h), int(right * w), int(bottom * h))
        cropped = img.crop(box)
        # Scale up small crops so the model has enough pixels to read text.
        cw, ch = cropped.size
        if cw < 400 or ch < 300:
            scale = max(400 / max(cw, 1), 300 / max(ch, 1), 1.5)
            cropped = cropped.resize((int(cw * scale), int(ch * scale)), resample=3)
        out = io.BytesIO()
        cropped.save(out, format="PNG", optimize=False)
        return out.getvalue()
    except Exception as exc:
        logger.debug("Crop failed (non-fatal): %s", exc)
        return image_bytes


# ── Credential / config helpers ───────────────────────────────────────────────

def vision_credentials(settings: Settings) -> tuple[str | None, str, str]:
    """Return api_key, chat_url, model for an OpenAI-compatible vision model."""
    candidates = [settings.vision_api_key, settings.deepseek_ocr_api_key, settings.qwen_api_key]
    api_key = next((key for key in candidates if key and key != "replace-me"), None)
    base_url = str(settings.vision_base_url or settings.qwen_base_url).rstrip("/")
    chat_url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    return api_key, chat_url, settings.vision_model


def vision_is_configured(settings: Settings) -> bool:
    api_key, _, _ = vision_credentials(settings)
    return bool(settings.enable_visual_analysis and api_key)


# ── Core vision call ──────────────────────────────────────────────────────────

async def _call_vision(
    image_bytes: bytes,
    prompt: str,
    *,
    api_key: str,
    chat_url: str,
    model: str,
    timeout: int = 120,
) -> str:
    """Send one image+prompt to the OpenAI-compatible endpoint and return raw text."""
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url(image_bytes)}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(chat_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"]


# ── Multi-crop second pass ─────────────────────────────────────────────────────

# Region definitions: (name, box_frac, region_type_label)
# box_frac = (left, top, right, bottom) as fractions of image size
_MAP_REGIONS = [
    ("title_area",    (0.0,  0.0,  1.0,  0.12), "title_area"),
    ("legend_right",  (0.75, 0.05, 1.0,  0.95), "legend_area"),
    ("legend_bottom", (0.0,  0.85, 1.0,  1.0),  "legend_area"),
    ("center_map",    (0.1,  0.1,  0.9,  0.85), "contour_zone"),
    ("left_edge",     (0.0,  0.05, 0.08, 0.95), "coordinate_edge"),
    ("bottom_edge",   (0.05, 0.88, 0.95, 1.0),  "coordinate_edge"),
]

_FIGURE_REGIONS = [
    ("title_area",    (0.0,  0.0,  1.0,  0.12), "title_area"),
    ("caption_bottom",(0.0,  0.88, 1.0,  1.0),  "title_area"),
    ("main_body",     (0.05, 0.1,  0.95, 0.88), "contour_zone"),
]


async def _run_region_passes(
    image_bytes: bytes,
    artifact_type: str,
    *,
    api_key: str,
    chat_url: str,
    model: str,
) -> list[dict[str, Any]]:
    """Run focused crop analyses in parallel and return list of region payloads.

    WHY: previously ran sequentially — 6 crops x ~5s each = ~30s per page.
    asyncio.gather fires all crops concurrently, cutting per-page crop time
    to ~5-6s regardless of crop count (bounded by slowest single call).
    """
    regions = _MAP_REGIONS if artifact_type == "map" else _FIGURE_REGIONS

    async def _one_crop(
        name: str,
        box_frac: tuple[float, float, float, float],
        region_type: str,
    ) -> "dict[str, Any] | None":
        try:
            crop_bytes = _crop_region(image_bytes, box_frac)
            enhanced = _enhance_for_ocr(crop_bytes)
            prompt = VISUAL_REGION_ANALYSIS_PROMPT.replace("{region_type}", region_type)
            raw = await _call_vision(
                enhanced, prompt,
                api_key=api_key, chat_url=chat_url, model=model, timeout=60,
            )
            parsed = _parse_json_object(raw)
            if parsed and parsed.get("extracted"):
                parsed["_region_name"] = name
                return parsed
        except Exception as exc:
            logger.debug("Region crop '%s' failed (non-fatal): %s", name, exc)
        return None

    raw_results = await asyncio.gather(
        *[_one_crop(n, b, t) for n, b, t in regions]
    )
    return [r for r in raw_results if r is not None]


def _merge_region_crops(primary: dict[str, Any], crops: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge crop results into the primary payload, filling empty fields."""
    if not crops:
        return primary
    merged = dict(primary)

    # Collect all extracted text from all crops
    extra_text: list[str] = []
    for crop in crops:
        for item in crop.get("extracted") or []:
            s = str(item).strip()
            if s and len(s) > 1:
                extra_text.append(s)

    # Merge into visible_text
    existing = set(str(x) for x in (merged.get("visible_text") or []))
    new_visible = list(merged.get("visible_text") or [])
    for t in extra_text:
        if t not in existing:
            new_visible.append(t)
            existing.add(t)
    if new_visible:
        merged["visible_text"] = new_visible

    # Extract title from title_area crops if primary has none
    if not merged.get("title"):
        for crop in crops:
            if crop.get("_region_name") in ("title_area", "caption_bottom"):
                extracted = crop.get("extracted") or []
                for line in extracted:
                    s = str(line).strip()
                    # Look for typical geological figure patterns
                    if re.search(r"(рис\.|рисунок|карта|figure|fig\.)\s*\d", s, re.I):
                        merged["title"] = s
                        break
                if merged.get("title"):
                    break

    # Extract coordinates from edge crops
    coord_text: list[str] = []
    for crop in crops:
        if crop.get("_region_name") in ("left_edge", "bottom_edge"):
            for item in crop.get("extracted") or []:
                s = str(item).strip()
                # Coordinate patterns: large numbers, degree symbols
                if re.search(r"\d{4,}", s) or "°" in s or re.search(r"\d+[.,]\d+", s):
                    coord_text.append(s)
    if coord_text:
        existing_coords = set(str(x) for x in (merged.get("coordinates") or []))
        new_coords = list(merged.get("coordinates") or [])
        for c in coord_text:
            if c not in existing_coords:
                new_coords.append(c)
                existing_coords.add(c)
        merged["coordinates"] = new_coords

    # Extract well IDs from legend crops
    well_text: list[str] = []
    for crop in crops:
        if "legend" in (crop.get("_region_name") or ""):
            for item in crop.get("extracted") or []:
                s = str(item).strip()
                # Well numbers are typically short digit strings
                if re.search(r"^\d{1,4}$", s) or re.search(r"скв\w*[\s.]\d+", s, re.I):
                    well_text.append(s)

    # Merge legend elements if primary legend is empty
    if not merged.get("legend"):
        for crop in crops:
            if "legend" in (crop.get("_region_name") or ""):
                structured = crop.get("structured") or {}
                if structured:
                    merged["legend"] = [{"label": k, "symbol": "", "meaning": v} for k, v in structured.items()]
                    break

    return merged


# ── Main public API ───────────────────────────────────────────────────────────

async def analyze_geology_image(
    image_bytes: bytes,
    *,
    settings: Settings,
    filename: str,
    page: int | None = None,
    mime_type: str = "image/png",
) -> dict[str, Any] | None:
    """Analyze a map/figure image and return structured visual reading JSON.

    Pipeline:
    1. Enhance image (contrast + sharpening).
    2. Full-image pass with Chain-of-Thought prompt.
    3. If map/figure → multi-crop second pass on key regions.
    4. Merge crop findings into primary payload.

    Returns None when vision is not configured.
    Raises on network errors so the caller can fall back to visual-placeholder.
    """
    if not settings.enable_visual_analysis:
        return None
    api_key, chat_url, model = vision_credentials(settings)
    if not api_key:
        return None

    context = f"Файл: {filename}." + (f" Страница: {page}." if page else "")
    enhanced = _enhance_for_ocr(image_bytes)

    # ── Pass 1: full image with CoT prompt ────────────────────────────────────
    full_prompt = f"{VISUAL_GEOLOGY_ANALYSIS_PROMPT}\n\nКонтекст: {context}"
    raw = await _call_vision(enhanced, full_prompt, api_key=api_key, chat_url=chat_url, model=model, timeout=150)
    primary = _parse_json_object(raw)
    if primary is None:
        logger.warning("Vision model returned non-JSON for %s page %s; using raw text", filename, page)
        primary = {"visual_type": "figure", "title": None, "summary": str(raw).strip(), "raw_response": str(raw)}

    # ── Pass 2: regional crop passes for map/figure ───────────────────────────
    artifact_type = visual_payload_type(primary, fallback="figure")
    if artifact_type in ("map", "figure"):
        try:
            crops = await _run_region_passes(
                enhanced, artifact_type,
                api_key=api_key, chat_url=chat_url, model=model,
            )
            if crops:
                primary = _merge_region_crops(primary, crops)
                primary["_region_passes"] = len(crops)
        except Exception as exc:
            logger.warning("Multi-crop pass failed (non-fatal): %s", exc)

    return primary


# ── Payload utilities ─────────────────────────────────────────────────────────

def visual_payload_to_text(payload: dict[str, Any]) -> str:
    """Flatten structured visual reading into searchable text."""
    parts: list[str] = []
    for key in ("title", "caption", "summary", "scale"):
        value = payload.get(key)
        if value:
            parts.append(str(value))

    for label, key in (
        ("Текст на изображении", "visible_text"),
        ("Легенда", "legend"),
        ("Скважины", "wells"),
        ("Контуры и изолинии", "contours"),
        ("Координаты", "coordinates"),
        ("Горизонты/пласты", "horizons"),
        ("Категории/зоны", "categories"),
        ("Геологические наблюдения", "observations"),
        ("Ограничения чтения", "limitations"),
    ):
        value = payload.get(key)
        if value:
            parts.append(f"{label}: {_stringify(value)}")
    return "\n".join(p for p in parts if p).strip()


def visual_payload_type(payload: dict[str, Any], fallback: str = "figure") -> str:
    """Classify visual artifact type with geology-specific safeguards."""
    raw = str(payload.get("visual_type") or "").lower()
    hay = _payload_text(payload).lower().replace("ё", "е")

    explicit_map = any(token in raw for token in ("map", "карта", "plan", "gis", "contour"))
    explicit_figure = any(token in raw for token in ("section", "разрез", "figure", "схема", "diagram", "plot"))

    map_score = 0
    map_terms = (
        "карта", "структурная", "контур", "изолини", "внк", "гнк", "гвк",
        "кровл", "подошв", "план", "скважин", "добывающ", "нагнетатель",
        "категор", "координат", "масштаб", "c1", "c2", "c3", "с1", "с2", "с3",
        "изогипс", "изопахит", "горизонт п", "пласт ю", "пласт д",
    )
    for token in map_terms:
        if token in hay:
            map_score += 1

    # Structured fields are even stronger than free text.
    for key in ("legend", "wells", "contours", "coordinates", "categories"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            map_score += 2

    if explicit_map or map_score >= 3:
        return "map"
    if fallback == "map" and not explicit_figure:
        return "map"
    if explicit_figure:
        return "figure"
    if str(payload.get("visual_type") or "").lower() == "table":
        return "table"
    return fallback if fallback in {"map", "figure", "table", "text"} else "figure"


def _bad_generated_title(text: str) -> bool:
    low = text.lower().replace("ё", "е")
    bad_markers = (
        "визуальным признакам",
        "даже если vision",
        "vision-модель",
        "local mapreader",
        "страница определена как карта",
        "желтая заливка",
        "зеленая заливка",
        "образует основную",
        "площадную зону",
        "видны синие",
        "видны красные",
        "похожие на",
    )
    if any(marker in low for marker in bad_markers):
        return True
    if len(low) > 85 and not any(token in low for token in ("рисунок", "рис.", "карта", "структурная карта")):
        return True
    if low.startswith("карта:") and not any(token in low for token in ("структурная", "кровл", "подошв", "месторожд", "рисунок")):
        return True
    return False


def visual_payload_title(payload: dict[str, Any], artifact_type: str, filename: str, page: int | None) -> str:
    """Infer a useful title from vision JSON even when title/caption is weak."""
    for key in ("title", "caption"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and value.strip().lower() not in {"null", "none"}:
            cleaned = re.sub(r"\s+", " ", value).strip(" -—:;,. ")
            if not _bad_generated_title(cleaned):
                return cleaned

    hay_items: list[str] = []
    for value in payload.get("visible_text") or []:
        if isinstance(value, str):
            hay_items.append(value)
        elif isinstance(value, dict):
            hay_items.extend(str(v) for v in value.values() if v)
    hay_items.extend(str(payload.get(key) or "") for key in ("summary", "visible_text"))
    hay = "\n".join(hay_items)

    patterns = (
        r"((?:Рис\.|Рисунок|Fig\.)\s*\d[\d.,\w]*[^\n.;]{0,80})",
        r"((?:Структурная\s+)?карта[^\n.;]{0,80})",
        r"((?:Карта|Map)\s*\d*[^\n.;]{0,80})",
        r"((?:Схема|Figure|Fig\.)\s*\d*[^\n.;]{0,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, hay, flags=re.I)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip(" -—:;,.")
            if title and not _bad_generated_title(title):
                return title

    if artifact_type == "map":
        return "Структурная карта по кровле пласта"
    noun = "Визуальный артефакт"
    suffix = f", стр. {page}" if page else ""
    return f"{noun}: {filename}{suffix}"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _payload_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_payload_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_payload_text(item)}" for key, item in value.items())
    return str(value)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = _strip_code_fence(str(raw or "").strip())
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_stringify(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_stringify(v)}" for k, v in value.items() if v not in (None, "", [], {}))
    return str(value)

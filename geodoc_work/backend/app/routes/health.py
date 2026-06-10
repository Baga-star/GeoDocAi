from fastapi import APIRouter

from app.config import get_settings
from app.security import api_key_is_enabled
from app.services.vision_agent import vision_is_configured

router = APIRouter(tags=["health"])


def _configured(value: str | None) -> bool:
    return bool(value and value != "replace-me")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "GeoDoc AI", "version": "0.5.0"}


@router.get("/capabilities")
async def capabilities() -> dict:
    settings = get_settings()
    ocr_enabled = _configured(settings.deepseek_ocr_api_key)
    vision_enabled = settings.enable_visual_analysis and vision_is_configured(settings)
    llm_enabled = _configured(settings.qwen_api_key)
    return {
        "backend": {"status": "online", "version": "0.5.0"},
        "security": {
            "api_key_required": api_key_is_enabled(settings),
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "cors_credentials": settings.cors_allow_credentials,
        },
        "ocr": {
            "enabled": ocr_enabled,
            "provider": "DeepSeek OCR" if ocr_enabled else None,
            "model": settings.deepseek_ocr_model if ocr_enabled else None,
        },
        "vision": {
            "enabled": vision_enabled,
            "provider": "Visual Geology Agent" if vision_enabled else None,
            "model": settings.vision_model if vision_enabled else None,
        },
        "llm": {
            "enabled": llm_enabled,
            "provider": "Qwen" if llm_enabled else None,
            "model": settings.qwen_model if llm_enabled else None,
        },
        "retrieval": {
            "backend": settings.vector_backend,
            "active_backend": "local_in_memory",
            "top_k": settings.top_k,
            "rerank_configured": settings.rerank,
        },
        "demo_mode": settings.enable_demo_mode,
    }

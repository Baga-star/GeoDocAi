from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:8080"
    cors_allow_credentials: bool = False
    api_key: str = ""
    rate_limit_per_minute: int = Field(default=120, ge=0, le=10000)

    enable_demo_mode: bool = False

    parser_engine: str = "hybrid"
    vector_backend: str = "local"
    qdrant_url: AnyHttpUrl = "http://localhost:6333"
    qdrant_collection: str = "geodoc_ai"
    embedding_model: str = "intfloat/multilingual-e5-small"

    # DeepSeek OCR / llm.alem.ai compatible endpoint
    deepseek_ocr_api_key: str = "replace-me"
    deepseek_ocr_url: str = "https://llm.alem.ai/v1/chat/completions"
    deepseek_ocr_model: str = "deepseek-ocr"
    ocr_max_pages: int = Field(default=30, ge=1, le=500)

    # Qwen chat model / OpenAI-compatible endpoint
    qwen_base_url: AnyHttpUrl = "https://llm.alem.ai/v1"
    qwen_api_key: str = "replace-me"
    qwen_model: str = "qwen3.6"

    # Vision / map-reading agent. If VISION_API_KEY is not set, the app falls
    # back to DEEPSEEK_OCR_API_KEY and then QWEN_API_KEY. The endpoint must be
    # OpenAI-compatible and support image_url message content.
    enable_visual_analysis: bool = True
    vision_api_key: str = "replace-me"
    vision_base_url: AnyHttpUrl = "https://llm.alem.ai/v1"
    vision_model: str = "deepseek-ocr"
    vision_max_pages: int = Field(default=25, ge=1, le=300)
    vision_render_dpi: int = Field(default=220, ge=90, le=300)

    top_k: int = Field(default=8, ge=1, le=30)
    similarity_threshold: float = Field(default=0.05, ge=0, le=1)
    rerank: bool = True

    # Load .env correctly whether the backend is started from project root
    # (`uvicorn backend.app.main:app`) or from backend/ (`uvicorn app.main:app`).
    # Later files override earlier ones, so backend/.env can override root .env.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

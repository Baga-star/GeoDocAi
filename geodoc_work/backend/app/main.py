import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.health import router as health_router
from app.routes.trajectory import router as trajectory_router
from app.services.local_index import local_index
from app.security import rate_limit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.enable_demo_mode:
        local_index.seed_demo()
        logger.info("GeoDoc AI запущен. Demo mode enabled; demo index loaded.")
    else:
        logger.info("GeoDoc AI запущен. Demo mode disabled; ждём реальные документы.")
    yield


app = FastAPI(
    title="GeoDoc AI API",
    description="Artifact-aware geological RAG assistant over local parsing, OCR and Qwen.",
    version="0.5.5",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def quota_guard(request: Request, call_next):
    try:
        await rate_limit(request, settings)
    except Exception as exc:
        status_code = getattr(exc, "status_code", 429)
        detail = getattr(exc, "detail", "Слишком много запросов")
        return JSONResponse(status_code=status_code, content={"detail": detail})
    return await call_next(request)


app.include_router(health_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(trajectory_router, prefix="/api")


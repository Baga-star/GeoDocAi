from fastapi import APIRouter, Depends

from app.clients.qwen import QwenClient
from app.config import Settings, get_settings
from app.models import ChatRequest, ChatResponse
from app.security import require_api_key
from app.services.geology_assistant import GeologyAssistant

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


def get_assistant(settings: Settings = Depends(get_settings)) -> GeologyAssistant:
    return GeologyAssistant(QwenClient(settings))


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, assistant: GeologyAssistant = Depends(get_assistant)) -> ChatResponse:
    return await assistant.answer(request.question, top_k=request.top_k)


@router.get("/demo-questions")
async def demo_questions() -> dict[str, list[str]]:
    return {
        "questions": [
            "Физико-механические свойства горных пород по разрезу скважины",
            "Стратиграфический разрез и литологическая характеристика",
            "Конструкция скважины и интервалы бурения",
            "Какие рисунки и карты есть в документе?",
        ]
    }

import asyncio

from app.clients.qwen import QwenClient
from app.config import get_settings
from app.models import DocumentArtifact
from app.services.geology_assistant import GeologyAssistant
from app.services.local_index import chunk_text, classify_query, local_index


def setup_function():
    local_index.clear()


def test_chunk_text_preserves_markdown_table_layout():
    text = "Таблица 4.3\n| Пласт | Интервал, м | Плотность, г/см³ |\n| --- | --- | --- |\n| Mz+Kz | 0-296 | 1,79 |"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "\n| Пласт |" in chunks[0]
    assert "| --- |" in chunks[0]


def test_query_is_table_first_for_physical_mechanical_properties():
    route = classify_query("Физико-механические свойства горных пород по разрезу скважины")
    assert route["route"] == "table-first"
    assert route["preferred_types"][0] == "table"


def test_table_first_answer_returns_structured_table_without_demo():
    artifact = DocumentArtifact(
        document_name="ГТП.pdf",
        page=23,
        artifact_type="table",
        title="Таблица 4.3 Физико-механические свойства горных пород по разрезу скважины",
        columns=["Стратиграфическое подразделение", "Интервал от, м", "Интервал до, м", "Название горной породы", "Плотность, г/см³"],
        rows=[["Mz+Kz", "0", "296", "Суглинки; Глины; Пески", "1,79"]],
        text="Таблица 4.3 Физико-механические свойства горных пород по разрезу скважины",
    )
    local_index.add_artifacts("ГТП.pdf", [artifact])
    assistant = GeologyAssistant(QwenClient(get_settings()))
    response = asyncio.run(assistant.answer("Физико-механические свойства горных пород по разрезу скважины"))
    assert response.used_demo_mode is False
    assert response.answer_type in {"table", "mixed"}
    assert response.tables
    assert "Таблица 4.3" in (response.tables[0].title or "")
    assert response.sources[0].artifact_type == "table"


def test_map_and_figure_artifacts_are_returned():
    artifacts = [
        DocumentArtifact(document_name="ГТП.pdf", page=10, artifact_type="map", title="Карта 2 Структурная карта", text="Карта 2 Структурная карта"),
        DocumentArtifact(document_name="ГТП.pdf", page=11, artifact_type="figure", title="Рисунок 4.1 Конструкция скважины", text="Рисунок 4.1 Конструкция скважины"),
    ]
    local_index.add_artifacts("ГТП.pdf", artifacts)
    assistant = GeologyAssistant(QwenClient(get_settings()))
    map_response = asyncio.run(assistant.answer("Какие карты есть в документе?"))
    fig_response = asyncio.run(assistant.answer("Какие рисунки есть в документе?"))
    assert map_response.maps
    assert fig_response.figures


def test_image_upload_indexes_visual_map_without_vision_key(monkeypatch):
    from io import BytesIO
    from PIL import Image, ImageDraw
    from app.services.document_parser import _parse_image

    monkeypatch.setenv("VISION_API_KEY", "replace-me")
    monkeypatch.setenv("DEEPSEEK_OCR_API_KEY", "replace-me")
    monkeypatch.setenv("QWEN_API_KEY", "replace-me")
    get_settings.cache_clear()

    img = Image.new("RGB", (420, 260), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 50, 360, 190), fill=(245, 238, 135), outline=(20, 60, 180), width=5)
    draw.rectangle((120, 80, 250, 150), fill=(130, 220, 140), outline=(130, 40, 40), width=3)
    for x, y in [(90, 110), (170, 130), (300, 120)]:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(145, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")

    artifacts = asyncio.run(_parse_image("structural-map.png", buf.getvalue(), ".png"))
    assert artifacts
    assert artifacts[0].artifact_type == "map"
    assert artifacts[0].metadata["visual_status"] == "vision_api_not_configured"
    assert artifacts[0].metadata["preview_data_url"].startswith("data:image/")


def test_visual_payload_with_map_text_overrides_wrong_figure_type():
    from app.services.vision_agent import visual_payload_title, visual_payload_type

    payload = {
        "visual_type": "figure",
        "title": "Структурная карта по кровле пласта",
        "summary": "Показаны изолинии -2702, -2704, ВНК внешний и внутренний, добывающие и нагнетательные скважины.",
        "legend": [
            {"label": "Добывающие", "symbol": "красная точка"},
            {"label": "Нагнетательные", "symbol": "зелёный знак"},
        ],
        "contours": [{"label": "ВНК внешний", "style": "синяя линия"}],
        "categories": ["C1", "C2"],
    }

    assert visual_payload_type(payload, fallback="figure") == "map"
    assert visual_payload_title(payload, "map", "map.pdf", 1) == "Структурная карта по кровле пласта"


def test_short_geological_entity_query_returns_readable_answer_not_table_only():
    text = DocumentArtifact(
        document_name="kargaly.pdf",
        page=39,
        artifact_type="text",
        text=(
            "Жигулевский ярус вскрыт лишь в скважинах, пробуренных на самой восточной Александровской складке. "
            "Представлен он мощным комплексом сероцветных, преимущественно терригенных пород, состоящих из аргиллитов, "
            "песчаников и алевролитов с редкими прослоями известняков. "
            "Толщина жигулевского яруса, вскрытого в скважине 14 Александровской складки, определяется в 850-900 м."
        ),
    )
    table = DocumentArtifact(
        document_name="kargaly.pdf",
        page=45,
        artifact_type="table",
        title="Таблица 4.1.1.",
        columns=["Стратиграфическое подразделение", "Скважина №14"],
        rows=[["Жигулевский ярус", "850-900 м"]],
        text="Таблица 4.1.1. Жигулевский ярус 850-900 м",
    )
    local_index.add_artifacts("kargaly.pdf", [text, table])
    assistant = GeologyAssistant(QwenClient(get_settings()))
    response = asyncio.run(assistant.answer("Жигулевский ярус"))
    assert response.answer_type in {"text", "mixed"}
    assert "Найдена релевантная таблица" not in response.answer_markdown
    assert "аргиллит" in response.answer_markdown.lower()
    assert "850-900" in response.answer_markdown
    assert response.tables


def test_visual_pdf_candidate_page_above_max_count_is_rendered(monkeypatch):
    import fitz
    from app.services.document_parser import _parse_pdf_visual_pages

    monkeypatch.setenv("VISION_API_KEY", "replace-me")
    monkeypatch.setenv("DEEPSEEK_OCR_API_KEY", "replace-me")
    get_settings.cache_clear()
    settings = get_settings()
    old_max = settings.vision_max_pages
    settings.vision_max_pages = 3

    doc = fitz.open()
    try:
        for page_index in range(50):
            page = doc.new_page(width=300, height=220)
            if page_index == 43:
                page.insert_text((30, 40), "Рис. 4.1.1. Схематический типовой разрез", fontsize=12)
                page.draw_rect(fitz.Rect(35, 70, 260, 170), color=(0, 0, 0), fill=(0.95, 0.92, 0.65))
            else:
                page.insert_text((30, 40), f"Страница {page_index + 1}", fontsize=10)
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()

    existing = [DocumentArtifact(document_name="geo.pdf", page=44, artifact_type="figure", title="Рис. 4.1.1.", text="Рис. 4.1.1.")]
    try:
        artifacts = asyncio.run(_parse_pdf_visual_pages("geo.pdf", pdf_bytes, existing))
    finally:
        settings.vision_max_pages = old_max
    assert artifacts
    assert artifacts[0].page == 44
    assert artifacts[0].metadata["preview_data_url"].startswith("data:image/")

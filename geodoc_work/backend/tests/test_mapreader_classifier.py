import asyncio
from unittest.mock import patch

from app.config import get_settings
from app.services.document_parser import _visual_artifact_from_image_bytes


async def _fake_vision_figure(*args, **kwargs):
    return {
        "visual_type": "figure",
        "title": "Геологический разрез или схема",
        "summary": "Модель ошибочно назвала структурную карту рисунком.",
        "confidence": "low",
    }


def test_local_mapreader_overrides_wrong_vision_figure_label():
    # A tiny synthetic contour-map-like image: yellow/green zones, blue contour
    # and red/green well markers. It should be routed as map even if the vision
    # model calls it figure.
    from io import BytesIO
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 620), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((120, 110, 800, 500), fill=(250, 248, 170), outline=(0, 60, 210), width=6)
    draw.ellipse((250, 190, 560, 390), fill=(165, 225, 160), outline=(160, 70, 40), width=3)
    for offset in range(0, 140, 28):
        draw.arc((150 + offset, 130 + offset // 2, 760 - offset, 480 - offset // 2), 0, 360, fill=(50, 50, 50), width=2)
    for x, y in [(250, 260), (340, 310), (480, 250), (620, 330), (710, 260)]:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(140, 0, 0))
    for x, y in [(220, 210), (420, 360), (650, 240)]:
        draw.line((x - 10, y, x + 10, y), fill=(0, 140, 120), width=3)
        draw.line((x, y - 10, x, y + 10), fill=(0, 140, 120), width=3)

    buf = BytesIO()
    img.save(buf, format="PNG")

    settings = get_settings()
    old_key = settings.vision_api_key
    old_enable = settings.enable_visual_analysis
    settings.vision_api_key = "test-key"
    settings.enable_visual_analysis = True
    try:
        with patch("app.services.document_parser.analyze_geology_image", _fake_vision_figure):
            artifact = asyncio.run(
                _visual_artifact_from_image_bytes(
                    "synthetic-map.pdf",
                    buf.getvalue(),
                    page=1,
                    mime_type="image/png",
                    fallback_type="figure",
                    source="test",
                )
            )
    finally:
        settings.vision_api_key = old_key
        settings.enable_visual_analysis = old_enable

    assert artifact.artifact_type == "map"
    assert artifact.metadata["local_visual_type"] == "map"
    assert artifact.metadata["visual_analysis"]["visual_type"] == "map"

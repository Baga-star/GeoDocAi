import json
import logging
import re
from typing import Any

from httpx import HTTPError

from app.clients.qwen import QwenClient
from app.config import get_settings
from app.models import ChatResponse, DocumentArtifact
from app.prompts.geology import build_user_prompt
from app.services.local_index import DEMO_CHUNKS, classify_query, local_index, tokenize
from app.services.text_cleanup import clean_generated_answer, compact_spaces, looks_like_intrusive_noise, looks_like_noisy_text, normalize_pdf_prose

logger = logging.getLogger(__name__)


class GeologyAssistant:
    def __init__(self, qwen: QwenClient):
        self.qwen = qwen
        self.settings = get_settings()

    async def answer(self, question: str, top_k: int | None = None) -> ChatResponse:
        route_info = classify_query(question)
        route = str(route_info["route"])
        preferred_types = list(route_info["preferred_types"])  # type: ignore[arg-type]
        chunks = local_index.search(
            question,
            top_k=top_k or self.settings.top_k,
            preferred_types=preferred_types,
            threshold=self.settings.similarity_threshold,
        )

        used_demo_mode = False
        if not chunks and self.settings.enable_demo_mode:
            chunks = DEMO_CHUNKS
            used_demo_mode = True

        if not chunks:
            return self._not_found(question)

        # Add related visual objects from the same/near pages when the main hit is a table/text.
        chunks = self._with_related_visuals(chunks)

        # Safety net for previously indexed files: if the user asks for a map but
        # a visual artifact was stored as `figure`, reclassify it in-memory when
        # its preview/text has map grammar. This fixes old uploads without waiting
        # for a perfect vision-model label.
        chunks = self._coerce_map_like_visuals(chunks, route)

        # Keep display artifacts separately from the LLM evidence. The UI can show
        # nearby maps/figures, but the answer prompt must stay clean and small.
        display_chunks = self._cap_context(chunks, limit=12)
        answer_chunks = self._prepare_answer_context(question, display_chunks, route, limit=5)

        locator_response = _try_locator_answer(question, answer_chunks, display_chunks, used_demo_mode)
        if locator_response:
            return _clean_response_for_ui(locator_response)

        if _is_short_entity_query(question, route):
            tables = [c for c in answer_chunks if c.artifact_type == "table" and c.columns]
            figures = [c for c in display_chunks if c.artifact_type == "figure"]
            maps = [c for c in display_chunks if c.artifact_type == "map"]
            response = _readable_text_answer(question, answer_chunks, tables, figures, maps, used_demo_mode, include_sources=_user_requested_sources(question))
            return _clean_response_for_ui(self._attach_display_artifacts(response, display_chunks))

        prompt = build_user_prompt(question, [chunk.model_dump() for chunk in answer_chunks], route=route)
        if self._qwen_enabled():
            try:
                raw_answer = await self.qwen.complete(prompt)
                parsed = self._parse_qwen_json(raw_answer)
                if parsed:
                    response = self._response_from_qwen(parsed, answer_chunks, used_demo_mode)
                    if not _user_requested_sources(question):
                        response.answer_markdown = _strip_evidence_sections(response.answer_markdown or response.answer or "")
                        response.answer = response.answer_markdown
                    else:
                        response.answer_markdown = _ensure_source_section(response.answer_markdown or response.answer or "", answer_chunks)
                        response.answer = response.answer_markdown
                    response = self._attach_display_artifacts(response, display_chunks)
                    if self._should_override_map_response(route, response, display_chunks):
                        logger.info("Overriding vague Qwen map response with structured MapReader synthesis")
                        return _clean_response_for_ui(_map_answer_from_artifacts(display_chunks, used_demo_mode))
                    if _should_override_entity_response(question, route, response, answer_chunks):
                        logger.info("Overriding weak table-only Qwen response with readable geological synthesis")
                        tables = [c for c in answer_chunks if c.artifact_type == "table" and c.columns]
                        figures = [c for c in display_chunks if c.artifact_type == "figure"]
                        maps = [c for c in display_chunks if c.artifact_type == "map"]
                        response = _readable_text_answer(question, answer_chunks, tables, figures, maps, used_demo_mode, include_sources=_user_requested_sources(question))
                        return _clean_response_for_ui(self._attach_display_artifacts(response, display_chunks))
                    return _clean_response_for_ui(response)
                logger.warning("Qwen returned non-JSON answer; using extractive local synthesis")
            except (HTTPError, RuntimeError) as exc:
                logger.warning("Qwen unavailable: %s — using local synthesis", exc)
            except Exception as exc:
                logger.exception("Qwen unexpected error: %s", exc)

        response = self._extractive_answer(question, answer_chunks, route, used_demo_mode)
        return _clean_response_for_ui(self._attach_display_artifacts(response, display_chunks))


    @staticmethod
    def _should_override_map_response(route: str, response: ChatResponse, chunks: list[DocumentArtifact]) -> bool:
        if route != "map-first":
            return False
        source_maps = [c for c in chunks if c.artifact_type == "map"]
        if not source_maps:
            return False
        answer = (response.answer_markdown or "").lower()
        vague_markers = (
            "не выделены", "не найд", "точная таблица/карта/рисунок",
            "релевантные фрагменты", "недостаточно", "не удалось",
            "визуальным признакам", "даже если vision-модель", "vision-модель на",
            "желтая заливка образует", "зелёная заливка", "площадную зону карты",
        )
        if response.answer_type not in {"map", "mixed"}:
            return True
        if not response.maps:
            return True
        if any(marker in answer for marker in vague_markers):
            return True
        return False

    def _qwen_enabled(self) -> bool:
        return bool(self.settings.qwen_api_key and self.settings.qwen_api_key != "replace-me")

    @staticmethod
    def _with_related_visuals(chunks: list[DocumentArtifact]) -> list[DocumentArtifact]:
        if not chunks:
            return chunks
        doc_id = next((c.document_id for c in chunks if c.document_id), None)
        pages = [c.page for c in chunks if c.page is not None]
        related = local_index.related_artifacts(doc_id, pages, {"figure", "map"}, radius=1)
        seen = {c.id for c in chunks}
        merged = list(chunks)
        for artifact in related:
            if artifact.id not in seen:
                merged.append(artifact)
                seen.add(artifact.id)
        return merged


    @staticmethod
    def _coerce_map_like_visuals(chunks: list[DocumentArtifact], route: str) -> list[DocumentArtifact]:
        if route != "map-first":
            return chunks
        output: list[DocumentArtifact] = []
        for artifact in chunks:
            if artifact.artifact_type != "figure":
                output.append(artifact)
                continue
            if not _is_map_like_visual_artifact(artifact):
                output.append(artifact)
                continue
            metadata = dict(artifact.metadata or {})
            metadata["reclassified_from"] = "figure"
            metadata["mapreader_reclassified"] = True
            title = artifact.title or artifact.caption or "Карта"
            if "карт" not in title.lower():
                title = f"Карта: {title}"
            output.append(
                artifact.model_copy(
                    update={
                        "artifact_type": "map",
                        "title": title,
                        "caption": artifact.caption or title,
                        "metadata": metadata,
                    }
                )
            )
        return output


    @staticmethod
    def _cap_context(chunks: list[DocumentArtifact], limit: int = 12) -> list[DocumentArtifact]:
        if len(chunks) <= limit:
            return chunks
        kept: list[DocumentArtifact] = []
        seen: set[str] = set()
        for artifact in chunks:
            key = artifact.id or f"{artifact.document_id}:{artifact.page}:{artifact.artifact_type}:{artifact.title}"
            if key in seen:
                continue
            kept.append(artifact)
            seen.add(key)
            if len(kept) >= limit:
                break
        return kept

    @staticmethod
    def _prepare_answer_context(question: str, chunks: list[DocumentArtifact], route: str, limit: int = 5) -> list[DocumentArtifact]:
        """Return a small, cleaned evidence set for the answer model.

        The UI can still display additional nearby artifacts, but the LLM should
        not see 10+ noisy OCR snippets. This prevents answers from becoming a raw
        paste of PDF fragments.
        """
        if not chunks:
            return []
        locator = _is_locator_question(question)
        prepared: list[DocumentArtifact] = []
        seen: set[str] = set()

        def priority(artifact: DocumentArtifact) -> int:
            if route == "map-first":
                order = {"map": 0, "figure": 1, "text": 2, "table": 3}
            elif route == "figure-first":
                order = {"figure": 0, "map": 1, "text": 2, "table": 3}
            elif route == "table-first":
                order = {"table": 0, "text": 1, "figure": 2, "map": 3}
            else:
                order = {"text": 0, "table": 1, "figure": 2, "map": 3}
            return order.get(artifact.artifact_type, 9)

        for artifact in sorted(chunks, key=lambda a: (priority(a), -(a.score or 0.0))):
            cleaned = _clean_evidence_artifact(question, artifact, allow_toc=locator)
            if not cleaned:
                continue
            key = _artifact_dedupe_key(cleaned)
            if key in seen:
                continue
            seen.add(key)
            prepared.append(cleaned)
            if len(prepared) >= limit:
                break

        # Fallback: never return an empty context if search found something.
        if not prepared:
            for artifact in chunks[:limit]:
                cleaned = _clean_evidence_artifact(question, artifact, allow_toc=True)
                if cleaned:
                    prepared.append(cleaned)
        return prepared[:limit]

    @staticmethod
    def _attach_display_artifacts(response: ChatResponse, display_chunks: list[DocumentArtifact]) -> ChatResponse:
        """Preserve exact visual/table artifacts for tabs, including preview_data_url."""
        source_tables = [c for c in display_chunks if c.artifact_type == "table"]
        source_figures = [c for c in display_chunks if c.artifact_type == "figure"]
        source_maps = [c for c in display_chunks if c.artifact_type == "map"]
        if source_tables and (not response.tables or not response.tables[0].rows):
            response.tables = source_tables[:3]
        if source_figures:
            response.figures = source_figures[:6]
        if source_maps:
            response.maps = source_maps[:6]
        return response

    @staticmethod
    def _parse_qwen_json(raw: str) -> dict[str, Any] | None:
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            # Try to recover first {...} block.
            match = re.search(r"\{.*\}", raw, flags=re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    return parsed if isinstance(parsed, dict) else None
                except Exception:
                    return None
        return None

    @staticmethod
    def _response_from_qwen(data: dict[str, Any], sources: list[DocumentArtifact], used_demo_mode: bool) -> ChatResponse:
        def artifacts_from_payload(key: str, typ: str) -> list[DocumentArtifact]:
            output: list[DocumentArtifact] = []
            for item in data.get(key, []) or []:
                if not isinstance(item, dict):
                    continue
                output.append(
                    DocumentArtifact(
                        document_name=item.get("document_name"),
                        page=item.get("page"),
                        artifact_type=typ,  # type: ignore[arg-type]
                        title=item.get("title"),
                        caption=item.get("caption"),
                        text=item.get("note") or item.get("caption") or item.get("title") or "",
                        columns=[str(c) for c in (item.get("columns") or [])],
                        rows=[[str(c) for c in row] for row in (item.get("rows") or []) if isinstance(row, list)],
                        metadata={"source": "qwen"},
                    )
                )
            return output

        answer_markdown = str(data.get("answer_markdown") or "")
        if not answer_markdown:
            answer_markdown = "Ответ сформирован по найденным артефактам документа."
        answer_markdown = _polish_answer_markdown(answer_markdown, sources, data.get("answer_type") or "mixed")
        response = ChatResponse(
            answer_type=data.get("answer_type") or "mixed",
            answer_markdown=answer_markdown,
            answer=answer_markdown,
            tables=artifacts_from_payload("tables", "table"),
            figures=artifacts_from_payload("figures", "figure"),
            maps=artifacts_from_payload("maps", "map"),
            sources=sources,
            used_demo_mode=used_demo_mode,
            confidence=data.get("confidence") or "medium",
            missing_data=[str(x) for x in (data.get("missing_data") or [])],
        )
        # Keep retrieved exact artifacts when available so UI preserves rows,
        # visual metadata and inline previews. Qwen still controls the summary.
        source_tables = [s for s in sources if s.artifact_type == "table"]
        source_figures = [s for s in sources if s.artifact_type == "figure"]
        source_maps = [s for s in sources if s.artifact_type == "map"]
        if source_tables and (not response.tables or not response.tables[0].rows):
            response.tables = source_tables[:3]
        if source_figures:
            response.figures = source_figures[:5]
        if source_maps:
            response.maps = source_maps[:5]
        return response

    @staticmethod
    def _not_found(question: str) -> ChatResponse:
        text = (
            "В загруженных документах я не нашёл подтверждённый источник для этого запроса. "
            "Загрузите страницу отчёта с нужной таблицей, картой или рисунком либо уточните пласт, горизонт, скважину, интервал глубин или номер страницы."
        )
        return ChatResponse(
            answer_type="not_found",
            answer_markdown=text,
            answer=text,
            sources=[],
            used_demo_mode=False,
            confidence="low",
            missing_data=["Нет релевантных артефактов в индексе", f"Запрос: {question}"],
        )

    @staticmethod
    def _extractive_answer(
        question: str,
        chunks: list[DocumentArtifact],
        route: str,
        used_demo_mode: bool,
    ) -> ChatResponse:
        tables = [c for c in chunks if c.artifact_type == "table" and c.columns]
        figures = [c for c in chunks if c.artifact_type == "figure"]
        maps = [c for c in chunks if c.artifact_type == "map"]
        text_hits = [c for c in chunks if c.artifact_type == "text"]

        # For explicit table-first queries, never replace an actual table with a prose answer.
        # For short entity queries such as "Жигулевский ярус", the user expects
        # a readable geological explanation; tables remain evidence, not the whole answer.
        if tables and route == "table-first":
            first = tables[0]
            title = first.title or "релевантная таблица"
            src = _source_label(first)
            answer_type = "mixed" if figures or maps else "table"
            answer = (
                f"Данные по этому вопросу находятся в таблице **{title}** ({src}). "
                "Я вывел её во вкладке «Таблицы», чтобы значения глубин, пластов и единиц измерения не потерялись в пересказе."
            )
            nearby = [*(figures[:3]), *(maps[:3])]
            if nearby:
                names = "; ".join(f"{item.title or item.caption or artifact_type_russian(item.artifact_type)}, стр. {item.page or '?'}" for item in nearby[:4])
                answer += f" Рядом с этими данными также найдены визуальные материалы: {names}."
            return ChatResponse(
                answer_type=answer_type, answer_markdown=answer, answer=answer,
                tables=tables[:3], figures=figures[:5], maps=maps[:5], sources=chunks,
                used_demo_mode=used_demo_mode, confidence="high", missing_data=[],
            )

        if route == "map-first" and maps:
            return _clean_response_for_ui(_map_answer_from_artifacts(chunks, used_demo_mode))

        if route == "figure-first" and figures:
            lines = []
            missing: list[str] = []
            for f in figures[:6]:
                note = _visual_reading_note(f)
                lines.append(f"- **{f.title or f.caption or 'Рисунок'}**, {_source_label(f)}" + (f" — {note}" if note else ""))
                if f.metadata.get("visual_status") != "analyzed":
                    missing.append("Рисунок не был проанализирован при загрузке документа. Переиндексируйте документ для активации vision.")
            answer = "Найдены рисунки или схемы, связанные с запросом. Ниже перечислено, что удалось прочитать из визуальных артефактов.\n" + "\n".join(lines)
            return ChatResponse(
                answer_type="figure", answer_markdown=answer, answer=answer,
                figures=figures[:6], maps=maps[:3], tables=tables[:2], sources=chunks,
                used_demo_mode=used_demo_mode, confidence="high" if not missing else "medium", missing_data=sorted(set(missing)),
            )

        # Text/entity fallback with concise human-readable geological synthesis.
        return _clean_response_for_ui(_readable_text_answer(question, chunks, tables, figures, maps, used_demo_mode, include_sources=_user_requested_sources(question)))




ENTITY_CONTEXT_TERMS = {
    "ярус", "горизонт", "пласт", "система", "отдел", "свита", "разрез", "скважина",
    "жигулевский", "оренбургский", "сакмарский", "артинский", "кунгурский", "пермский",
}



GENERIC_ENTITY_TERMS = {"ярус", "горизонт", "пласт", "система", "отдел", "свита", "разрез", "скважина"}
SOURCE_REQUEST_TERMS = {"источник", "источники", "страница", "страницы", "откуда", "доказательства", "ссылка", "ссылки", "source", "sources"}

LOCATOR_TERMS = (
    "где указ", "где находится", "где найти", "в какой таблице", "в какой табл",
    "какая таблица", "на какой странице", "номер таблицы", "номер рисунка", "номер карты",
)


def _is_locator_question(question: str) -> bool:
    q = (question or "").lower().replace("ё", "е")
    return any(term in q for term in LOCATOR_TERMS)


def _artifact_dedupe_key(artifact: DocumentArtifact) -> str:
    body = " ".join([artifact.artifact_type or "", artifact.title or "", artifact.caption or "", artifact.text or ""])
    body = re.sub(r"\W+", " ", body.lower().replace("ё", "е")).strip()
    return body[:240] or (artifact.id or "")


def _clean_evidence_artifact(question: str, artifact: DocumentArtifact, allow_toc: bool = False) -> DocumentArtifact | None:
    """Clean one retrieved artifact before it is sent to the answer model."""
    text = _clean_evidence_text(artifact.text or "")
    caption = compact_spaces(artifact.caption or "") if artifact.caption else None
    title = compact_spaces(artifact.title or "") if artifact.title else None

    hay = "\n".join(x for x in [title or "", caption or "", text] if x).lower().replace("ё", "е")
    if not allow_toc and _looks_like_toc_or_appendix_list(hay):
        return None

    if artifact.artifact_type == "text" and _bad_evidence_text(text):
        return None

    update: dict[str, Any] = {"text": text}
    if caption is not None:
        update["caption"] = caption
    if title is not None:
        update["title"] = title

    # Keep tables structured, but do not send huge damaged tables to the LLM.
    if artifact.columns:
        update["columns"] = [compact_spaces(c) for c in artifact.columns[:16]]
    if artifact.rows:
        cleaned_rows: list[list[str]] = []
        for row in artifact.rows[:20]:
            cleaned_row = [compact_spaces(cell) for cell in row[:16]]
            if any(cleaned_row):
                cleaned_rows.append(cleaned_row)
        update["rows"] = cleaned_rows

    # Visual previews are large and unsafe for prompt; keep only compact metadata.
    metadata = dict(artifact.metadata or {})
    for key in list(metadata):
        if key.endswith("_data_url") or key in {"preview_data_url", "image_data_url", "base64", "raw_image", "raw_bytes"}:
            metadata.pop(key, None)
    update["metadata"] = metadata

    cleaned = artifact.model_copy(update=update)
    if not any([cleaned.text, cleaned.title, cleaned.caption, cleaned.columns, cleaned.rows]):
        return None
    return cleaned


def _clean_evidence_text(value: str, max_len: int = 900) -> str:
    text = normalize_pdf_prose(value or "")
    if not text:
        return ""
    # Remove filenames and UI-like extraction traces from the evidence body.
    text = re.sub(r"\b[\w\-.]*_original\.[\w\-.]*\.pdf\b", " ", text, flags=re.I)
    text = re.sub(r"\b[\w\-.]+\.(?:pdf|docx|xlsx|xls|csv|png|jpg|jpeg)\b", " ", text, flags=re.I)
    text = re.sub(r"\.{3,}|…", ". ", text)
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = compact_spaces(raw)
        if not line:
            continue
        if line.count(".") >= 6 and len(line) < 80:
            continue
        if looks_like_noisy_text(line, 0.34) or looks_like_intrusive_noise(line, 0.30):
            continue
        key = re.sub(r"\W+", " ", line.lower().replace("ё", "е")).strip()
        if key and key not in seen:
            seen.add(key)
            lines.append(line)
    text = "\n".join(lines).strip()
    if len(text) > max_len:
        cut = text[:max_len]
        last = max(cut.rfind(". "), cut.rfind("; "), cut.rfind("\n"), cut.rfind(" "))
        text = cut[:last].strip() if last > max_len * 0.55 else cut.strip()
    return text


def _bad_evidence_text(text: str) -> bool:
    if not text:
        return True
    compacted = compact_spaces(text)
    if len(compacted) < 35:
        return True
    if compacted.count("...") >= 2 or compacted.count("…") >= 2:
        return True
    if looks_like_noisy_text(compacted, 0.42) or looks_like_intrusive_noise(compacted, 0.34):
        return True
    # OCR chunks that start in the middle of a broken word usually produce the
    # ugly answers the user reported. Keep them only if a strong table/figure id exists.
    first = compacted[:40]
    if re.match(r"^[а-яё]{2,}\b", first) and not re.search(r"\b(?:табл|таблица|рис\.|рисунок|карта)\s*\d", compacted, flags=re.I):
        return True
    return False


def _looks_like_toc_or_appendix_list(text: str) -> bool:
    if not text:
        return False
    markers = (
        "список таблиц", "список графических приложений", "список текстовых приложений",
        "наименование приложения", "наименование таблиц", "календарный план работ",
        "основные технико-экономические показатели",
    )
    hits = sum(1 for marker in markers if marker in text)
    numbered = len(re.findall(r"\b\d{1,3}\s+(?:[А-ЯA-ZЁ]|табл|рис)", text, flags=re.I))
    return hits >= 2 or (hits >= 1 and numbered >= 4)


def _try_locator_answer(
    question: str,
    answer_chunks: list[DocumentArtifact],
    display_chunks: list[DocumentArtifact],
    used_demo_mode: bool,
) -> ChatResponse | None:
    if not _is_locator_question(question):
        return None
    chunks = answer_chunks or display_chunks
    if not chunks:
        return None

    q = question.lower().replace("ё", "е")
    q_terms = _query_terms(question)

    def score_artifact(a: DocumentArtifact) -> int:
        hay = " ".join([a.title or "", a.caption or "", a.text or ""]).lower().replace("ё", "е")
        score = len(q_terms & set(tokenize(hay))) * 4
        if "количествен" in q and "количествен" in hay:
            score += 10
        if "перспектив" in q and "перспектив" in hay:
            score += 8
        if a.artifact_type == "table":
            score += 4
        if a.artifact_type in {"map", "figure"}:
            score += 3
        if re.search(r"\b(?:табл\.?|таблица|рис\.?|рисунок|карта)\s*\d", hay, flags=re.I):
            score += 3
        return score

    best = max(chunks, key=score_artifact)
    if score_artifact(best) <= 0:
        return None

    hay = " ".join([best.title or "", best.caption or "", best.text or ""])
    hay_clean = compact_spaces(hay)
    table_match = re.search(r"(?:табл\.?|таблиц[аеуы]?)\s*№?\s*([0-9]+(?:\.[0-9]+)*)", hay_clean, flags=re.I)
    figure_match = re.search(r"(?:рис\.?|рисун(?:ок|ке|ка)?)\s*№?\s*([0-9]+(?:\.[0-9]+)*)", hay_clean, flags=re.I)

    tables = [c for c in display_chunks if c.artifact_type == "table"]
    figures = [c for c in display_chunks if c.artifact_type == "figure"]
    maps = [c for c in display_chunks if c.artifact_type == "map"]

    subject = _locator_subject(question)
    page = f", стр. {best.page}" if best.page else ""
    if table_match:
        answer = f"{subject} указана в таблице {table_match.group(1)}{page}."
        if "количествен" in q and "перспектив" in q:
            answer += " В документе эта таблица относится к разделу с результатами оценки перспективных углеводородов; рядом перечислены календарный план работ, объёмы геологоразведочных работ и основные технико-экономические показатели."
    elif best.artifact_type == "table":
        title = best.title or "релевантной таблице"
        answer = f"{subject} указана в {title}{page}. Полные строки лучше смотреть во вкладке «Таблицы»."
    elif figure_match:
        answer = f"Нужный материал находится в рисунке {figure_match.group(1)}{page}."
    elif best.artifact_type in {"map", "figure"}:
        kind = "карте" if best.artifact_type == "map" else "рисунке"
        title = best.title or best.caption or kind
        answer = f"Нужный материал находится в {kind}: {title}{page}. Карточка с изображением доступна во вкладке «Карты и рисунки»."
    else:
        answer = f"{subject} найдена в текстовом фрагменте документа{page}. Точного номера таблицы или рисунка в найденном фрагменте нет."

    return ChatResponse(
        answer_type="mixed" if tables or figures or maps else "text",
        answer_markdown=answer,
        answer=answer,
        tables=tables[:3],
        figures=figures[:6],
        maps=maps[:6],
        sources=answer_chunks[:5] or chunks[:5],
        used_demo_mode=used_demo_mode,
        confidence="high" if (table_match or figure_match or best.page) else "medium",
        missing_data=[],
    )


def _locator_subject(question: str) -> str:
    q = question.strip().rstrip("?")
    q = re.sub(r"^где\s+(?:указан[аоы]?|находится|найти)\s+", "", q, flags=re.I)
    q = re.sub(r"^в\s+какой\s+таблице\s+(?:указан[аоы]?\s+)?", "", q, flags=re.I)
    if not q or len(q) > 120:
        return "Искомая информация"
    first = q[0].upper() + q[1:]
    return first
EVIDENCE_HEADINGS_RE = re.compile(
    r"\n?#{2,4}\s*(?:Связанная\s+таблица|Рисунки\s*/\s*схемы\s+рядом|Рисунки\s+рядом|Карты\s+рядом|Источник|Источники)\b.*?(?=\n#{2,4}\s+|\Z)",
    flags=re.I | re.S,
)

def _user_requested_sources(question: str) -> bool:
    q = (question or "").lower().replace("ё", "е")
    return any(term in q for term in SOURCE_REQUEST_TERMS)

def _strip_evidence_sections(markdown: str) -> str:
    text = re.sub(EVIDENCE_HEADINGS_RE, "", markdown or "").strip()
    # Qwen sometimes emits headings inline because it ignores markdown newlines.
    text = re.sub(r"\s*#{2,4}\s*(?:Связанная\s+таблица|Рисунки\s*/\s*схемы\s+рядом|Источник|Источники)\b.*$", "", text, flags=re.I | re.S).strip()
    return text

def _ensure_source_section(markdown: str, chunks: list[DocumentArtifact]) -> str:
    text = _strip_evidence_sections(markdown)
    source_lines = _unique_source_lines(chunks, limit=8)
    if source_lines:
        text += "\n\n### Источники\n" + "\n".join(f"- {line}" for line in source_lines)
    return text.strip()

SECTION_HINTS = (
    ("Что это", ("ярус", "горизонт", "система", "отдел", "вскрыт", "относ", "представлен")),
    ("Положение в разрезе", ("верх", "ниж", "кровл", "подошв", "разрез", "скважин", "складк", "отдел")),
    ("Литология", ("аргиллит", "песчан", "алевролит", "известня", "карбонат", "терриген", "пород")),
    ("Мощность / глубины", ("мощност", "толщин", "глубин", "м ", "метр", "850", "900", "3000")),
)


def _is_short_entity_query(question: str, route: str) -> bool:
    if route != "text-first": return False
    q_tokens = set(tokenize(question))
    if not q_tokens or len(q_tokens) > 5: return False
    if any(token in q_tokens for token in {"таблица", "карта", "рисунок", "схема"}): return False
    return bool(q_tokens & ENTITY_CONTEXT_TERMS) or len(q_tokens) <= 3

def _clean_response_for_ui(response: ChatResponse) -> ChatResponse:
    response.answer_markdown = clean_generated_answer(response.answer_markdown or response.answer or "")
    response.answer = response.answer_markdown
    def clean_artifact(artifact: DocumentArtifact) -> DocumentArtifact:
        update: dict[str, Any] = {}
        if artifact.text: update["text"] = normalize_pdf_prose(artifact.text)
        if artifact.caption: update["caption"] = compact_spaces(artifact.caption)
        if artifact.title: update["title"] = compact_spaces(artifact.title)
        if artifact.columns: update["columns"] = [compact_spaces(c) for c in artifact.columns]
        if artifact.rows: update["rows"] = [[compact_spaces(cell) for cell in row] for row in artifact.rows]
        return artifact.model_copy(update=update) if update else artifact
    def prepare_artifact(a: DocumentArtifact) -> DocumentArtifact:
        cleaned = clean_artifact(a)
        if cleaned.artifact_type == "table" and _table_looks_noisy(cleaned):
            metadata = dict(cleaned.metadata or {})
            metadata["extraction_warning"] = "noisy_pdf_table_hidden"
            return cleaned.model_copy(update={"columns": [], "rows": [], "metadata": metadata})
        return cleaned
    response.tables = [prepare_artifact(a) for a in (response.tables or [])]
    response.figures = [prepare_artifact(a) for a in (response.figures or [])]
    response.maps = [prepare_artifact(a) for a in (response.maps or [])]
    response.sources = [prepare_artifact(a) for a in (response.sources or [])]
    return response

def _should_override_entity_response(question: str, route: str, response: ChatResponse, chunks: list[DocumentArtifact]) -> bool:
    if route != "text-first":
        return False
    if not chunks:
        return False
    q_tokens = set(tokenize(question))
    if not q_tokens:
        return False
    looks_like_entity = len(q_tokens) <= 5 and not any(token in q_tokens for token in {"таблица", "карта", "рисунок", "схема"})
    if not looks_like_entity:
        return False
    answer = (response.answer_markdown or response.answer or "").lower().replace("ё", "е")
    weak_markers = (
        "найдена релевантная таблица",
        "я вывел ее как структурированные строки",
        "ответ сформирован по найденным артефактам",
        "релевантные фрагменты",
        "точная таблица/карта/рисунок",
    )
    if response.answer_type == "table":
        return True
    if any(marker in answer for marker in weak_markers):
        return True
    useful_token_hits = sum(1 for token in q_tokens if token in answer)
    return useful_token_hits == 0


def _readable_text_answer(
    question: str,
    chunks: list[DocumentArtifact],
    tables: list[DocumentArtifact],
    figures: list[DocumentArtifact],
    maps: list[DocumentArtifact],
    used_demo_mode: bool,
    include_sources: bool = False,
) -> ChatResponse:
    facts = _extract_entity_facts(question, chunks)
    if not facts:
        raw = _extract_facts(question, [c for c in chunks if c.artifact_type == "text"] or chunks)
        facts = _fallback_fact_lines(raw)

    lines: list[str] = []
    if facts:
        answer_paragraph = " ".join(_ensure_sentence(fact) for fact in facts[:4])
        lines.append(answer_paragraph.strip())
    else:
        lines.append("В найденных фрагментах есть совпадения по запросу, но их недостаточно для уверенного геологического вывода.")

    if include_sources:
        source_lines = _unique_source_lines(chunks, limit=8)
        if source_lines:
            lines += ["", "### Источники"]
            lines.extend(f"- {line}" for line in source_lines)
        table_note = _table_match_note(question, tables)
        if table_note:
            lines += ["", "### Связанная таблица", f"- {table_note}"]
        visual_notes: list[str] = []
        for item in [*figures[:2], *maps[:2]]:
            visual_notes.append(f"{item.title or item.caption or artifact_type_russian(item.artifact_type)}, стр. {item.page or '?'}")
        if visual_notes:
            lines += ["", "### Рисунки / схемы рядом", *[f"- {note}" for note in visual_notes[:3]]]

    missing: list[str] = []
    if not any(c.artifact_type == "text" for c in chunks):
        missing.append("Ответ основан в основном на таблицах/подписях; для полного объяснения нужен текстовый фрагмент раздела")
    if tables and _table_looks_noisy(tables[0]):
        missing.append("Структура таблицы извлечена из PDF неидеально; проверяйте значения в источнике/странице")

    answer = "\n".join(lines)
    return ChatResponse(
        answer_type="mixed" if tables or figures or maps else "text",
        answer_markdown=answer,
        answer=answer,
        tables=tables[:3],
        figures=figures[:4],
        maps=maps[:4],
        sources=chunks,
        used_demo_mode=used_demo_mode,
        confidence="high" if len(facts) >= 3 else "medium" if facts else "low",
        missing_data=missing,
    )


def artifact_type_russian(artifact_type: str | None) -> str:
    if artifact_type == "table":
        return "Таблица"
    if artifact_type == "figure":
        return "Рисунок"
    if artifact_type == "map":
        return "Карта"
    return "Источник"


def _query_terms(question: str) -> set[str]:
    tokens = set(tokenize(question))
    # Keep short geological entity tokens and their stems. The normal tokenizer already strips common suffixes.
    return {t for t in tokens if len(t) >= 3}


def _extract_entity_facts(question: str, chunks: list[DocumentArtifact]) -> list[str]:
    terms = _query_terms(question)
    if not terms:
        return []
    primary_terms = {term for term in terms if term not in GENERIC_ENTITY_TERMS}

    text_artifacts = [c for c in chunks if c.artifact_type == "text" and c.text]
    if not text_artifacts:
        text_artifacts = [c for c in chunks if c.text]

    candidates: list[tuple[int, str]] = []
    for artifact in text_artifacts:
        for sentence in _split_geo_sentences(_normalize_prose(artifact.text)):
            low = sentence.lower().replace("ё", "е")
            sentence_tokens = set(tokenize(low))
            overlap = len(terms & sentence_tokens)
            primary_overlap = len(primary_terms & sentence_tokens) if primary_terms else 0
            if not overlap:
                continue
            # For entity queries like "Жигулевский ярус", generic words such as
            # "ярус" alone are not enough; otherwise the answer drifts to nearby
            # unrelated Kazan/Orenburg/Sakmar sections.
            if primary_terms and not primary_overlap:
                continue
            score = overlap * 5 + primary_overlap * 8
            if any(term in low for term in ("представлен", "вскрыт", "сложен", "относ", "выделяется")):
                score += 4
            if any(term in low for term in ("аргиллит", "песчан", "алевролит", "известня", "карбонат")):
                score += 3
            if any(term in low for term in ("мощност", "толщин", "глубин", " м")) or re.search(r"\d+\s*[-–—]\s*\d+\s*м", low):
                score += 3
            if len(sentence) < 45:
                score -= 2
            if len(sentence) > 420:
                score -= 10
            if len(sentence) > 700:
                score -= 20
            candidates.append((score, sentence))

    # Add nearby/supporting geological sentences from the same artifact. For short entity queries,
    # the sentence after the entity name often contains lithology without repeating the entity name.
    for artifact in text_artifacts:
        normalized = _normalize_prose(artifact.text)
        artifact_tokens = set(tokenize(normalized))
        if primary_terms:
            if not (primary_terms & artifact_tokens):
                continue
        elif not (terms & artifact_tokens):
            continue
        low_artifact = normalized.lower().replace("ё", "е")
        query_positions = [low_artifact.find(term) for term in terms if term in low_artifact]
        query_positions = [pos for pos in query_positions if pos >= 0]
        for sentence in _split_geo_sentences(normalized):
            low = sentence.lower().replace("ё", "е")
            sentence_tokens = set(tokenize(low))
            has_query_term = bool((primary_terms or terms) & sentence_tokens)
            if not has_query_term:
                if not query_positions:
                    continue
                pos = low_artifact.find(low[: min(len(low), 80)])
                if pos < 0 or min(abs(pos - qpos) for qpos in query_positions) > 520:
                    continue
            if any(term in low for term in ("аргиллит", "песчан", "алевролит", "известня", "карбонат", "терриген")):
                candidates.append((8 if has_query_term else 6, sentence))
            if any(term in low for term in ("мощност", "толщин")) and re.search(r"\d", low):
                candidates.append((7 if has_query_term else 5, sentence))

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected: list[str] = []
    for _, sentence in candidates:
        fact = _sentence_to_fact(sentence)
        if not fact:
            continue
        key = re.sub(r"\W+", " ", fact.lower().replace("ё", "е")).strip()
        if any(_too_similar(key, old) for old in selected):
            continue
        selected.append(fact)
        if len(selected) >= 6:
            break

    # Put the easiest-to-read definition/lithology/depth facts first.
    def rank(fact: str) -> int:
        low = fact.lower().replace("ё", "е")
        if any(x in low for x in ("представлен", "вскрыт", "сложен", "относ")):
            return 0
        if any(x in low for x in ("аргиллит", "песчан", "алевролит", "известня")):
            return 1
        if any(x in low for x in ("мощност", "толщин", "глубин", " м")):
            return 2
        return 3

    ranked = sorted(selected, key=rank)
    unique: list[str] = []
    seen: set[str] = set()
    for fact in ranked:
        key = re.sub(r"\W+", " ", fact.lower().replace("ё", "е")).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(fact)
    return unique


def _normalize_prose(text: str) -> str:
    text = normalize_pdf_prose(text or "")
    text = re.sub(r"[ \t]+", " ", text)
    # Join hard-wrapped PDF lines inside paragraphs, but keep headings/tables readable.
    lines = [line.strip() for line in text.splitlines()]
    out: list[str] = []
    buf = ""
    for line in lines:
        if not line:
            if buf:
                out.append(buf.strip())
                buf = ""
            continue
        if line.startswith("|") or re.match(r"^(Таблица|Рис\.|Рисунок|Карта|\d+(?:\.\d+)*)\b", line):
            if buf:
                out.append(buf.strip())
                buf = ""
            out.append(line)
            continue
        if buf:
            if re.search(r"[-–—]$", buf):
                buf = re.sub(r"[-–—]$", "", buf) + line
            else:
                buf += " " + line
        else:
            buf = line
    if buf:
        out.append(buf.strip())
    return "\n".join(out)


def _split_geo_sentences(text: str) -> list[str]:
    normalized = _normalize_prose(text)
    pieces = re.split(r"(?<=[.!?])\s+(?=[А-ЯA-ZЁӘҒҚҢӨҰҮҺІ0-9])|\n+", normalized)
    return [re.sub(r"\s+", " ", p).strip(" -•\t") for p in pieces if len(p.strip()) > 25]


def _sentence_to_fact(sentence: str, max_len: int = 310) -> str:
    text = compact_spaces(normalize_pdf_prose(sentence))
    text = re.sub(r"ГУ \"Управление природных ресурсов.*$", "", text).strip()
    mixed_case_tokens = [tok for tok in re.findall(r"[A-Za-zА-Яа-яЁё]+", text) if any(ch.isupper() for ch in tok[1:])]
    if re.search(r"\b(?:рсо|ресу|роева|чгуано|нлеа|петкра|рясу|скр|оа|жк|нт|туа)\w*\b", text, flags=re.I):
        return ""
    if len(mixed_case_tokens) >= 2:
        return ""
    if not text or looks_like_noisy_text(text, threshold=0.42) or looks_like_intrusive_noise(text, threshold=0.24):
        return ""
    if len(text) > max_len:
        cut = text[: max_len - 1]
        last = max(cut.rfind(";"), cut.rfind(","), cut.rfind(" "))
        text = cut[:last].rstrip() + "…" if last > 80 else cut.rstrip() + "…"
    return text


def _ensure_sentence(text: str) -> str:
    value = compact_spaces(text)
    if not value:
        return ""
    value = re.sub(r"\.{3,}|…", ". ", value).strip(" -—;,")
    return value if value.endswith((".", "!", "?")) else value + "."


def _too_similar(new_key: str, selected_facts: list[str]) -> bool:
    new_tokens = set(new_key.split())
    if not new_tokens:
        return True
    for fact in selected_facts:
        old_tokens = set(re.sub(r"\W+", " ", fact.lower().replace("ё", "е")).split())
        if not old_tokens:
            continue
        if len(new_tokens & old_tokens) / max(len(new_tokens | old_tokens), 1) > 0.72:
            return True
    return False


def _fallback_fact_lines(raw: str) -> list[str]:
    if not raw:
        return []
    lines = []
    for item in raw.splitlines():
        item = item.strip(" -•\t")
        if item:
            lines.append(_sentence_to_fact(item, max_len=260))
    return [x for x in lines if x][:4]


def _table_match_note(question: str, tables: list[DocumentArtifact]) -> str:
    if not tables:
        return ""
    terms = _query_terms(question)
    best = tables[0]
    title = best.title or "релевантная таблица"
    page = f", стр. {best.page}" if best.page else ""
    if _table_looks_noisy(best):
        return f"{title}{page}: таблица связана с запросом, но PDF извлёк её с искажениями. Используйте её как указатель на первоисточник; значения лучше сверить на странице документа."

    matched_rows: list[str] = []
    for row in best.rows or []:
        row_text = " | ".join(str(cell) for cell in row if str(cell).strip())
        if not row_text:
            continue
        row_tokens = set(tokenize(row_text))
        if terms & row_tokens:
            matched_rows.append(_sentence_to_fact(row_text, max_len=180))
            if len(matched_rows) >= 2:
                break
    if matched_rows:
        return f"{title}{page}. В ней есть строки по запросу: " + "; ".join(matched_rows) + "."
    return f"{title}{page} связана с этим фрагментом; полные строки показаны во вкладке «Таблицы»."


def _unique_source_lines(chunks: list[DocumentArtifact], limit: int = 4) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    # Prefer text/table sources over caption-only visual placeholders for entity answers.
    ordered = sorted(chunks, key=lambda c: {"text": 0, "table": 1, "figure": 2, "map": 3}.get(c.artifact_type, 4))
    for c in ordered:
        label = _source_label(c)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(label)
        if len(output) >= limit:
            break
    return output


def _table_looks_noisy(table: DocumentArtifact) -> bool:
    values = [*(table.columns or [])]
    for row in (table.rows or [])[:10]:
        values.extend(row)
    values = [str(value or "") for value in values if str(value or "").strip()]
    if not values:
        return False
    noisy = 0
    for text in values:
        if looks_like_intrusive_noise(text, threshold=0.16):
            noisy += 1
            continue
        if len(text) >= 8 and len(re.findall(r"\b[А-Яа-яA-Za-z]\b", text)) >= 2:
            noisy += 1
    return noisy / max(len(values), 1) > 0.10

def _is_map_like_visual_artifact(artifact: DocumentArtifact) -> bool:
    metadata = artifact.metadata or {}
    if metadata.get("local_visual_type") == "map":
        return True

    payload = metadata.get("visual_analysis")
    hay = "\n".join(
        str(x or "")
        for x in (artifact.title, artifact.caption, artifact.text, payload)
    ).lower().replace("ё", "е")
    map_terms = (
        "структурная карта", "карта", "кровл", "подошв", "изолини", "контур",
        "внк", "гнк", "гвк", "скважин", "добывающ", "нагнетатель",
        "c1", "c2", "c3", "с1", "с2", "с3", "масштаб", "координат",
    )
    if sum(1 for term in map_terms if term in hay) >= 2:
        return True

    return False


def _map_answer_from_artifacts(chunks: list[DocumentArtifact], used_demo_mode: bool) -> ChatResponse:
    maps = [c for c in chunks if c.artifact_type == "map"]
    figures = [c for c in chunks if c.artifact_type == "figure"]
    tables = [c for c in chunks if c.artifact_type == "table" and c.columns]
    if not maps:
        message = (
            "Карта не выделена как отдельный map-артефакт. Индекс нашёл связанные фрагменты, но не смог уверенно определить визуальный объект как карту. "
            "Перезагрузите документ после обновления MapReader или уточните страницу/название карты."
        )
        return ChatResponse(
            answer_type="not_found",
            answer_markdown=message,
            answer=message,
            sources=chunks,
            used_demo_mode=used_demo_mode,
            confidence="low",
            missing_data=["Нет map-артефакта в найденных источниках"],
        )

    first = maps[0]
    metadata = first.metadata or {}
    payload = metadata.get("visual_analysis")
    local_reading = metadata.get("local_map_reading")
    analyzed = metadata.get("visual_status") == "analyzed"
    title = _clean_visual_title(first, fallback="Структурная карта по кровле пласта")

    # Merge visual-model details with local MapReader heuristics into one clean,
    # non-repeating answer. The UI already shows the image, so the prose should
    # read like a human geologist's note, not repeat the card title.
    lines: list[str] = []
    if analyzed and isinstance(payload, dict):
        lines.append(
            f"Прочитана **{title}**. По карте видны цветовые зоны, контуры/изолинии и точечные маркеры скважин; ниже перечислены только элементы, которые есть в visual evidence."
        )
    else:
        lines.append(
            f"Найдена **{title}**. Локальный MapReader распознал её как карту по визуальной структуре: цветовые зоны, линии контуров/изолиний и точечные маркеры."
        )

    interpretation: list[str] = []
    if isinstance(payload, dict):
        interpretation.extend(_format_visual_items(payload.get("interpretation"), limit=8))
    if isinstance(local_reading, dict):
        interpretation.extend(_format_visual_items(local_reading.get("interpretation"), limit=8))
    interpretation = _dedupe_lines(interpretation)
    if interpretation:
        lines += ["", "### Основная интерпретация", *[f"- {item}" for item in interpretation[:8]]]

    # Prefer structured blocks over a generic summary. This avoids one-line answers like
    # "карта: жёлтая заливка..." and makes it visible that the agent reads the map.
    block_specs = [
        ("### Зоны и легенда", "legend", 8),
        ("### Контуры и изолинии", "contours", 8),
        ("### Скважины / точки", "wells", 12),
        ("### Прочитанные подписи", "visible_text", 10),
        ("### Наблюдения", "observations", 8),
    ]
    emitted: set[str] = set()
    for heading, key, limit in block_specs:
        items: list[str] = []
        if isinstance(payload, dict):
            items.extend(_format_visual_items(payload.get(key), limit=limit))
        if isinstance(local_reading, dict):
            items.extend(_format_visual_items(local_reading.get(key), limit=limit))
        items = _dedupe_lines(items)
        if items:
            emitted.add(key)
            lines += ["", heading, *[f"- {item}" for item in items[:limit]]]

    if not emitted and isinstance(local_reading, dict):
        summary = _clean_visual_text(str(local_reading.get("summary") or ""), max_len=420)
        if summary:
            lines += ["", "### Что видно на карте", f"- {summary}"]

    lines += ["", "### Источник", f"- {_source_label(first)}"]

    missing: list[str] = []
    limitations: list[str] = []
    if isinstance(payload, dict):
        limitations.extend(_format_visual_items(payload.get("limitations"), limit=4))
    if isinstance(local_reading, dict):
        limitations.extend(_format_visual_items(local_reading.get("limitations"), limit=4))
    limitations = _dedupe_lines(limitations)
    if limitations:
        lines += ["", "### Ограничения", *[f"- {item}" for item in limitations[:4]]]
    for m in maps:
        if (m.metadata or {}).get("visual_status") != "analyzed":
            missing.append("Точные номера скважин, значения изолиний и мелкие подписи требуют подключённой Vision/OCR-модели и хорошего качества скана")
    if analyzed and isinstance(payload, dict):
        has_details = any(_format_visual_items(payload.get(key), limit=1) for key in ("legend", "contours", "wells", "visible_text", "observations", "categories"))
        if not has_details and not isinstance(local_reading, dict):
            missing.append("Vision подтвердил карту, но не извлёк достаточно деталей легенды, скважин или подписей")

    answer = "\n".join(lines)
    return ChatResponse(
        answer_type="map",
        answer_markdown=answer,
        answer=answer,
        maps=maps[:6],
        figures=figures[:3],
        tables=tables[:2],
        sources=chunks,
        used_demo_mode=used_demo_mode,
        confidence="high" if analyzed and not missing else "medium",
        missing_data=sorted(set(missing)),
    )

def _polish_answer_markdown(markdown: str, sources: list[DocumentArtifact], answer_type: str) -> str:
    """Normalize LLM answers into a human, non-extractive format."""
    text = re.sub(r"\n{3,}", "\n\n", (markdown or "").strip())
    text = re.sub(r"^\s*\*\*\s*ОТВЕТ\s*\*\*\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*ОТВЕТ\s*[:\-]?\s*", "", text, flags=re.I)
    text = re.sub(r"(?im)^\s*#{1,4}\s*Краткий\s+вывод\s*$", "", text)
    text = re.sub(r"(?i)^\s*Краткий\s+вывод\s*[-—:]*\s*", "", text.strip())
    text = re.sub(r"\.{3,}|…", ". ", text)
    text = re.sub(r"\b[\w\-.]*_original\.[\w\-.]*\.pdf\b", "", text, flags=re.I)
    if not text:
        text = "Ответ сформирован по найденным артефактам документа, но в нём не хватает точных данных для полного вывода."

    # If the model returned headings/bullets despite the prompt, compress them into
    # a concise readable paragraph unless the question explicitly requested sources.
    text = _strip_evidence_sections(text)
    text = re.sub(r"(?m)^#{1,4}\s+", "", text)
    text = re.sub(r"(?m)^[-*]\s+", "", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if sentences:
        # Drop repeated or broken-looking sentences.
        unique: list[str] = []
        seen: set[str] = set()
        for sentence in sentences:
            clean = _sentence_to_fact(sentence, max_len=260)
            if not clean:
                continue
            key = re.sub(r"\W+", " ", clean.lower().replace("ё", "е")).strip()
            if key in seen:
                continue
            seen.add(key)
            unique.append(_ensure_sentence(clean))
            if len(unique) >= 4:
                break
        text = " ".join(unique) if unique else text

    words = text.split()
    if len(words) > 220:
        text = " ".join(words[:210]).rstrip(" ,;:-") + "."

    if answer_type == "not_found" and "В найденных фрагментах точного ответа нет" not in text:
        text = "В найденных фрагментах точного ответа нет. Уточните страницу, пласт, горизонт, скважину или интервал либо загрузите документ с нужной таблицей, картой или рисунком."
    return clean_generated_answer(text)


def _simple_bullets_from_text(text: str, limit: int = 4) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    cleaned = [re.sub(r"\s+", " ", part).strip(" -•\t") for part in parts]
    output = [part for part in cleaned if part]
    if not output:
        return ["Найдены релевантные данные, но ответ требует уточнения источника."]
    return output[:limit]


def _clean_visual_title(artifact: DocumentArtifact, fallback: str = "Карта") -> str:
    payload = artifact.metadata.get("visual_analysis") if artifact.metadata else None
    candidates: list[str] = []
    if isinstance(payload, dict):
        candidates.extend(str(payload.get(key) or "") for key in ("title", "caption"))
    candidates.extend([artifact.title or "", artifact.caption or ""])
    for candidate in candidates:
        text = _clean_visual_text(candidate, max_len=120)
        low = text.lower().replace("ё", "е")
        if not text:
            continue
        if any(marker in low for marker in (
            "даже если", "vision-модель", "визуальным признакам", "желтая заливка",
            "зеленая заливка", "образует основную", "площадную зону", "похожие на"
        )):
            continue
        if low in {"контурной/структурной карты", "контурная/структурная карта", "карта", "рисунок", "figure", "map"}:
            continue
        if len(text) < 4:
            continue
        return text
    hay = " ".join(candidates + [artifact.text or ""]).lower().replace("ё", "е")
    if "кровл" in hay and "пласт" in hay:
        return "Структурная карта по кровле пласта"
    if artifact.artifact_type == "map":
        return fallback or "Структурная карта по кровле пласта"
    return fallback


def _clean_visual_text(value: str, max_len: int = 520) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"^карта\s+по\s+визуальным\s+признакам\s*", "", text, flags=re.I)
    text = re.sub(r",?\s*даже\s+если\s+vision[- ]модель.*$", "", text, flags=re.I)
    text = text.strip(" .;:—-")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _format_visual_items(value: Any, limit: int = 8) -> list[str]:
    if value in (None, "", [], {}):
        return []
    items = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            priority_keys = ("label", "id", "type", "value", "style", "meaning", "relative_position")
            parts = []
            for key in priority_keys:
                val = item.get(key)
                if val not in (None, "", [], {}):
                    parts.append(str(val))
            if not parts:
                parts = [f"{k}: {v}" for k, v in item.items() if v not in (None, "", [], {})]
            text = " — ".join(parts)
        else:
            text = str(item)
        text = _clean_visual_text(re.sub(r"\s+", " ", text).strip(), max_len=260)
        low = text.lower().replace("ё", "е")
        if "даже если vision" in low or "визуальным признакам" in low or "local mapreader" in low:
            continue
        if text and text not in output:
            output.append(text)
    return output


def _dedupe_lines(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_visual_text(str(item), max_len=260)
        key = text.lower().replace("ё", "е")
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _visual_reading_note(artifact: DocumentArtifact, max_len: int = 360) -> str:
    payload = artifact.metadata.get("visual_analysis") if artifact.metadata else None
    if isinstance(payload, dict):
        parts: list[str] = []
        summary = payload.get("summary")
        if summary:
            parts.append(str(summary))
        observations = payload.get("observations")
        if isinstance(observations, list) and observations:
            parts.append("; ".join(str(x) for x in observations[:3]))
        legend = payload.get("legend")
        if isinstance(legend, list) and legend:
            parts.append("Легенда: " + "; ".join(str(item.get("label") or item) if isinstance(item, dict) else str(item) for item in legend[:4]))
        contours = payload.get("contours")
        if isinstance(contours, list) and contours:
            parts.append("Контуры: " + "; ".join(str(item.get("label") or item.get("value") or item) if isinstance(item, dict) else str(item) for item in contours[:4]))
        note = " ".join(parts).strip()
    else:
        note = (artifact.text or artifact.caption or "").strip()
    return _clean_visual_text(re.sub(r"\s+", " ", note), max_len=max_len)


def _source_label(artifact: DocumentArtifact) -> str:
    name = artifact.document_name or "Документ"
    page = f", стр. {artifact.page}" if artifact.page else ""
    source_title = _clean_visual_title(artifact, fallback="") if artifact.artifact_type in {"map", "figure"} else (artifact.title or "")
    title = f" — {source_title}" if source_title else ""
    return f"{name}{page}{title}"


def _extract_facts(question: str, chunks: list[DocumentArtifact]) -> str:
    context = "\n".join(c.text for c in chunks if c.text)
    if not context:
        return ""
    facts: list[str] = []
    patterns = [
        (r"дебит[^.\n]*?([\d]+(?:[,.]\d+)?\s*(?:т/сут|м3/сут|м³/сут))", "Дебит: {}."),
        (r"интервал[^\d]*(\d{1,5}(?:[,.]\d+)?\s*[-–—]\s*\d{1,5}(?:[,.]\d+)?\s*м)", "Интервал: {}."),
        (r"горизонт\s+([A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9\-+]+)", "Горизонт: {}."),
        (r"пласт\s+([A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9\-+]+)", "Пласт: {}."),
    ]
    for pattern, template in patterns:
        match = re.search(pattern, context, flags=re.I)
        if match:
            value = match.group(1).strip()
            line = template.format(value)
            if line not in facts:
                facts.append(line)
    if facts:
        return "\n".join(f"- {fact}" for fact in facts)
    # Return a short relevant excerpt, preserving line breaks.
    excerpt = context.strip()[:900]
    return excerpt + ("…" if len(context) > 900 else "")

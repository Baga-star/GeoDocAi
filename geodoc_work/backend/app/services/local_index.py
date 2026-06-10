import logging
import math
import re
import uuid
from collections import Counter, defaultdict
from typing import Iterable

from app.models import DocumentArtifact, SourceChunk

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9]+")

STOP_WORDS = {
    "и", "в", "на", "с", "по", "из", "к", "у", "от", "за", "до", "об", "о",
    "или", "но", "что", "как", "так", "это", "тот", "те", "для", "при", "со",
    "ко", "во", "не", "же", "бы", "а", "мен", "және", "бойынша", "үшін", "бар",
}

GEOLOGY_ROOTS = {
    # скважина
    "скважины": "скважина", "скважину": "скважина", "скважин": "скважина",
    "скважиной": "скважина", "скважинах": "скважина", "скважинам": "скважина",
    "ұңғыма": "скважина", "ұңғымалар": "скважина", "ұңғыманың": "скважина",
    # пласт / горизонт
    "пласта": "пласт", "пласте": "пласт", "пластов": "пласт", "пластам": "пласт",
    "пластах": "пласт", "пластом": "пласт", "горизонта": "горизонт", "горизонте": "горизонт",
    "горизонтов": "горизонт", "горизонтам": "горизонт", "горизонтах": "горизонт",
    # запасы / дебит / интервалы
    "запасов": "запасы", "запасам": "запасы", "запасах": "запасы", "запасами": "запасы",
    "дебита": "дебит", "дебите": "дебит", "дебитом": "дебит",
    "интервала": "интервал", "интервалы": "интервал", "интервалов": "интервал",
    "глубины": "глубина", "глубине": "глубина", "глубин": "глубина",
    # свойства / литология / конструкция
    "свойства": "свойство", "свойств": "свойство", "свойствами": "свойство",
    "механические": "механический", "механических": "механический",
    "физико": "физика", "физические": "физика", "физических": "физика",
    "литологическая": "литология", "литологический": "литология", "литологию": "литология",
    "конструкции": "конструкция", "конструкцию": "конструкция", "конструкцией": "конструкция",
    # породы / коллекторы
    "породы": "порода", "породе": "порода", "породой": "порода", "пород": "порода",
    "коллектора": "коллектор", "коллекторе": "коллектор", "коллекторов": "коллектор",
    # таблицы / рисунки / карты
    "таблицы": "таблица", "таблице": "таблица", "таблицу": "таблица", "таблиц": "таблица",
    "рисунки": "рисунок", "рисунка": "рисунок", "рисунке": "рисунок", "рисунков": "рисунок",
    "рис": "рисунок", "карты": "карта", "карте": "карта", "карту": "карта", "карт": "карта",
    "схемы": "схема", "схеме": "схема", "схему": "схема", "схем": "схема",
    # казахские слова
    "кесте": "таблица", "кестелер": "таблица", "сурет": "рисунок", "суреттер": "рисунок",
    "картада": "карта", "қабат": "пласт", "қабаттар": "пласт", "қор": "запасы",
}

TABLE_FIRST_TERMS = {
    "таблица", "свойство", "физика", "механический", "литология", "конструкция",
    "интервал", "глубина", "запасы", "дебит", "плотность", "пористость", "проницаемость",
    "карбонатность", "твердость", "модуль", "пуассон", "разрез", "бурение",
}
FIGURE_TERMS = {"рисунок", "схема", "профиль", "колонка", "диаграмма", "разрез"}
MAP_TERMS = {"карта", "координата", "контур", "структурная", "изолиния", "масштаб"}


def normalize(token: str) -> str:
    lower = token.lower().replace("ё", "е")
    if lower in GEOLOGY_ROOTS:
        return GEOLOGY_ROOTS[lower]
    # Lightweight suffix stripping for Russian/Kazakh forms without heavy dependencies.
    for suffix in ("ами", "ями", "ого", "ему", "ими", "ыми", "ая", "яя", "ое", "ее", "ой", "ей", "ах", "ях", "ам", "ям", "ов", "ев", "ом", "ем", "ым", "им", "ы", "и", "а", "я", "е", "у", "ю"):
        if len(lower) > len(suffix) + 3 and lower.endswith(suffix):
            stem = lower[: -len(suffix)]
            return GEOLOGY_ROOTS.get(stem, stem)
    return lower


def tokenize(text: str) -> list[str]:
    tokens = [normalize(t) for t in TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def chunk_text(text: str, size: int = 1200, overlap: int = 180) -> list[str]:
    """Structure-preserving chunker: keeps newlines/tables/captions intact."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n")]
    clean = "\n".join(lines).strip()
    if not clean:
        return []

    # Markdown or OCR tables are kept as one block when possible.
    if _looks_like_table(clean) and len(clean) <= size * 4:
        return [clean]

    paragraphs = re.split(r"\n{2,}", clean)
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > size:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_long_block(para, size=size, overlap=overlap))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = para
    if current:
        chunks.append(current.strip())
    return chunks


def chunk_text_with_pages(text: str, size: int = 1200, overlap: int = 180) -> list[tuple[str, int | None]]:
    page_pattern = re.compile(r"\[Страница\s+(\d+)\]")
    parts = page_pattern.split(text)
    segments: list[tuple[str, int | None]] = []
    if len(parts) == 1:
        return [(c, None) for c in chunk_text(parts[0], size, overlap)]
    if parts[0].strip():
        segments.extend((c, None) for c in chunk_text(parts[0], size, overlap))
    for i in range(1, len(parts) - 1, 2):
        try:
            page = int(parts[i])
        except ValueError:
            page = None
        segments.extend((c, page) for c in chunk_text(parts[i + 1], size, overlap))
    return segments


def _looks_like_table(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pipe_rows = [l for l in lines if l.startswith("|") and l.endswith("|")]
    if len(pipe_rows) >= 2:
        return True
    multi_col = [l for l in lines if len(re.split(r"\s{2,}|\t|\|", l)) >= 3]
    return len(multi_col) >= 3


def _split_long_block(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunk = text[start:end]
        if end < len(text):
            last_break = max(chunk.rfind("\n"), chunk.rfind(". "), chunk.rfind(" "))
            if last_break > size * 0.6:
                end = start + last_break + 1
                chunk = text[start:end]
        chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [c for c in chunks if c]


def table_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
    if not columns:
        return ""
    normalized_rows = []
    width = len(columns)
    for row in rows:
        normalized_rows.append((row + [""] * width)[:width])
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in normalized_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def extract_geo_metadata(text: str) -> dict[str, list[str]]:
    patterns = {
        "wells": r"(?:скважин[аы]?|ұңғыма|№|#)\s*№?\s*([A-Za-zА-Яа-я0-9\-/]+)",
        "horizons": r"(?:горизонт|пласт|қабат)\s+([A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9\-+]+)",
        "intervals_m": r"(\d{1,5}(?:[,.]\d+)?\s*[-–—]\s*\d{1,5}(?:[,.]\d+)?\s*м)",
        "reserve_categories": r"\b(C1|C2|C3|С1|С2|С3)\b",
        "units": r"\b(?:т/сут|м3/сут|м³/сут|МПа|кг/см²|кг/см2|г/см³|г/см3|тыс\.\s*т|м)\b",
    }
    metadata: dict[str, list[str]] = {}
    for key, pattern in patterns.items():
        found = []
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            value = match if isinstance(match, str) else " ".join(match)
            value = value.strip()
            if value and value not in found:
                found.append(value)
        if found:
            metadata[key] = found[:20]
    return metadata


def classify_query(question: str) -> dict[str, object]:
    tokens = set(tokenize(question))
    q = question.lower()
    if tokens & MAP_TERMS or "карт" in q:
        route = "map-first"
        preferred = ["map", "figure", "table", "text"]
    elif (tokens & TABLE_FIRST_TERMS) or any(s in q for s in ("физико", "литолог", "проницаем", "порист", "плотност", "табл")):
        route = "table-first"
        preferred = ["table", "text", "figure", "map"]
    elif tokens & FIGURE_TERMS or "рис" in q:
        route = "figure-first"
        preferred = ["figure", "map", "table", "text"]
    else:
        route = "text-first"
        preferred = ["text", "table", "figure", "map"]
    return {"route": route, "preferred_types": preferred, "tokens": sorted(tokens)}


class LocalIndex:
    def __init__(self) -> None:
        self._artifacts: list[DocumentArtifact] = []
        self._vectors: list[Counter[str]] = []
        self._documents: dict[str, dict] = {}
        self._seeded = False

    def clear(self) -> None:
        self._artifacts.clear()
        self._vectors.clear()
        self._documents.clear()
        self._seeded = False

    def seed_demo(self) -> None:
        if self._seeded:
            return
        self._seeded = True
        for artifact in DEMO_CHUNKS:
            self._artifacts.append(artifact)
            self._vectors.append(Counter(tokenize(self._searchable_text(artifact))))
        logger.info("Demo artifacts seeded: %d", len(DEMO_CHUNKS))

    def add_document(self, filename: str, texts: list[str]) -> str:
        artifacts = [DocumentArtifact(document_name=filename, artifact_type="text", text=t) for t in texts]
        return self.add_artifacts(filename, artifacts)

    def add_document_with_pages(self, filename: str, segments: list[tuple[str, int | None]]) -> str:
        artifacts = [DocumentArtifact(document_name=filename, page=p, artifact_type="text", text=t) for t, p in segments]
        return self.add_artifacts(filename, artifacts)

    def add_artifacts(self, filename: str, artifacts: list[DocumentArtifact], document_id: str | None = None) -> str:
        if document_id is None:
            document_id = str(uuid.uuid4())
        counts = Counter(a.artifact_type for a in artifacts)
        self._documents[document_id] = {
            "id": document_id,
            "filename": filename,
            "chunks": len(artifacts),
            "artifacts": len(artifacts),
            "tables": counts.get("table", 0),
            "figures": counts.get("figure", 0),
            "maps": counts.get("map", 0),
        }
        for index, artifact in enumerate(artifacts, start=1):
            artifact.document_id = document_id
            artifact.document_name = artifact.document_name or filename
            artifact.id = artifact.id or f"{document_id}:{index}"
            artifact.metadata = {**extract_geo_metadata(self._searchable_text(artifact)), **artifact.metadata}
            self._artifacts.append(artifact)
            self._vectors.append(Counter(tokenize(self._searchable_text(artifact))))
        logger.info("Проиндексировано '%s': %d artifacts (документ %s)", filename, len(artifacts), document_id)
        return document_id

    def add_placeholder(self, filename: str, document_id: str) -> None:
        """Register a document placeholder before background processing completes."""
        self._documents[document_id] = {
            "id": document_id,
            "filename": filename,
            "chunks": 0,
            "artifacts": 0,
            "tables": 0,
            "figures": 0,
            "maps": 0,
            "processing": True,
        }

    def get_document_info(self, document_id: str) -> dict | None:
        return self._documents.get(document_id)


    def remove_document(self, document_id: str) -> bool:
        if document_id not in self._documents:
            return False
        del self._documents[document_id]
        kept_artifacts: list[DocumentArtifact] = []
        kept_vectors: list[Counter[str]] = []
        for artifact, vector in zip(self._artifacts, self._vectors):
            if artifact.document_id == document_id:
                continue
            kept_artifacts.append(artifact)
            kept_vectors.append(vector)
        self._artifacts = kept_artifacts
        self._vectors = kept_vectors
        logger.info("Документ удалён из индекса: %s", document_id)
        return True

    def list_documents(self) -> list[dict]:
        return list(self._documents.values())

    def get_artifact(self, artifact_id: str) -> DocumentArtifact | None:
        for artifact in self._artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None

    def artifacts_for_document(self, document_id: str | None = None, artifact_type: str | None = None) -> list[DocumentArtifact]:
        results: list[DocumentArtifact] = []
        for artifact in self._artifacts:
            if document_id and artifact.document_id != document_id:
                continue
            if artifact_type and artifact.artifact_type != artifact_type:
                continue
            results.append(artifact)
        return results

    def has_real_documents(self) -> bool:
        return bool(self._documents)

    def search(
        self,
        question: str,
        top_k: int = 8,
        preferred_types: list[str] | None = None,
        threshold: float = 0.05,
    ) -> list[DocumentArtifact]:
        query = Counter(tokenize(question))
        if not query:
            logger.warning("Пустой запрос после токенизации: '%s'", question)
            return []
        route = classify_query(question)
        preferred_types = preferred_types or list(route["preferred_types"])
        preferred_rank = {typ: len(preferred_types) - i for i, typ in enumerate(preferred_types)}

        has_real = self.has_real_documents()
        scored: list[tuple[float, DocumentArtifact]] = []
        for vector, artifact in zip(self._vectors, self._artifacts):
            if has_real and (artifact.id or "").startswith("demo-"):
                continue
            score = cosine(query, vector)
            score += self._type_bonus(artifact, preferred_rank)
            score += self._title_bonus(question, artifact)
            score += self._exact_phrase_bonus(question, artifact)
            if score >= threshold:
                scored.append((score, artifact))

        scored.sort(key=lambda item: item[0], reverse=True)
        grouped = self._group_by_page(scored)
        results = [artifact.model_copy(update={"score": round(min(score, 1.0), 4)}) for score, artifact in grouped[:top_k]]
        logger.info("Search '%s' -> %d artifacts via %s", question, len(results), route["route"])
        return results

    def related_artifacts(
        self,
        document_id: str | None,
        pages: Iterable[int | None],
        artifact_types: set[str],
        radius: int = 1,
        limit: int = 6,
    ) -> list[DocumentArtifact]:
        if not document_id:
            return []
        page_set = {p for p in pages if p is not None}
        results: list[DocumentArtifact] = []
        for artifact in self._artifacts:
            if artifact.document_id != document_id or artifact.artifact_type not in artifact_types:
                continue
            if page_set and artifact.page is not None and all(abs(artifact.page - p) > radius for p in page_set):
                continue
            results.append(artifact)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _searchable_text(artifact: DocumentArtifact) -> str:
        parts = [artifact.artifact_type, artifact.title or "", artifact.caption or "", artifact.text or ""]
        if artifact.columns:
            parts.append(" ".join(artifact.columns))
        if artifact.rows:
            parts.append("\n".join(" | ".join(row) for row in artifact.rows[:80]))
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _type_bonus(artifact: DocumentArtifact, preferred_rank: dict[str, int]) -> float:
        if artifact.artifact_type not in preferred_rank:
            return 0.0
        return 0.08 * preferred_rank[artifact.artifact_type]

    @staticmethod
    def _title_bonus(question: str, artifact: DocumentArtifact) -> float:
        if not artifact.title:
            return 0.0
        q_tokens = set(tokenize(question))
        title_tokens = set(tokenize(artifact.title))
        if not q_tokens:
            return 0.0
        return min(0.25, 0.05 * len(q_tokens & title_tokens))

    @staticmethod
    def _exact_phrase_bonus(question: str, artifact: DocumentArtifact) -> float:
        q = question.lower()
        hay = "\n".join([artifact.title or "", artifact.caption or "", artifact.text or ""]).lower()
        bonus = 0.0
        for phrase in ("физико-механические", "физико механические", "литологическая характеристика", "разрез скважины", "конструкция скважины"):
            if phrase in q and phrase in hay:
                bonus += 0.18
        return min(bonus, 0.35)

    @staticmethod
    def _group_by_page(scored: list[tuple[float, DocumentArtifact]]) -> list[tuple[float, DocumentArtifact]]:
        # Keep best artifacts while avoiding ten near-duplicate text chunks from one page.
        buckets: defaultdict[tuple[str | None, int | None, str], int] = defaultdict(int)
        output: list[tuple[float, DocumentArtifact]] = []
        for score, artifact in scored:
            key = (artifact.document_id, artifact.page, artifact.artifact_type)
            if buckets[key] >= (3 if artifact.artifact_type == "text" else 5):
                continue
            buckets[key] += 1
            output.append((score, artifact))
        return output


def cosine(left: Counter[str], right: Counter[str]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(v * v for v in left.values()))
    right_norm = math.sqrt(sum(v * v for v in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


DEMO_CHUNKS = [
    SourceChunk(
        id="demo-1",
        document_name="demo_report_well_12.pdf",
        document_id="demo",
        page=14,
        artifact_type="text",
        score=0.98,
        text="Скважина №12: интервал перфорации 2410-2436 м, горизонт Ю1. Дебит нефти после ГТМ составил 38,4 т/сут, обводненность 12%, пластовое давление 18,6 МПа.",
    ),
    SourceChunk(
        id="demo-2",
        document_name="demo_reserves_c1_c2.xlsx",
        document_id="demo",
        page=2,
        artifact_type="table",
        title="Демо-таблица запасов C1/C2",
        columns=["Категория", "Геологические запасы, тыс. т", "Извлекаемые запасы, тыс. т", "КИН"],
        rows=[["C1", "1 240", "428", "0,345"], ["C2", "860", "258", "0,300"]],
        text="Запасы по категории C1 и C2.",
    ),
    SourceChunk(
        id="demo-3",
        document_name="demo_horizon_yu1.docx",
        document_id="demo",
        page=7,
        artifact_type="text",
        score=0.91,
        text="Горизонт Ю1 представлен переслаиванием песчаников и алевролитов. Упоминания Ю1 связаны со скважинами №8, №12 и №19; глубины кровли 2398-2422 м.",
    ),
]


local_index = LocalIndex()

from __future__ import annotations
import re
from typing import Any
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9]+")
CONTROL_RE = re.compile(r"[\uFFFE\uFEFF\u200b\u200c\u200d￾]")
WATERMARK_WORDS = {"гу","управление","природных","ресурсов","регулирования","природопользования","акимат","актюбинской","области","тайкарова","гб"}
SHORT_FRAGS = {"гу","г","б","a","а","й","ко","нс","юб","кт","мат","лас","ласт","об","ва","ро","рордо"}
FULL_WATERMARK_RE = re.compile(r"ГУ\s*[\"“]?Управление\s+природных\s+ресурсов.*?(?:Тайкарова\s*Г\.?\s*Б\.?)?", re.I|re.S)
def clean_control_chars(value: object) -> str:
    return CONTROL_RE.sub(" ", str(value or "")).replace("\r\n","\n").replace("\r","\n")
def is_watermark_fragment_line(line: str) -> bool:
    stripped = clean_control_chars(line).strip(" .,:;—-–()[]{}\\/\t")
    if not stripped: return True
    toks=[t.lower().replace('ё','е') for t in TOKEN_RE.findall(stripped)]
    if not toks: return True
    if len(stripped)<=3 and not any(ch.isdigit() for ch in stripped): return True
    if len(toks)<=3 and all(t in SHORT_FRAGS or t in WATERMARK_WORDS or len(t)<=2 for t in toks): return True
    if len(toks)<=5 and sum(1 for t in toks if t in WATERMARK_WORDS)>=2: return True
    return False
def remove_watermark_fragments(text: str) -> str:
    text=FULL_WATERMARK_RE.sub(" ", clean_control_chars(text))
    text=re.sub(r"\b(?:ГУ|Акимат)\b[^\n]{0,160}\b(?:области|Тайкарова)\b", " ", text, flags=re.I)
    out=[]
    for raw in text.split('\n'):
        line=re.sub(r"[ \t]+"," ",raw).strip()
        if is_watermark_fragment_line(line): continue
        line=strip_intrusive_ocr_noise(line)
        if not line: continue
        out.append(line)
    return "\n".join(out).strip()
def normalize_pdf_prose(text: str) -> str:
    text=remove_watermark_fragments(text)
    if not text: return ""
    lines=[re.sub(r"[ \t]+"," ",l).strip() for l in text.split('\n')]
    out=[]; buf=""
    def flush():
        nonlocal buf
        if buf.strip(): out.append(buf.strip())
        buf=""
    for line in lines:
        if not line: flush(); continue
        is_tableish=line.startswith('|') or len(re.split(r"\s{2,}|\t|\|", line))>=4
        is_caption=re.match(r"^(Таблица|Рис\.|Рисунок|Карта|Схема)\b", line, re.I)
        is_heading=re.match(r"^\d+(?:\.\d+)*\.?\s+[А-ЯA-ZЁ]", line) or re.match(r"^[А-ЯA-ZЁ][А-ЯA-ZЁ\s\-]{8,}$", line)
        if is_tableish or is_caption or is_heading:
            flush(); out.append(line); continue
        if buf: buf = re.sub(r"[-–—]$", "", buf)+line if re.search(r"[-–—]$", buf) else buf+" "+line
        else: buf=line
    flush(); return "\n".join(out).strip()
def compact_spaces(value: object) -> str:
    return re.sub(r"\s+"," ",clean_control_chars(value)).strip()

GENERIC_BROKEN_TOKENS = {
    "рсо", "рясу", "роду", "роре", "рск", "нле", "нлеа", "оа", "жк", "нт",
    "туа", "шк", "скр", "сси", "исти", "обрл", "верзне", "саксарские",
}

GEOLOGY_COMMON_WORDS = {
    "ярус", "система", "отдел", "пласт", "горизонт", "свита", "разрез", "скважина",
    "породы", "отложения", "известняки", "песчаники", "аргиллиты", "алевролиты",
    "кровля", "подошва", "толщина", "мощность", "глубина", "метров", "представлен",
}

def intrusive_noise_score(value: str) -> float:
    """Score PDF watermark/diagonal-text contamination inside otherwise normal prose.

    The Kargaly PDF has a diagonal state watermark. Some text layers inject its
    letters into paragraphs and tables as fragments such as "р о", "н с", "ОА",
    "шК". We use a conservative score: a normal geological sentence with a few
    short words is fine, but many isolated letters / watermark fragments mark the
    sentence or table cell as unsafe to display as factual data.
    """
    text = compact_spaces(value)
    if not text:
        return 0.0
    tokens = TOKEN_RE.findall(text)
    if not tokens:
        return 0.0
    norm = [t.lower().replace("ё", "е") for t in tokens]
    allowed_single = {"и", "в", "с", "к", "о", "у", "а"}
    isolated = sum(1 for t in norm if len(t) == 1 and not t.isdigit() and t not in allowed_single)
    watermark_hits = sum(1 for t in norm if t in WATERMARK_WORDS)
    watermark_noise = watermark_hits if watermark_hits >= 2 else 0
    short_noise = sum(1 for t in norm if t in SHORT_FRAGS or t in GENERIC_BROKEN_TOKENS) + watermark_noise
    mixed_case = sum(1 for t in tokens if any(ch.isupper() for ch in t[1:]))
    repeated_single = len(re.findall(r"(?:\b[А-Яа-яA-Za-z]\b\s*){3,}", text))
    return (isolated * 1.25 + short_noise + mixed_case * 1.5 + repeated_single * 4) / max(len(tokens), 1)

def looks_like_intrusive_noise(value: str, threshold: float = 0.18) -> bool:
    text = compact_spaces(value)
    if not text:
        return False
    if len(text) <= 3 and not re.search(r"\d", text):
        return True
    return intrusive_noise_score(text) >= threshold

def strip_intrusive_ocr_noise(value: str) -> str:
    """Remove obvious watermark fragments from a single line/cell without rewriting facts."""
    text = compact_spaces(value)
    if not text:
        return ""
    has_repeated_single_run = bool(re.search(r"(?:\b[А-Яа-яA-Za-z]\b\s*){3,}", text))
    severe_noise = has_repeated_single_run or intrusive_noise_score(text) >= 0.18
    if not severe_noise:
        return text
    text = re.sub(r"(?:\b[А-Яа-яA-Za-z]\b\s*){3,}", " ", text)
    words = []
    for token in text.split():
        clean = token.strip(".,:;()[]{}\\/—–-")
        norm = clean.lower().replace("ё", "е")
        if len(clean) == 1 and clean.isalpha() and norm not in {"и", "в", "с", "к", "о", "у", "а"}:
            continue
        if norm in SHORT_FRAGS or norm in WATERMARK_WORDS or norm in GENERIC_BROKEN_TOKENS:
            continue
        words.append(token)
    cleaned = re.sub(r"\s+", " ", " ".join(words)).strip()
    # If cleanup left only garbage, do not show it.
    if cleaned and looks_like_intrusive_noise(cleaned, threshold=0.34) and not re.search(r"\d", cleaned):
        return ""
    return cleaned

def clean_cell_text(value: object) -> str:
    text=compact_spaces(value)
    if text and is_watermark_fragment_line(text) and not re.search(r"\d", text): return ""
    return strip_intrusive_ocr_noise(text)
def noisy_text_score(value: str) -> float:
    text=compact_spaces(value); toks=[t.lower().replace('ё','е') for t in TOKEN_RE.findall(text)]
    if not toks: return 0.0
    broken=len(re.findall(r"\b[А-Яа-яA-Za-z]\b", text)); wm=sum(1 for t in toks if t in WATERMARK_WORDS or t in SHORT_FRAGS)
    return (broken+wm)/max(len(toks),1)
def looks_like_noisy_text(value: str, threshold: float=0.22) -> bool:
    return noisy_text_score(value)>=threshold
def clean_generated_answer(text: str) -> str:
    raw = clean_control_chars(text)
    raw = re.sub(r"(?im)^\s*#{1,4}\s*Краткий\s+вывод\s*$", "", raw)
    raw = re.sub(r"(?i)^\s*Краткий\s+вывод\s*[-—:]*\s*", "", raw.strip())
    raw = re.sub(r"\.{3,}|…", ". ", raw)
    raw = re.sub(r"\s*(#{2,4}\s+)", r"\n\n\1", raw)
    lines=[]
    for raw_line in raw.split('\n'):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            lines.append("")
            continue
        prefix = ""
        body = line
        if line.startswith(("- ", "* ")):
            prefix, body = line[:2], line[2:].strip()
        elif re.match(r"^#{1,4}\s+", line):
            prefix, body = re.match(r"^(#{1,4}\s+)(.*)$", line).groups()  # type: ignore[union-attr]
        body = strip_intrusive_ocr_noise(body)
        if body and (looks_like_noisy_text(body,0.34) or looks_like_intrusive_noise(body,0.30)):
            continue
        if body:
            lines.append(prefix + body)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned

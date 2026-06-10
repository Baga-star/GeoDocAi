import React, { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  BookOpen,
  BrainCircuit,
  FileText,
  Image as ImageIcon,
  Map as MapIcon,
  Search,
  Send,
  Table2,
  Trash2,
  UploadCloud,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { TrajectoryModeSwitch } from './features/trajectory/TrajectoryModeSwitch';
import { TrajectoryWorkspace } from './features/trajectory/TrajectoryWorkspace';
import type { AppMode } from './features/trajectory/types';
import './styles.css';

type ArtifactType = 'text' | 'table' | 'figure' | 'map';
type AnswerType = 'table' | 'text' | 'figure' | 'map' | 'mixed' | 'not_found';
type Confidence = 'high' | 'medium' | 'low';
type TabId = 'answer' | 'tables' | 'visuals' | 'sources';

type SourceChunk = {
  id?: string;
  document_id?: string;
  document_name?: string;
  page?: number;
  score?: number;
  artifact_type?: ArtifactType;
  title?: string;
  caption?: string;
  text: string;
  columns?: string[];
  rows?: string[][];
  units?: string[];
  metadata?: Record<string, unknown>;
};

type ChatApiResponse = {
  answer_type: AnswerType;
  answer_markdown: string;
  answer?: string;
  tables: SourceChunk[];
  figures: SourceChunk[];
  maps: SourceChunk[];
  sources: SourceChunk[];
  used_demo_mode: boolean;
  confidence: Confidence;
  missing_data: string[];
};

type Message = {
  role: 'user' | 'assistant';
  text: string;
  answerType?: AnswerType;
  confidence?: Confidence;
  missingData?: string[];
  tables?: SourceChunk[];
  figures?: SourceChunk[];
  maps?: SourceChunk[];
  sources?: SourceChunk[];
  demo?: boolean;
  requestedSources?: boolean;
};

type DocInfo = { id: string; filename: string; chunks: number; artifacts?: number; tables?: number; figures?: number; maps?: number };
type UploadState = 'idle' | 'uploading' | 'success' | 'error';
type BackendStatus = 'checking' | 'online' | 'offline';

const configuredApiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
const browserHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const sameHostApiBase = typeof window !== 'undefined' ? `http://${browserHost}:8001/api` : 'http://localhost:8001/api';
const API_CANDIDATES = Array.from(new Set([
  configuredApiBase,
  sameHostApiBase,
  'http://localhost:8001/api',
  'http://127.0.0.1:8001/api',
  import.meta.env.DEV ? undefined : '/api',
].filter(Boolean) as string[]));
let activeApiBase = API_CANDIDATES[0] || 'http://localhost:8001/api';
const configuredApiKey = (import.meta.env.VITE_API_KEY as string | undefined)?.trim();

const ACCEPTED_FILE_TYPES = '.pdf,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.webp';

function withAuth(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  if (configuredApiKey) headers.set('X-API-Key', configuredApiKey);
  return { ...init, headers };
}

function apiUrl(path: string, base = activeApiBase): string {
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

async function fetchJson<T>(pathOrUrl: string, init?: RequestInit): Promise<T> {
  const isAbsolute = /^https?:\/\//i.test(pathOrUrl) || pathOrUrl.startsWith('/api');
  const candidates = isAbsolute ? [pathOrUrl] : API_CANDIDATES.map(base => apiUrl(pathOrUrl, base));
  let lastError: unknown;
  for (const url of candidates) {
    try {
      const res = await fetch(url, withAuth(init));
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      activeApiBase = url.replace(/\/[^/]*$/, '').replace(/\/documents$/, '').replace(/\/chat$/, '').replace(/\/health$/, '').replace(/\/capabilities$/, '');
      return res.json() as Promise<T>;
    } catch (err) {
      lastError = err;
    }
  }
  const details = lastError instanceof Error ? lastError.message : 'network error';
  throw new Error(`Backend недоступен: ${details}`);
}

// ── Text helpers ──────────────────────────────────────────────────────────────

const WATERMARK_WORDS = new Set(['гу', 'управление', 'природных', 'ресурсов', 'регулирования', 'природопользования', 'акимат', 'актюбинской', 'области', 'тайкарова']);
const SHORT_WATERMARK_FRAGMENTS = new Set(['гу', 'г', 'б', 'a', 'а', 'й', 'ко', 'нс', 'юб', 'кт', 'мат', 'лас', 'ласт', 'об', 'ва', 'ро', 'рордо']);

function isWatermarkFragmentLine(line: string): boolean {
  const stripped = String(line || '').replace(/[\uFFFE￾]/g, ' ').trim().replace(/[.,:;—–()\[\]{}\\/\\]/g, '').trim();
  if (!stripped) return true;
  const tokens = stripped.match(/[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9]+/g)?.map(t => t.toLowerCase().replace('ё', 'е')) || [];
  if (!tokens.length) return true;
  if (stripped.length <= 3 && !/\d/.test(stripped)) return true;
  if (tokens.length <= 3 && tokens.every(t => SHORT_WATERMARK_FRAGMENTS.has(t) || WATERMARK_WORDS.has(t) || t.length <= 2)) return true;
  if (tokens.length <= 5 && tokens.filter(t => WATERMARK_WORDS.has(t)).length >= 2) return true;
  return false;
}

function cleanUiText(value: string | undefined | null): string {
  const raw = String(value || '').replace(/[\uFFFE\uFEFF\u200b\u200c\u200d￾]/g, ' ').replace(/\r\n?/g, '\n').replace(/ГУ\s*[""]?Управление\s+природных\s+ресурсов[^\n]*/gi, ' ');
  const lines = raw.split('\n').map(line => line.replace(/[ \t]+/g, ' ').trim());
  const out: string[] = [];
  let buffer = '';
  const flush = () => { if (buffer.trim()) out.push(buffer.trim()); buffer = ''; };
  for (const line of lines) {
    if (!line || isWatermarkFragmentLine(line)) { flush(); continue; }
    const isTable = line.startsWith('|');
    const isCaption = /^(Таблица|Рис\.|Рисунок|Карта|Схема)\b/i.test(line);
    const isHeading = /^\d+(\.\d+)*\.?\s+[А-ЯA-ZЁ]/.test(line) || /^[А-ЯA-ZЁ][А-ЯA-ZЁ\s\-]{8,}$/.test(line);
    if (isTable || isCaption || isHeading) { flush(); out.push(line); continue; }
    if (buffer) buffer = /[-–—]$/.test(buffer) ? buffer.replace(/[-–—]$/, '') + line : `${buffer} ${line}`;
    else buffer = line;
  }
  flush();
  return out.join('\n\n');
}

function compact(value: string | undefined | null, max = 140): string {
  const text = cleanUiText(value).replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max - 1).trim()}…` : text;
}

function normalizePlainTextForDisplay(value: string | undefined | null): string {
  return cleanUiText(value);
}

function noisyTextScore(value: string | undefined | null): number {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  const tokens = text.match(/[A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі0-9]+/g)?.map(t => t.toLowerCase().replace('ё', 'е')) || [];
  if (!tokens.length) return 0;
  const broken = (text.match(/\b[А-Яа-яA-Za-z]\b/g) || []).length;
  const watermark = tokens.filter(t => WATERMARK_WORDS.has(t) || SHORT_WATERMARK_FRAGMENTS.has(t)).length;
  return (broken + watermark) / Math.max(tokens.length, 1);
}

function isNoisyCell(value: string | undefined | null): boolean {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return false;
  const isolatedLetters = (text.match(/\b[А-Яа-яA-Za-z]\b/g) || []).length;
  const repeatedSingleRuns = (text.match(/(?:\b[А-Яа-яA-Za-z]\b\s*){3,}/g) || []).length;
  const badTokens = /\b(рсо|рясу|роду|роре|нлеа|скр|оа|жк|нт|туа|шк)\w*\b/i.test(text);
  return (text.length > 6 && noisyTextScore(text) > 0.16) || isolatedLetters >= 2 || repeatedSingleRuns > 0 || badTokens;
}

function isNoisyTable(columns: string[], rows: string[][]): boolean {
  const cells = [...columns, ...rows.slice(0, 12).flat()].filter(Boolean);
  if (cells.length < 4) return false;
  const noisy = cells.filter(cell => isNoisyCell(cell)).length;
  return noisy / cells.length > 0.10;
}

function userRequestedSources(question: string): boolean {
  const q = question.toLowerCase().replace(/ё/g, 'е');
  return ['источник', 'источники', 'страница', 'страницы', 'откуда', 'доказательства', 'source', 'sources'].some(term => q.includes(term));
}

function stripEvidenceSections(markdown: string): string {
  let text = String(markdown || '').replace(/\s*(#{2,4}\s+)/g, '\n\n$1');
  text = text.replace(/\n?#{2,4}\s*(Связанная\s+таблица|Рисунки\s*\/\s*схемы\s+рядом|Рисунки\s+рядом|Карты\s+рядом|Источник|Источники)\b[\s\S]*?(?=\n#{2,4}\s+|$)/gi, '');
  text = text.replace(/\s*#{2,4}\s*(Связанная\s+таблица|Рисунки\s*\/\s*схемы\s+рядом|Источник|Источники)\b[\s\S]*$/gi, '');
  return text.trim();
}

function answerMarkdownForDisplay(message?: Message): string {
  const cleaned = cleanUiText(message?.text || '');
  return message?.requestedSources ? cleaned : stripEvidenceSections(cleaned);
}

function displayCell(value: string | undefined | null): string {
  const text = cleanUiText(value).replace(/\s+/g, ' ').trim();
  return isNoisyCell(text) ? '—' : text;
}

function cleanVisualTitle(value: string | undefined | null, fallback = 'Карта'): string {
  const raw = String(value || '').replace(/\s+/g, ' ').trim();
  if (!raw) return fallback;
  const low = raw.toLowerCase().replace('ё', 'е');
  const bad = ['визуальным признакам', 'даже если vision', 'vision-модель', 'local mapreader classifier', 'страница определена как карта', 'желтая заливка', 'зеленая заливка', 'образует основную', 'площадную зону', 'видны синие', 'видны красные', 'похожие на'];
  if (bad.some(token => low.includes(token))) return fallback;
  if (low.startsWith('карта:') && !/(структур|кровл|подошв|месторожд|рисунок)/.test(low)) return fallback;
  if (['карта', 'рисунок', 'figure', 'map', 'контурной/структурной карты'].includes(low)) return fallback;
  return raw.length > 110 ? `${raw.slice(0, 109).trim()}…` : raw;
}

function visualReadingLines(item: SourceChunk): string[] {
  const metadata = item.metadata || {};
  const payload = metadata.visual_analysis as Record<string, unknown> | undefined;
  const local = metadata.local_map_reading as Record<string, unknown> | undefined;
  const addFrom = (value: unknown, limit = 6): string[] => {
    const arr = Array.isArray(value) ? value : value ? [value] : [];
    return arr.slice(0, limit).map((entry) => {
      if (entry && typeof entry === 'object') {
        const obj = entry as Record<string, unknown>;
        const parts = ['label', 'id', 'symbol', 'style', 'meaning', 'relative_position'].map(key => obj[key]).filter(val => val !== undefined && val !== null && val !== '').map(String);
        return parts.join(' — ');
      }
      return String(entry || '');
    }).map(text => text.replace(/\s+/g, ' ').trim()).filter(Boolean);
  };
  const lines = [...addFrom(payload?.interpretation, 6), ...addFrom(local?.interpretation, 6), ...addFrom(payload?.legend, 4), ...addFrom(local?.legend, 4), ...addFrom(payload?.contours, 3), ...addFrom(local?.contours, 3), ...addFrom(payload?.wells, 3), ...addFrom(local?.wells, 3)];
  const seen = new Set<string>();
  return lines.filter((line) => {
    const cleaned = cleanVisualTitle(line, line).replace(/^карта:?\s*/i, '').trim();
    const low = cleaned.toLowerCase().replace('ё', 'е');
    if (!cleaned || low.includes('vision-модель') || low.includes('визуальным признакам')) return false;
    if (seen.has(low)) return false;
    seen.add(low);
    return true;
  }).slice(0, 7);
}

function artifactLabel(type?: ArtifactType): string {
  if (type === 'table') return 'Таблица';
  if (type === 'figure') return 'Рисунок';
  if (type === 'map') return 'Карта';
  return 'Текст';
}

function sourceLocation(item: SourceChunk): string {
  const name = item.document_name || 'Документ';
  const page = item.page ? `стр. ${item.page}` : 'страница не указана';
  return `${name}, ${page}`;
}

function titleOf(item: SourceChunk, fallback = 'Источник'): string {
  const raw = item.title || item.caption || item.document_name || fallback;
  return item.artifact_type === 'map' || item.artifact_type === 'figure'
    ? cleanVisualTitle(raw, item.artifact_type === 'map' ? 'Структурная карта по кровле пласта' : fallback)
    : raw;
}

function iconFor(type?: ArtifactType, size = 16) {
  if (type === 'table') return <Table2 size={size} />;
  if (type === 'figure') return <ImageIcon size={size} />;
  if (type === 'map') return <MapIcon size={size} />;
  return <FileText size={size} />;
}

function previewUrl(item?: SourceChunk): string | undefined {
  const value = item?.metadata?.preview_data_url;
  return typeof value === 'string' && value.startsWith('data:image/') ? value : undefined;
}

function getRows(item?: SourceChunk): { columns: string[]; rows: string[][] } {
  if (!item) return { columns: [], rows: [] };
  if (item.columns?.length) return { columns: item.columns, rows: item.rows || [] };
  const lines = (item.text || '').split('\n').map(line => line.trim()).filter(Boolean);
  const tableLines = lines.filter(line => line.startsWith('|') && line.endsWith('|'));
  if (tableLines.length >= 2) {
    const rows = tableLines.filter(line => !line.match(/^\|[-| :]+\|$/)).map(line => line.split('|').slice(1, -1).map(cell => cell.trim()));
    return { columns: rows[0] || [], rows: rows.slice(1) };
  }
  return { columns: [], rows: [] };
}

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;
  const inline = (value: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    const regex = /\*\*(.+?)\*\*|`(.+?)`/g;
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(value)) !== null) {
      if (match.index > last) parts.push(value.slice(last, match.index));
      if (match[1]) parts.push(<strong key={match.index}>{match[1]}</strong>);
      if (match[2]) parts.push(<code key={match.index}>{match[2]}</code>);
      last = match.index + match[0].length;
    }
    if (last < value.length) parts.push(value.slice(last));
    return parts;
  };
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && i + 1 < lines.length && lines[i + 1].trim().match(/^\|[-| :]+\|$/)) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) { tableLines.push(lines[i]); i += 1; }
      const headers = tableLines[0].split('|').slice(1, -1).map(cell => cell.trim());
      const rows = tableLines.slice(2).map(row => row.split('|').slice(1, -1).map(cell => cell.trim()));
      nodes.push(<div className="table-scroll" key={`table-${i}`}><table><thead><tr>{headers.map((h, idx) => <th key={idx}>{inline(h)}</th>)}</tr></thead><tbody>{rows.map((row, ri) => <tr key={ri}>{headers.map((_, ci) => <td key={ci}>{inline(row[ci] || '')}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (trimmed.match(/^[-*] /)) {
      const start = i;
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().match(/^[-*] /)) { items.push(lines[i].trim().replace(/^[-*] /, '')); i += 1; }
      nodes.push(<ul key={`ul-${start}`}>{items.map((item, idx) => <li key={idx}>{inline(item)}</li>)}</ul>);
      continue;
    }
    if (!trimmed) nodes.push(<div className="md-gap" key={i} />);
    else if (trimmed.startsWith('### ')) nodes.push(<h4 key={i}>{inline(trimmed.slice(4))}</h4>);
    else if (trimmed.startsWith('## ')) nodes.push(<h3 key={i}>{inline(trimmed.slice(3))}</h3>);
    else if (trimmed.startsWith('# ')) nodes.push(<h2 key={i}>{inline(trimmed.slice(2))}</h2>);
    else nodes.push(<p key={i}>{inline(trimmed)}</p>);
    i += 1;
  }
  return nodes;
}

// ── Logo SVG (matches the teal contour-line logo) ────────────────────────────
function GeoDocLogo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="brand-logo">
      <path d="M10 75 C25 40 40 20 60 18 C80 16 95 40 110 75" stroke="url(#g1)" strokeWidth="6" strokeLinecap="round" fill="none"/>
      <path d="M20 75 C33 50 46 35 60 33 C74 31 87 50 100 75" stroke="url(#g1)" strokeWidth="5" strokeLinecap="round" fill="none" opacity="0.7"/>
      <path d="M32 75 C42 58 51 48 60 47 C69 46 78 58 88 75" stroke="url(#g1)" strokeWidth="4" strokeLinecap="round" fill="none" opacity="0.5"/>
      <circle cx="85" cy="38" r="9" stroke="url(#g1)" strokeWidth="5" fill="none"/>
      <defs>
        <linearGradient id="g1" x1="10" y1="75" x2="110" y2="18" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0d9488"/>
          <stop offset="100%" stopColor="#2dd4bf"/>
        </linearGradient>
      </defs>
    </svg>
  );
}

// ── Upload box ────────────────────────────────────────────────────────────────
function UploadBox({ state, message, onUpload }: { state: UploadState; message: string; onUpload: (file?: File) => void }) {
  return (
    <label className={`upload-box ${state}`}>
      <UploadCloud size={20} />
      <span>
        <strong>{state === 'uploading' ? 'Идёт обработка…' : 'Загрузить документ'}</strong>
        <small>{message}</small>
      </span>
      <input type="file" accept={ACCEPTED_FILE_TYPES} onChange={event => onUpload(event.target.files?.[0])} />
    </label>
  );
}

// ── Welcome screen ────────────────────────────────────────────────────────────
function WelcomeScreen() {
  return (
    <div className="welcome-screen">
      <GeoDocLogo size={72} />
      <div className="welcome-title">GeoDoc AI</div>
      <div className="welcome-sub">Загрузите геологический документ в левой панели — PDF, DOCX, Excel или скан. Затем задайте вопрос о картах, таблицах, пластах или скважинах.</div>
    </div>
  );
}

// ── AI message bubble with tabs ───────────────────────────────────────────────
function AiBubble({ message }: { message: Message }) {
  const [tab, setTab] = useState<TabId>('answer');
  const tableCount = message.tables?.length || 0;
  const visualCount = (message.maps?.length || 0) + (message.figures?.length || 0);
  const sourceCount = message.sources?.length || 0;
  return (
    <div className="ai-bubble">
      <div className="ai-bubble-tabs">
        <button type="button" className={tab === 'answer' ? 'active' : ''} onClick={() => setTab('answer')}>Ответ</button>
        {tableCount > 0 && <button type="button" className={tab === 'tables' ? 'active' : ''} onClick={() => setTab('tables')}>Таблицы <span className="tab-count">{tableCount}</span></button>}
        <button type="button" className={tab === 'visuals' ? 'active' : ''} onClick={() => setTab('visuals')}>Карты и рисунки <span className="tab-count">{visualCount}</span></button>
        {sourceCount > 0 && <button type="button" className={tab === 'sources' ? 'active' : ''} onClick={() => setTab('sources')}>Источники <span className="tab-count">{sourceCount}</span></button>}
      </div>
      <div className="ai-bubble-body">
        {tab === 'answer' && <AnswerContent message={message} />}
        {tab === 'tables' && <TableView tables={message.tables} />}
        {tab === 'visuals' && <VisualView maps={message.maps} figures={message.figures} />}
        {tab === 'sources' && <SourcesView sources={message.sources} />}
      </div>
    </div>
  );
}

function AnswerContent({ message }: { message: Message }) {
  return (
    <>
      <div className="markdown-body">{renderMarkdown(answerMarkdownForDisplay(message))}</div>
      {!!message.missingData?.length && (
        <div className="missing-box">
          <strong>Что ограничивает ответ</strong>
          <ul>{message.missingData.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      )}
      {message.demo && <div className="missing-box warning"><strong>Demo mode</strong><p>Ответ на демонстрационных данных. Загрузите документ для реального анализа.</p></div>}
    </>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="message-row">
      <div className="message-avatar ai-av"><GeoDocLogo size={18} /></div>
      <div className="message-bubble">
        <div className="ai-bubble" style={{ border: '1px solid var(--line)', background: 'var(--panel)', borderRadius: '4px 16px 16px 16px', padding: '14px 16px' }}>
          <div className="typing-dots"><span /><span /><span /></div>
        </div>
      </div>
    </div>
  );
}

// ── Table view ────────────────────────────────────────────────────────────────
function TableView({ tables }: { tables?: SourceChunk[] }) {
  if (!tables?.length) return <EmptyTab icon={<Table2 size={20} />} title="Таблицы не найдены" text="Задайте вопрос про глубины, интервалы, свойства пород или пласты." />;
  return (
    <div className="stack">
      {tables.slice(0, 4).map((table, index) => {
        const { columns, rows } = getRows(table);
        const noisy = isNoisyTable(columns, rows) || table.metadata?.extraction_warning === 'noisy_pdf_table_hidden';
        return (
          <article className="data-card" key={table.id || index}>
            <header>
              <span><Table2 size={14} />Таблица</span>
              <strong>{titleOf(table, `Таблица ${index + 1}`)}</strong>
              <small>{sourceLocation(table)}</small>
            </header>
            <div style={{ padding: '12px' }}>
              {columns.length && !noisy ? (
                <div className="table-scroll"><table><thead><tr>{columns.map((column, ci) => <th key={ci}>{displayCell(column)}</th>)}</tr></thead><tbody>{rows.map((row, ri) => <tr key={ri}>{columns.map((_, ci) => <td key={ci}>{displayCell(row[ci])}</td>)}</tr>)}</tbody></table></div>
              ) : columns.length && noisy ? (
                <div className="missing-box warning"><strong>Таблица извлечена с искажениями</strong><p>Используйте карточку как ссылку на страницу: {sourceLocation(table)}.</p></div>
              ) : <p className="muted">Структурированные строки не извлечены.</p>}
            </div>
          </article>
        );
      })}
    </div>
  );
}

// ── Visual view ───────────────────────────────────────────────────────────────
function VisualView({ maps, figures }: { maps?: SourceChunk[]; figures?: SourceChunk[] }) {
  const visuals = [...(maps || []), ...(figures || [])];
  if (!visuals.length) return <EmptyTab icon={<ImageIcon size={20} />} title="Визуальные артефакты не найдены" text="Попробуйте запросить карту, разрез, рисунок или схему." />;
  return (
    <div className="visual-grid">
      {visuals.map((item, index) => <VisualCard key={item.id || index} item={item} />)}
    </div>
  );
}

function VisualCard({ item }: { item: SourceChunk }) {
  const image = previewUrl(item);
  const payload = item.metadata?.visual_analysis as Record<string, unknown> | undefined;
  const local = item.metadata?.local_map_reading as Record<string, unknown> | undefined;
  const title = titleOf(item, item.artifact_type === 'map' ? 'Структурная карта по кровле пласта' : artifactLabel(item.artifact_type));
  const visibleText = Array.isArray(payload?.visible_text) ? payload.visible_text.map(String).slice(0, 8) : [];
  const reading = visualReadingLines(item);
  const rawSummary = typeof payload?.summary === 'string' ? payload.summary : typeof local?.summary === 'string' ? local.summary : item.text;
  const summary = cleanVisualTitle(rawSummary, '').replace(/^карта:?\s*/i, '').trim();
  const [reindexing, setReindexing] = useState(false);
  const [reindexMessage, setReindexMessage] = useState<string | null>(null);

  const reindex = async () => {
    if (!item.document_id || reindexing) return;
    setReindexing(true);
    setReindexMessage(null);
    try {
      const result = await fetchJson<{ message?: string }>(`/documents/${encodeURIComponent(item.document_id)}/reindex`, { method: 'POST' });
      setReindexMessage(result.message || 'Переиндексация запущена. После завершения задайте вопрос ещё раз.');
    } catch (err) {
      setReindexMessage(err instanceof Error ? err.message : 'Не удалось запустить переиндексацию');
    } finally {
      setReindexing(false);
    }
  };

  return (
    <article className="visual-card">
      <div className="visual-preview">
        {image ? (
          <img src={image} alt={title} />
        ) : (
          <div className="visual-fallback">
            <ImageIcon size={34} />
            <strong>Изображение найдено, но preview не создан.</strong>
            <p>Переиндексируйте документ с включённым Vision/OCR.</p>
            <button type="button" onClick={reindex} disabled={!item.document_id || reindexing}>
              {reindexing ? 'Переиндексация…' : 'Переиндексировать с Vision/OCR'}
            </button>
          </div>
        )}
      </div>
      <div className="visual-info">
        <span>{iconFor(item.artifact_type, 12)}{artifactLabel(item.artifact_type)}</span>
        <h3 title={title}>{title}</h3>
        <small>{sourceLocation(item)}</small>
        {reading.length ? (
          <div className="map-reading">
            <strong>Что прочитал MapReader</strong>
            <ul>{reading.map(line => <li key={line}>{line}</li>)}</ul>
          </div>
        ) : summary ? <p>{compact(summary, 300)}</p> : null}
        {!!visibleText.length && <div className="chip-row">{visibleText.map(text => <em key={text}>{text}</em>)}</div>}
        {reindexMessage && <p className="reindex-note">{reindexMessage}</p>}
      </div>
    </article>
  );
}

// ── Sources view ──────────────────────────────────────────────────────────────
function SourcesView({ sources }: { sources?: SourceChunk[] }) {
  if (!sources?.length) return <EmptyTab icon={<BookOpen size={20} />} title="Источники не выбраны" text="После вопроса здесь появятся страницы и фрагменты, на которых основан ответ." />;
  return (
    <div className="stack">
      {sources.slice(0, 10).map((source, index) => <SourceDisclosure key={source.id || index} source={source} index={index} />)}
    </div>
  );
}

function SourceDisclosure({ source, index }: { source: SourceChunk; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const { columns, rows } = getRows(source);
  const noisy = isNoisyTable(columns, rows);
  const extractionWarning = source.metadata?.extraction_warning === 'noisy_pdf_table_hidden';
  const noisyText = isNoisyCell(source.text || source.caption || '');
  const canTable = (source.artifact_type === 'table' || columns.length > 0) && columns.length > 0 && !noisy && !extractionWarning;
  return (
    <article className="source-item">
      <button type="button" onClick={() => setOpen(v => !v)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {iconFor(source.artifact_type, 14)}
        <span><strong>{titleOf(source, `Источник ${index + 1}`)}</strong><small> · {sourceLocation(source)}</small></span>
      </button>
      {open && (
        <div className="source-body">
          {canTable ? (
            <div className="table-scroll compact"><table><thead><tr>{columns.map((column, ci) => <th key={ci}>{displayCell(column)}</th>)}</tr></thead><tbody>{rows.map((row, ri) => <tr key={ri}>{columns.map((_, ci) => <td key={ci}>{displayCell(row[ci])}</td>)}</tr>)}</tbody></table></div>
          ) : noisy || extractionWarning ? (
            <div className="missing-box warning"><strong>Повреждённая таблица</strong><p>Откройте страницу документа: {sourceLocation(source)}.</p></div>
          ) : noisyText ? (
            <div className="missing-box warning"><strong>Текст повреждён</strong><p>Используйте карточку как указатель на страницу: {sourceLocation(source)}.</p></div>
          ) : <div className="markdown-body small">{renderMarkdown(normalizePlainTextForDisplay(source.text || source.caption || source.title || ''))}</div>}
        </div>
      )}
    </article>
  );
}

function EmptyTab({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="empty-tab">{icon}<strong>{title}</strong><p>{text}</p></div>;
}

// ── Question bar ──────────────────────────────────────────────────────────────
function QuestionBar({ value, setValue, ask, loading }: { value: string; setValue: (value: string) => void; ask: (question: string) => void; loading: boolean }) {
  const submit = (event: FormEvent) => { event.preventDefault(); ask(value); };
  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
  };
  return (
    <div className="question-bar-wrap">
      <form className="question-bar" onSubmit={submit}>
        <Search size={16} />
        <input value={value} onChange={event => setValue(event.target.value)} onKeyDown={handleKeyDown} placeholder="Спросите по документу: карта, таблицы, пласты, скважины…" disabled={loading} />
        <button type="submit" disabled={loading || !value.trim()}>{loading ? <BrainCircuit size={16} /> : <Send size={16} />}</button>
      </form>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  const [mode, setMode] = useState<AppMode>('documents');
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [documents, setDocuments] = useState<DocInfo[]>([]);
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [uploadMsg, setUploadMsg] = useState('PDF, DOCX, Excel, CSV, изображения и сканы');
  const [isAsking, setIsAsking] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  const loadDocs = useCallback(async () => {
    try {
      const data = await fetchJson<{ documents: DocInfo[] }>('/documents/list');
      setDocuments(data.documents || []);
    } catch { /* keep UI usable offline */ }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try { await fetchJson<unknown>('/capabilities'); } catch { try { await fetchJson('/health'); } catch { /* offline */ } }
      if (!cancelled) { /* status checked */ }
    };
    check();
    loadDocs();
    const timer = window.setInterval(check, 15000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [loadDocs]);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, isAsking]);

  const ask = useCallback(async (raw: string) => {
    const clean = raw.trim();
    if (!clean || isAsking) return;
    setQuestion('');
    setIsAsking(true);
    const requestedSources = userRequestedSources(clean);
    setMessages(prev => [...prev, { role: 'user', text: clean }]);
    try {
      const data = await fetchJson<ChatApiResponse>('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: clean, language: 'ru', top_k: 8 }),
      });
      const next: Message = {
        role: 'assistant',
        text: data.answer_markdown || data.answer || 'Ответ сформирован по найденным источникам.',
        answerType: data.answer_type,
        confidence: data.confidence,
        missingData: data.missing_data,
        tables: data.tables || [],
        figures: data.figures || [],
        maps: data.maps || [],
        sources: data.sources || [],
        demo: data.used_demo_mode,
        requestedSources,
      };
      setMessages(prev => [...prev, next]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Неизвестная ошибка';
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: `### Backend недоступен\n${msg}\n\nЗапустите: \`cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8001\``,
        confidence: 'low',
        missingData: ['Backend не ответил или вернул ошибку'],
        sources: [],
        requestedSources,
      }]);
    } finally {
      setIsAsking(false);
    }
  }, [isAsking]);

  const deleteDocument = useCallback(async (doc: DocInfo) => {
    const ok = window.confirm(`Удалить «${doc.filename}» из индекса?`);
    if (!ok) return;
    try {
      await fetchJson(`/documents/${encodeURIComponent(doc.id)}`, { method: 'DELETE' });
      await loadDocs();
      setMessages(prev => prev.filter(message => {
        const pools = [...(message.tables || []), ...(message.figures || []), ...(message.maps || []), ...(message.sources || [])];
        return !pools.some(item => item.document_id === doc.id);
      }));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Не удалось удалить');
    }
  }, [loadDocs]);

  const upload = useCallback(async (file?: File) => {
    if (!file || uploadState === 'uploading') return;
    setUploadState('uploading');
    setUploadMsg(`Загружается «${file.name}»…`);
    const form = new FormData();
    form.append('file', file);
    try {
      const result = await fetchJson<{ message: string; status?: string; document_id?: string }>(
        '/documents/upload', { method: 'POST', body: form }
      );
      if (result.status === 'processing' && result.document_id) {
        // Large file — poll for completion
        setUploadMsg(`«${file.name}» обрабатывается в фоне…`);
        await loadDocs();
        const docId = result.document_id;
        let attempts = 0;
        const poll = async () => {
          attempts++;
          try {
            const status = await fetchJson<{ status: string; artifacts?: number; message?: string }>(
              `/documents/status/${docId}`
            );
            if (status.status === 'ready') {
              setUploadState('success');
              setUploadMsg(`«${file.name}» готов: ${status.artifacts ?? 0} артефактов`);
              await loadDocs();
              window.setTimeout(() => { setUploadState('idle'); setUploadMsg('PDF, DOCX, Excel, CSV, изображения и сканы'); }, 4000);
              return;
            }
            if (status.status === 'error') {
              setUploadState('error');
              setUploadMsg(status.message || 'Ошибка обработки документа');
              return;
            }
          } catch { /* ignore poll errors */ }
          if (attempts < 60) {
            window.setTimeout(poll, 3000); // retry every 3s for up to 3 minutes
          } else {
            setUploadState('success');
            setUploadMsg(`«${file.name}» — обработка продолжается в фоне`);
            window.setTimeout(() => { setUploadState('idle'); setUploadMsg('PDF, DOCX, Excel, CSV, изображения и сканы'); }, 4000);
          }
        };
        window.setTimeout(poll, 3000);
      } else {
        setUploadState('success');
        setUploadMsg(result.message || 'Документ проиндексирован');
        await loadDocs();
        window.setTimeout(() => { setUploadState('idle'); setUploadMsg('PDF, DOCX, Excel, CSV, изображения и сканы'); }, 3500);
      }
    } catch (err) {
      setUploadState('error');
      setUploadMsg(err instanceof Error ? err.message : 'Ошибка загрузки');
      window.setTimeout(() => { setUploadState('idle'); setUploadMsg('PDF, DOCX, Excel, CSV, изображения и сканы'); }, 4500);
    }
  }, [uploadState, loadDocs]);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <GeoDocLogo size={34} />
          <div><strong>GeoDoc AI</strong><span>Geological RAG workspace</span></div>
        </div>
        <div className="header-spacer" />
        <TrajectoryModeSwitch mode={mode} onChange={setMode} />
      </header>

      {mode === 'documents' ? (
        <div className="layout">
          {/* Sidebar */}
          <aside className="sidebar">
            <UploadBox state={uploadState} message={uploadMsg} onUpload={upload} />
            <div className="sidebar-section">
              <span className="sidebar-label">Документы</span>
              <div className="doc-list">
                {documents.length ? documents.map(doc => (
                  <article className="doc-card" key={doc.id}>
                    <FileText size={15} />
                    <div className="doc-card-info">
                      <strong>{doc.filename}</strong>
                      {(doc as Record<string,unknown>).processing
                        ? <small style={{color:'#f59e0b'}}>⏳ Обрабатывается…</small>
                        : <small>{doc.artifacts ?? doc.chunks} арт. · {doc.tables || 0} табл. · {doc.maps || 0} карт</small>
                      }
                    </div>
                    <button className="doc-delete" type="button" onClick={() => deleteDocument(doc)} aria-label={`Удалить ${doc.filename}`}>
                      <Trash2 size={13} />
                    </button>
                  </article>
                )) : <p className="muted">Загрузите первый документ, чтобы начать анализ.</p>}
              </div>
            </div>
          </aside>

          {/* Main chat area */}
          <main className="main">
            <div className="chat-thread" ref={threadRef}>
              {messages.length === 0 ? <WelcomeScreen /> : (
                <>
                  {messages.map((message, index) => (
                    <div key={index} className={`message-row ${message.role === 'user' ? 'user' : ''}`}>
                      {message.role === 'user' ? (
                        <>
                          <div className="message-avatar user-av">Я</div>
                          <div className="message-bubble"><div className="user-bubble">{message.text}</div></div>
                        </>
                      ) : (
                        <>
                          <div className="message-avatar ai-av"><GeoDocLogo size={18} /></div>
                          <div className="message-bubble" style={{ flex: 1, maxWidth: '100%' }}>
                            <AiBubble message={message} />
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                  {isAsking && <TypingIndicator />}
                </>
              )}
            </div>
            <QuestionBar value={question} setValue={setQuestion} ask={ask} loading={isAsking} />
          </main>
        </div>
      ) : <TrajectoryWorkspace />}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

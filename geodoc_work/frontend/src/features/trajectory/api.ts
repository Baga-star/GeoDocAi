const configuredApiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
const configuredApiKey = (import.meta.env.VITE_API_KEY as string | undefined)?.trim();
const browserHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const sameHostApiBase = typeof window !== 'undefined'
  ? `http://${browserHost}:8001/api`
  : 'http://localhost:8001/api';

const API_CANDIDATES = Array.from(new Set([
  configuredApiBase,
  sameHostApiBase,
  'http://localhost:8001/api',
  'http://127.0.0.1:8001/api',
  import.meta.env.DEV ? undefined : '/api',
].filter(Boolean) as string[]));

let activeApiBase = API_CANDIDATES[0] || 'http://localhost:8001/api';

export function trajectoryApiUrl(path: string, base = activeApiBase): string {
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export function withTrajectoryAuth(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  if (configuredApiKey) headers.set('X-API-Key', configuredApiKey);
  return { ...init, headers };
}

/** Parse FastAPI error detail safely — always returns a string */
function parseDetail(detail: unknown): string {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    const d = detail as Record<string, unknown>;
    if (typeof d.message === 'string') return d.message;
    if (Array.isArray(d.errors) && d.errors.length > 0) return String(d.errors[0]);
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as Record<string, unknown>;
      return typeof first.msg === 'string' ? first.msg : JSON.stringify(first);
    }
    return JSON.stringify(detail);
  }
  return String(detail);
}

export async function trajectoryJson<T>(path: string, init?: RequestInit): Promise<T> {
  const candidates = API_CANDIDATES.map(base => trajectoryApiUrl(path, base));
  let lastError: unknown;
  for (const url of candidates) {
    try {
      const res = await fetch(url, withTrajectoryAuth(init));
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as Record<string, unknown>;
        const msg = parseDetail(body.detail) || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      activeApiBase = url.replace(/\/trajectory.*/, '');
      return res.json() as Promise<T>;
    } catch (err) {
      lastError = err;
    }
  }
  throw new Error(lastError instanceof Error ? lastError.message : 'Trajectory API недоступен');
}

export async function trajectoryBlob(path: string): Promise<Blob> {
  const candidates = API_CANDIDATES.map(base => trajectoryApiUrl(path, base));
  let lastError: unknown;
  for (const url of candidates) {
    try {
      const res = await fetch(url, withTrajectoryAuth());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      activeApiBase = url.replace(/\/trajectory.*/, '');
      return res.blob();
    } catch (err) {
      lastError = err;
    }
  }
  throw new Error(lastError instanceof Error ? lastError.message : 'Не удалось скачать файл');
}

export async function trajectoryPostJson<T>(path: string, body: unknown = {}): Promise<T> {
  return trajectoryJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

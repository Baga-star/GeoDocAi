const configuredApiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
const configuredApiKey = (import.meta.env.VITE_API_KEY as string | undefined)?.trim();
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

export function trajectoryApiUrl(path: string, base = activeApiBase): string {
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

export function withTrajectoryAuth(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  if (configuredApiKey) headers.set('X-API-Key', configuredApiKey);
  return { ...init, headers };
}

export async function trajectoryJson<T>(path: string, init?: RequestInit): Promise<T> {
  const candidates = API_CANDIDATES.map(base => trajectoryApiUrl(path, base));
  let lastError: unknown;
  for (const url of candidates) {
    try {
      const res = await fetch(url, withTrajectoryAuth(init));
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail?.message || body.detail || `HTTP ${res.status}`);
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

// Base URL of the FastAPI backend. The browser calls it directly so SSE streams are not buffered.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function handle<T>(res: Response, path: string): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, `${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, user?: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: user ? { "X-User-Id": user } : undefined,
  });
  return handle<T>(res, path);
}

export async function apiPost<T>(path: string, body: unknown, user: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Id": user },
    body: JSON.stringify(body ?? {}),
  });
  return handle<T>(res, path);
}

export async function apiPatch<T>(path: string, body: unknown, user: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-User-Id": user },
    body: JSON.stringify(body ?? {}),
  });
  return handle<T>(res, path);
}

export async function apiDelete<T>(path: string, user: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: { "X-User-Id": user } });
  return handle<T>(res, path);
}

export function streamUrl(runId: string, user: string) {
  return `${API_BASE}/api/briefings/${runId}/stream?user=${encodeURIComponent(user)}`;
}

export type Health = {
  status: string;
  today: string;
  llm_mode: "anthropic" | "offline";
  models?: { opus: string; haiku: string };   // display names of the live models, e.g. "Opus 5.5", "Haiku 5.5"
  db_ready: boolean;
  index_ready?: boolean;
};

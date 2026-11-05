import type {
  EvaluationReport, FeedbackCreated, FeedbackList, FeedbackUndone, Method,
  NextProductsResponse, PreferenceSummary, RecommendationsResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
  get isDuplicate() { return this.status === 409; }
  get isNotFound() { return this.status === 404; }
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : "")).filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch (e) {
    throw new ApiError(0, "Cannot reach the Brickwise server. Is the backend running?", e);
  }
  if (!res.ok) {
    let detail: unknown = null;
    try { detail = (await res.json() as { detail?: unknown }).detail ?? null; } catch { /* non-JSON body */ }
    throw new ApiError(res.status, detailToMessage(detail, `Request failed (${res.status})`), detail);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  health: () => request<{ status: string; products: number; embeddings: number; faiss: boolean }>("/api/health"),
  nextProducts: (limit = 1) => request<NextProductsResponse>(`/api/products/next?limit=${limit}`),
  rate: (set_num: string, rating: 0 | 1) =>
    request<FeedbackCreated>("/api/feedback", { method: "POST", body: JSON.stringify({ set_num, rating }) }),
  undo: () => request<FeedbackUndone>("/api/feedback/undo", { method: "POST" }),
  feedback: () => request<FeedbackList>("/api/feedback"),
  resetProfile: () => request<void>("/api/feedback", { method: "DELETE" }),
  preferences: () => request<PreferenceSummary>("/api/preferences"),
  recommendations: (method: Method, k = 5) =>
    request<RecommendationsResponse>(`/api/recommendations?k=${k}&method=${method}`),
  evaluation: () => request<EvaluationReport>("/api/evaluation"),
  simulate: () => request<EvaluationReport>("/api/evaluation/simulate", { method: "POST" }),
};

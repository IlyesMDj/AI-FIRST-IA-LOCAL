/**
 * Client HTTP typé — conforme à CONTRACTS.md (section « API HTTP »).
 * Base : /api (proxifié par Vite vers http://127.0.0.1:8000).
 * Mode démo : VITE_MOCK=1 ou `?mock` dans l'URL → données fictives en mémoire (src/mock.ts).
 * Aucune donnée candidat n'est persistée côté navigateur.
 */

// --- Types (miroir de backend/copilot/types.py) -----------------------------

export type Status = "pending" | "analyzing" | "ready" | "unsupported" | "error";
export type Assessment = "présent" | "partiel" | "non trouvé";
export type ModelKey = "rapide" | "precis";

export interface Criterion {
  id: string; // "C1".."C99"
  label: string;
  description: string;
}

export interface Evidence {
  criterion_id: string;
  assessment: Assessment;
  quote: string | null;
  start: number | null;
  end: number | null;
}

export interface Analysis {
  display_name?: string | null;
  summary: string;
  evidence: Evidence[];
  points_to_clarify: string[];
  dropped_quotes: number;
  model: string;
  prompt_version: number;
}

export interface InterviewQuestion {
  question: string;
  rationale: string;
  criterion_id: string | null;
}

export interface ErasureProof {
  candidate_id_hash: string;
  erased_at: string;
  tables: Record<string, number>;
  raw_file_hits: number;
  /** Nombre d'extraits du CV réellement recherchés dans les octets du .db (0 = vérification impossible). */
  extracts_checked: number;
  /** False si le VACUUM a échoué (pages libres non compactées). */
  vacuum_ok: boolean;
  verified: boolean;
}

export interface Health {
  ok: boolean;
  models: string[];
  missing: string[];
  model_keys: { rapide: string; precis: string };
}

export interface Job {
  title: string;
  text: string;
  criteria: Criterion[];
}

export interface CandidateSummary {
  id: string;
  display_name: string;
  status: Status;
  reason: string | null;
  created_at: string;
}

export interface UploadedCandidate {
  id: string;
  display_name: string;
  status: Status;
}

export interface CandidateDetail extends CandidateSummary {
  redacted_text: string | null;
  removed: Record<string, number>;
  analysis: Analysis | null;
  questions: InterviewQuestion[];
}

export interface CompareCell {
  assessment: Assessment;
  quote: string | null;
}

export interface CompareResult {
  criteria: Criterion[];
  candidates: { id: string; display_name: string; status: Status; cells: Record<string, CompareCell> }[];
}

export interface Api {
  health(): Promise<Health>;
  getJob(): Promise<Job>;
  saveCriteria(criteria: Criterion[]): Promise<{ criteria: Criterion[] }>;
  suggestCriteria(model: ModelKey): Promise<{ criteria: Criterion[] }>;
  uploadCandidates(files: File[], model: ModelKey): Promise<UploadedCandidate[]>;
  listCandidates(): Promise<CandidateSummary[]>;
  getCandidate(id: string): Promise<CandidateDetail>;
  reanalyze(id: string, model: ModelKey): Promise<{ status: Status }>;
  generateQuestions(id: string, model: ModelKey): Promise<{ questions: InterviewQuestion[] }>;
  /** Flux SSE (POST) : onToken est appelé à chaque fragment. Rien n'est stocké. */
  ask(id: string, question: string, model: ModelKey, onToken: (t: string) => void, signal?: AbortSignal): Promise<void>;
  compare(): Promise<CompareResult>;
  erase(id: string): Promise<ErasureProof>;
  erasures(): Promise<ErasureProof[]>;
}

// --- Erreurs ----------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let msg = `Erreur ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") msg = body.detail;
    else if (body && Array.isArray(body.detail)) msg = body.detail.map((d: { msg?: string }) => d.msg ?? "").join(" ; ");
  } catch {
    /* corps non JSON */
  }
  return new ApiError(res.status, msg);
}

const BASE = "/api";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Serveur local injoignable (le back-end est-il lancé sur le port 8000 ?)");
  }
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

// --- Client réel ------------------------------------------------------------

export const httpApi: Api = {
  health: () => request("GET", "/health"),
  getJob: () => request("GET", "/job"),
  saveCriteria: (criteria) => request("PUT", "/job/criteria", { criteria }),
  suggestCriteria: (model) => request("POST", "/job/criteria/suggest", { model }),

  async uploadCandidates(files, model) {
    const form = new FormData();
    // FastAPI : `files: list[UploadFile]` → champ « files » répété.
    for (const f of files) form.append("files", f, f.name);
    form.append("model", model);
    let res: Response;
    try {
      res = await fetch(`${BASE}/candidates`, { method: "POST", body: form });
    } catch {
      throw new ApiError(0, "Serveur local injoignable");
    }
    if (!res.ok) throw await errorFrom(res);
    return res.json();
  },

  listCandidates: () => request("GET", "/candidates"),
  getCandidate: (id) => request("GET", `/candidates/${enc(id)}`),
  reanalyze: (id, model) => request("POST", `/candidates/${enc(id)}/reanalyze`, { model }),
  generateQuestions: (id, model) => request("POST", `/candidates/${enc(id)}/questions`, { model }),

  async ask(id, question, model, onToken, signal) {
    const res = await fetch(`${BASE}/candidates/${enc(id)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, model }),
      signal,
      cache: "no-store",
    });
    if (!res.ok) throw await errorFrom(res);
    if (!res.body) throw new ApiError(0, "Flux de réponse indisponible");
    await readSse(res.body, onToken);
  },

  compare: () => request("GET", "/compare"),
  erase: (id) => request("DELETE", `/candidates/${enc(id)}`),
  erasures: () => request("GET", "/erasures"),
};

/** Lit un flux text/event-stream : `data: {"token": "..."}` … `data: {"done": true}`. */
export async function readSse(body: ReadableStream<Uint8Array>, onToken: (t: string) => void): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const event = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const data = event
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).replace(/^ /, ""))
          .join("\n");
        if (!data) continue;
        let msg: { token?: string; done?: boolean; error?: string; detail?: string };
        try {
          msg = JSON.parse(data);
        } catch {
          continue;
        }
        if (msg.error || msg.detail) throw new ApiError(500, msg.error ?? msg.detail ?? "Erreur du modèle");
        if (typeof msg.token === "string") onToken(msg.token);
        if (msg.done) return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// --- Sélection réel / mock --------------------------------------------------

export const MOCK: boolean =
  import.meta.env.VITE_MOCK === "1" ||
  (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("mock"));

let impl: Api = httpApi;
export function setApi(a: Api) {
  impl = a;
}

/** Point d'entrée unique utilisé par l'UI. */
export const api: Api = new Proxy({} as Api, {
  get: (_t, prop: keyof Api) => impl[prop],
});

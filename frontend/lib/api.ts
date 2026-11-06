// Typed client for the local backend (same-origin, proxied by Next.js).
import { getLang, translate } from "./i18n";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const UNREACHABLE = "The application server is not reachable. Is the backend running?";

/** Headers sent with every request: the backend translates its messages. */
export function langHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("X-Lang", getLang());
  return h;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { cache: "no-store", ...init, headers: langHeaders(init?.headers) });
  } catch {
    throw new ApiError(translate(getLang(), UNREACHABLE), 0);
  }
  if (!res.ok) {
    let msg = translate(getLang(), "Request failed ({status})", { status: res.status });
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    if (res.status === 502 || res.status === 504) msg = translate(getLang(), UNREACHABLE);
    throw new ApiError(msg, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>(p),
  post: <T,>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }),
  put: <T,>(p: string, body: unknown) =>
    request<T>(p, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  del: <T,>(p: string) => request<T>(p, { method: "DELETE" }),
  upload: <T,>(p: string, form: FormData) => request<T>(p, { method: "POST", body: form }),
};

// ------------------------------------------------------------------ types
export type CandidateStatus = "imported" | "pending" | "processing" | "completed" | "failed";

export interface CandidateSummary {
  id: string;
  display_name: string | null;
  email: string | null;
  status: CandidateStatus;
  processing_step: string | null;
  error_message: string | null;
  original_filename: string;
  file_type: string;
  file_size: number;
  ocr_used: boolean;
  has_warnings: boolean;
  confidence: number | null;
  created_at: string;
  processed_at: string | null;
}

export interface Verification {
  status: "verified" | "approximate" | "term_found" | "not_found" | "missing";
  location: { start: number; end: number; section: string } | null;
}

export interface Skill { name: string; category: string; basis: "explicit" | "inferred"; evidence: string | null; verification: Verification }
export interface Experience { position: string | null; company: string | null; description: string | null; start_date: string | null; end_date: string | null; evidence: string | null; verification: Verification }
export interface Education { degree: string | null; field: string | null; institution: string | null; graduation_year: number | null; evidence: string | null; verification: Verification }
export interface Language { language: string; level: string | null; evidence: string | null; verification: Verification }
export interface Certification { name: string; issuer: string | null; year: number | null; evidence: string | null; verification: Verification }
export interface Project { name: string; description: string | null; technologies: string[]; evidence: string | null; verification: Verification }

export interface Profile {
  candidate_name: string | null;
  professional_summary: string | null;
  skills: Skill[];
  experience: Experience[];
  education: Education[];
  languages: Language[];
  certifications: Certification[];
  projects: Project[];
  extraction_metadata: { model: string; confidence: number; confidence_method: string; processed_at: string; attempts: number; duration_s: number; text_method: string; prompt_version: string };
}

export interface CandidateDetail extends CandidateSummary {
  phone: string | null;
  page_count: number | null;
  injection_flags: { type: string; excerpt: string }[];
  warnings: string[];
  possible_duplicates: { candidate_id: string; rule: string }[];
  profile: Profile | null;
  text_method: string | null;
  redactions: Record<string, number> | null;
}

export interface Job {
  id: string;
  title: string;
  description: string;
  required_skills: string[];
  optional_skills: string[];
  experience_requirements: string;
  education_requirements: string;
  languages: string[];
  responsibilities: string[];
  criteria: string[];
  created_at: string;
  updated_at: string;
}

export type AssessmentStatus = "demonstrated" | "partial" | "not_found" | "undetermined";

export interface EvidenceItem {
  quote: string;
  verified: boolean;
  match?: string;
  location: { start: number; end: number; section: string } | null;
}

export interface CriterionResult {
  id: string;
  kind: string;
  importance: "required" | "optional";
  requirement: string;
  status: AssessmentStatus;
  status_label: string;
  model_status: AssessmentStatus;
  evidence: EvidenceItem[];
  relevant_experience: string | null;
  missing_information: string | null;
  explanation: string;
  verification_notes: string[];
}

export interface InterviewQuestion {
  question: string;
  why_relevant: string;
  competency: string;
  evidence: EvidenceItem | null;
}

export interface Analysis {
  id: string;
  candidate_id: string;
  job_id: string;
  kind: "analysis" | "interview";
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  result:
    | ({ criteria?: CriterionResult[]; disclaimer?: string; model?: string; generated_at?: string;
         categories?: { key: string; label: string; questions: InterviewQuestion[] }[]; removed_questions?: number })
    | null;
  model: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  candidate_name: string | null;
  job_title: string | null;
}

export interface SystemStatus {
  ollama: { url: string; reachable: boolean; version?: string; error?: string };
  active_model: string;
  embedding_model: string;
  active_model_available: boolean;
  embedding_model_available: boolean;
  installed_models: { name: string; size_mb: number; parameter_size?: string; quantization?: string; family?: string; capabilities: string[]; role?: string }[];
  running_models: { name: string; size_mb: number; vram_mb: number; context_length?: number; expires_at?: string }[];
  hardware: {
    cpu_pct: number; cpu_count: number; ram_total_mb: number; ram_available_mb: number; ram_used_pct: number;
    gpus: { name: string; vram_total_mb: number; vram_used_mb: number; utilization_pct: number | null; temperature_c: number | null }[];
  };
  queue: { pending: number; current: string | null };
  ocr_available: boolean;
  issues: string[];
}

export interface Citation {
  ref: string;
  candidate_id: string;
  candidate_label: string;
  section: string;
  text: string | null;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
}

export interface Conversation {
  id: string;
  title: string;
  job_id: string | null;
  created_at: string;
  candidates: { id: string; label: string }[];
  messages?: ChatMessage[];
}

export interface DeletionReport {
  candidate_ref: string;
  deleted_at: string;
  removed: { records: Record<string, number>; files: string[] };
  verification: { check: string; passed: boolean; details: Record<string, unknown> }[];
  secure_delete: string;
  limitations: string[];
}

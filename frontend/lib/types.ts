export type User = { user_id: string; name: string; team?: string; clearance: "analyst" | "senior" };

export type ClientSignal = { rule: string; title: string; severity: "high" | "medium" };

/** A covered client with a short snapshot for the home page (from GET /api/clients). */
export type ClientSnapshot = {
  client_id: string;
  client_name: string;
  industry: string;
  region: string;
  segment: string;
  tier: string;
  client_since: string;
  role: string;
  meetings: { meeting_id: string; start_time: string; title: string }[];
  signals: ClientSignal[];
};

export type Task = {
  task_id: string;
  client_id: string;
  owner: string;
  description: string;
  due_date: string | null;
  status: "open" | "done";
  created_at?: string;
  run_id?: string;          // present in the cross-briefing list
  client_name?: string;
  meeting?: string;
};

export type BriefingSummary = {
  run_id: string;
  client_id: string;
  meeting_id: string | null;
  client_name: string | null;
  meeting: string | null;
  mode: "anthropic" | "offline" | null;
  created_at: string;
  status: "complete" | "in progress" | "failed";
  unavailable: string[];
  statements: number;
  questions_asked: number;
  tasks_created: number;
};

export type Evidence = {
  id: string;
  kind: string;
  title: string;
  text: string;
  restricted: boolean;
  source: {
    type: "sql" | "doc" | "system";
    query?: string;
    params?: unknown[];
    rows?: Record<string, unknown>[];
    refs?: string[];
    doc_id?: string;
    chunk_id?: string;
    page?: number;
    section?: string | null;
    date?: string;
    doc_type?: string;
    title?: string;
    quote?: string;
    sources?: string[];
    found_by?: string;
    rule?: string;
    severity?: string;
    threshold?: number;
    value?: number;
  };
};

/** role: 'answer' (direct answer to the question), 'point' (labelled supporting detail), 'why' (why it matters).
 *  Offline and older briefings have no role: shown as a plain list. */
export type Statement = {
  text: string; evidence_ids: string[]; empty?: boolean; kind?: string;
  role?: "answer" | "point" | "why"; label?: string;
};

export type Section = {
  id: string;
  question: string;
  status: "ok" | "unavailable";
  layout?: "bullets" | "table";
  statements: Statement[];
  dropped: { text: string; reason: string }[];
  evidence?: Record<string, Evidence>;
};

export type PlanTask = { id: string; reason: string; depends_on: string[]; agent: string };
export type Plan = { tasks: PlanTask[]; focus: string };
export type TaskStatus = "queued" | "running" | "done" | "unavailable";

export type GuardResult = {
  ok: boolean;
  reason: string;
  original_sql: string;
  rewritten_sql: string | null;
  row_count: number;
};

export type ChatAnswer = {
  answer: Statement[];
  dropped?: { text: string; reason: string }[];
  sql: GuardResult | null;
  evidence: Record<string, Evidence>;
};

export const SECTION_ORDER = ["profile", "what_changed", "commitments", "metrics", "opportunities", "news"] as const;

/** Which agent tasks each section waits for (mirrors SECTION_NEEDS in the backend supervisor). */
export const SECTION_NEEDS: Record<string, string[]> = {
  profile: ["profile", "notes"], what_changed: ["changes"], commitments: ["commitments"], metrics: ["signals"],
  opportunities: ["opportunities", "deals_actions"], news: ["news"],
};

/** The question each section answers (same wording as the backend), shown under the section title. */
export const SECTION_QUESTIONS: Record<string, string> = {
  profile: "Who is the client and what matters in the relationship?",
  what_changed: "What changed since the last interaction?",
  commitments: "What did the client ask, say or commit to, and what remains open?",
  metrics: "Which metrics or performance are material?",
  opportunities: "Which opportunities should the team discuss, and what evidence supports them?",
  news: "Which recent news or events should shape the conversation?",
};

export const SECTION_TITLES: Record<string, string> = {
  profile: "Who they are and what matters",
  what_changed: "What changed since we last met",
  commitments: "Asks, promises and what is open",
  metrics: "Material metrics",
  opportunities: "Opportunities to discuss",
  news: "News to shape the conversation",
  uncertainty: "Uncertain, conflicting or unavailable",
};

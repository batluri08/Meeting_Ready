"use client";

import { WorkingDots } from "@/components/WorkingDots";
import { formatMeeting } from "@/lib/format";
import type { Plan, TaskStatus } from "@/lib/types";

/** Each agent task as a short name; the longer explanation shows on hover. */
const STEPS: Record<string, { name: string; short: string; detail: string }> = {
  profile: { name: "Client record", short: "the client record", detail: "Products, contacts, satisfaction, share of wallet" },
  signals: { name: "Key numbers", short: "the numbers", detail: "Revenue, service issues, product use and surveys, checked against the importance rules" },
  changes: { name: "Changes since last meeting", short: "what changed", detail: "New deals, issues, emails, news and surveys" },
  deals_actions: { name: "Deals and follow-ups", short: "deals and follow-ups", detail: "Open pipeline and actions" },
  opportunities: { name: "Product ideas", short: "product ideas", detail: "Backed by data and the client's own words" },
  email_extract: { name: "Emails", short: "the emails", detail: "What the client asked for, promised or worried about" },
  notes: { name: "Call notes", short: "call notes", detail: "Notes and transcripts; flags out-of-date statements" },
  news: { name: "News", short: "the news", detail: "Approved sources, one entry per story" },
  commitments: { name: "Untracked asks", short: "the follow-up check", detail: "Client asks that no open action covers" },
};

/** Short names, used by the briefing sections while they wait ("Waiting for the emails and call notes"). */
export const LABEL: Record<string, string> = Object.fromEntries(Object.entries(STEPS).map(([k, v]) => [k, v.short]));

function Status({ st }: { st: TaskStatus }) {
  if (st === "done") return <span className="w-3.5 shrink-0 text-center text-[12px] font-bold text-ok" aria-label="done">✓</span>;
  if (st === "unavailable") return <span className="w-3.5 shrink-0 text-center text-[12px] font-bold text-risk" aria-label="could not complete">!</span>;
  if (st === "running") return <span className="flex w-3.5 shrink-0 justify-center text-accent"><WorkingDots /></span>;
  return <span className="mx-[3px] h-2 w-2 shrink-0 rounded-full border border-muted" aria-label="waiting" />;
}

/** How the briefing was prepared: the focus and a compact checklist. Folds away once complete. */
export function PlanTimeline({ plan, status, done }: {
  plan: Plan | null; status: Record<string, TaskStatus>; done: boolean; live?: boolean;
}) {
  if (!plan) return (
    <p className="flex items-center gap-2 rounded-xl border border-line bg-surface p-4 text-sm text-muted">
      <WorkingDots className="text-accent" /> Planning
    </p>
  );
  const total = plan.tasks.length;
  const finished = plan.tasks.filter((t) => ["done", "unavailable"].includes(status[t.id] ?? "")).length;
  const failed = plan.tasks.filter((t) => status[t.id] === "unavailable").length;

  return (
    <details open={!done} className="group rounded-xl border border-line bg-surface px-4 py-3">
      <summary className="flex cursor-pointer list-none items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">How this was prepared</span>
        <span className={`shrink-0 text-xs ${failed ? "text-risk" : "text-muted"}`}>
          {finished}/{total}{failed ? ` · ${failed} failed` : ""}
        </span>
      </summary>

      {!done && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-canvas" aria-hidden="true">
          <div className="h-full bg-accent transition-all" style={{ width: `${Math.round((finished / total) * 100)}%` }} />
        </div>
      )}

      <p className="mt-2 line-clamp-2 text-xs text-muted" title={formatMeeting(plan.focus)}>
        <span className="font-medium text-ink">Focus:</span> {formatMeeting(plan.focus)}
      </p>

      <ul className="mt-2 flex flex-col gap-1">
        {plan.tasks.map((t) => {
          const st = status[t.id] ?? "queued";
          const step = STEPS[t.id];
          return (
            <li key={t.id} className="flex items-center gap-2 text-[13px]" title={step?.detail}>
              <Status st={st} />
              <span className={`min-w-0 truncate ${st === "unavailable" ? "text-risk" : st === "queued" ? "text-muted" : ""}`}>
                {step?.name ?? t.id}
              </span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

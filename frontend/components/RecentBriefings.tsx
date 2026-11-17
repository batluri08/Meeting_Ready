"use client";

import Link from "next/link";
import { useState } from "react";
import { apiDelete } from "@/lib/api";
import { ago, formatMeeting } from "@/lib/format";
import { engineLabel, useModels } from "@/lib/models";
import type { BriefingSummary } from "@/lib/types";

const STATUS: Record<string, string> = {
  complete: "bg-ok-soft text-ok",
  "in progress": "bg-info-soft text-info",
  failed: "bg-risk-soft text-risk",
};

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** The signed-in user's saved briefings, newest first, with open and delete. */
export function RecentBriefings({ items, user, onDeleted }: {
  items: BriefingSummary[] | null; user: string; onDeleted: (runId: string) => void;
}) {
  const models = useModels();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(runId: string) {
    try {
      await apiDelete(`/api/briefings/${runId}`, user);
      onDeleted(runId);
    } catch (e) {
      setError(String(e));
    } finally {
      setConfirming(null);
    }
  }

  return (
    <section className="rounded-xl border border-line bg-surface">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <h2 className="text-[15px] font-semibold">Recent briefings</h2>
        <p className="text-xs text-muted">Saved automatically. Only you can see yours.</p>
      </header>
      {error && <p className="px-5 pt-3 text-sm text-risk">{error}</p>}
      {items === null && <p className="px-5 py-4 text-sm text-muted">Loading…</p>}
      {items?.length === 0 && (
        <p className="px-5 py-4 text-sm text-muted">No briefings yet. Prepare one from a meeting above and it will be saved here.</p>
      )}
      {items && items.length > 0 && (
        <ul className="divide-y divide-line">
          {items.map((b) => (
            <li key={b.run_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{b.client_name ?? b.client_id}</p>
                <p className="truncate text-xs text-muted">{formatMeeting(b.meeting)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <span title={b.created_at}>{ago(b.created_at)}</span>
                <span className="rounded-full bg-canvas px-2 py-0.5 font-mono text-[10px]">{b.mode ? engineLabel(b.mode, models) : "–"}</span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase ${STATUS[b.status]}`}>{b.status}</span>
                {b.unavailable.length > 0 && <span className="text-risk">{b.unavailable.length} unavailable</span>}
                {(b.questions_asked > 0 || b.tasks_created > 0) && (
                  <span>{plural(b.questions_asked, "question")} · {plural(b.tasks_created, "task")}</span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {confirming === b.run_id ? (
                  <>
                    <span className="text-xs text-muted">Delete?</span>
                    <button onClick={() => remove(b.run_id)} className="rounded-md bg-risk px-2.5 py-1 text-xs font-medium text-white">Delete</button>
                    <button onClick={() => setConfirming(null)} className="rounded-md px-2.5 py-1 text-xs text-muted hover:text-ink">Cancel</button>
                  </>
                ) : (
                  <>
                    <Link href={`/briefing/${b.run_id}`} className="rounded-md px-2.5 py-1 text-sm font-medium text-accent hover:bg-accent-soft">Open</Link>
                    <button onClick={() => setConfirming(b.run_id)} disabled={b.status === "in progress"}
                      title={b.status === "in progress" ? "Wait until it has finished" : "Delete this briefing"}
                      className="rounded-md px-2.5 py-1 text-sm text-muted hover:bg-risk-soft hover:text-risk disabled:opacity-40">Delete</button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

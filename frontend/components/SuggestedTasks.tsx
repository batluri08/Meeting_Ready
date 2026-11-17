"use client";

import { useEffect, useState } from "react";
import { WorkingDots } from "@/components/WorkingDots";
import { apiPost } from "@/lib/api";
import { useModels } from "@/lib/models";
import type { Task } from "@/lib/types";

export type Suggestion = { description: string; reason: string; timing: string; due_date: string; evidence_ids: string[] };

// One request per briefing while the page is open, shared by the Tasks panel and the Create task dialog.
// (The backend also keeps them with the briefing, so the model is asked only once.)
/** source: 'opus' on live briefings, 'rules' offline (no AI), so the label never claims AI that did not run. */
export type Suggestions = { suggestions: Suggestion[]; source: "opus" | "rules" };
const loading: Record<string, Promise<Suggestions>> = {};
const cache: Record<string, Suggestions> = {};
export function loadSuggestions(runId: string, user: string): Promise<Suggestions> {
  loading[runId] ??= apiPost<Suggestions>(`/api/briefings/${runId}/actions/suggest_tasks`, {}, user)
    .then((r) => (cache[runId] = r))
    .catch((e) => { delete loading[runId]; throw e; });
  return loading[runId];
}

// "2026-11-18" is a calendar day: read it as local midnight, not UTC midnight (which shows the day before in the US).
export const day = (iso: string) => new Date(`${iso}T00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** Tasks Opus suggests from the briefing's open items. Nothing is created until the user adds one. */
export function SuggestedTasks({ runId, user, onAdded, onEdit }: {
  runId: string; user: string; onAdded: (task: Task) => void; onEdit: (description: string, due: string) => void;
}) {
  const models = useModels();
  const [set, setSet] = useState<Suggestions | null>(cache[runId] ?? null);
  const items = set?.suggestions ?? null;
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    if (cache[runId]) return;
    loadSuggestions(runId, user).then(setSet).catch((e) => setError(String(e)));
  }, [runId, user]);

  async function add(i: number, s: Suggestion) {
    setBusy(i);
    try {
      const task = await apiPost<Task>(`/api/briefings/${runId}/actions/create_task`,
        { description: s.description, due_date: s.due_date }, user);
      setAdded((a) => ({ ...a, [i]: true }));
      onAdded(task);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="flex flex-col gap-2 rounded-lg border border-line bg-canvas p-3">
      <h3 className="text-sm font-semibold">{set?.source === "rules" ? "Suggested from the briefing (offline rules)" : `Suggested by ${models.opus}`}</h3>
      <p className="text-xs text-muted">From the briefing&apos;s open asks, actions, concerns and flagged items. Due dates are set from
        the meeting date. Nothing is created until you add it.</p>
      {!items && !error && (
        <p className="flex items-center gap-2 py-2 text-sm text-muted"><WorkingDots className="text-accent" /> {models.opus} is reading the briefing</p>
      )}
      {error && <p className="text-sm text-risk">{error}</p>}
      {items?.length === 0 && <p className="text-sm text-muted">No follow-up tasks stand out in this briefing.</p>}
      <ul className="flex flex-col gap-2">
        {items?.map((s, i) => (
          <li key={i} className="flex items-start gap-3 rounded-md bg-surface px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="text-sm">{s.description}</p>
              <p className="mt-0.5 text-xs text-muted">
                Due {day(s.due_date)} · {s.timing} · {s.reason}
                <span className="ml-1 font-mono text-[10px]">{s.evidence_ids.join(" ")}</span>
              </p>
            </div>
            {added[i] ? (
              <span className="shrink-0 rounded-md bg-ok-soft px-2.5 py-1 text-xs font-medium text-ok">Added</span>
            ) : (
              <div className="flex shrink-0 gap-1.5">
                <button type="button" onClick={() => onEdit(s.description, s.due_date)}
                  className="rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent">Edit</button>
                <button type="button" onClick={() => add(i, s)} disabled={busy !== null}
                  className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50">
                  {busy === i ? "Adding…" : "Add"}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

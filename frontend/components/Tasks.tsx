"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { day, loadSuggestions, type Suggestion, type Suggestions } from "@/components/SuggestedTasks";
import { WorkingDots } from "@/components/WorkingDots";
import { apiPatch, apiPost } from "@/lib/api";
import { useModels } from "@/lib/models";
import type { Task } from "@/lib/types";

/** Demo date: the whole synthetic world is frozen on Monday 16 November 2026. */
export const TODAY = "2026-11-16";

export function dueLabel(due: string | null, status: string): { text: string; cls: string } {
  if (!due) return { text: "no due date", cls: "text-muted" };
  const pretty = new Date(`${due}T00:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  if (status === "done") return { text: `due ${pretty}`, cls: "text-muted" };
  if (due < TODAY) return { text: `overdue · was due ${pretty}`, cls: "text-risk font-medium" };
  if (due === TODAY) return { text: "due today", cls: "text-warn font-medium" };
  return { text: `due ${pretty}`, cls: "text-muted" };
}

/** One task with a tick box. Ticking marks it done (and back). */
export function TaskRow({ task, runId, user, onChange, showClient }: {
  task: Task; runId: string; user: string; onChange: (t: Task) => void; showClient?: boolean;
}) {
  const due = dueLabel(task.due_date, task.status);
  async function toggle() {
    const next = task.status === "done" ? "open" : "done";
    onChange({ ...task, status: next });                                  // optimistic
    try {
      const saved = await apiPatch<Task>(`/api/briefings/${runId}/tasks/${task.task_id}`, { status: next }, user);
      onChange({ ...task, ...saved });
    } catch {
      onChange(task);                                                    // put it back if saving failed
    }
  }
  return (
    <li className="flex items-start gap-3 py-2.5">
      <input type="checkbox" id={`task-${runId}-${task.task_id}`} checked={task.status === "done"} onChange={toggle}
        className="mt-1 h-4 w-4 accent-[var(--accent)]" aria-label={`Mark ${task.description} as done`} />
      <label htmlFor={`task-${runId}-${task.task_id}`} className="min-w-0 flex-1 cursor-pointer">
        <span className={`block text-sm ${task.status === "done" ? "text-muted line-through" : ""}`}>{task.description}</span>
        <span className="flex flex-wrap gap-x-2 text-xs">
          <span className={due.cls}>{due.text}</span>
          {showClient && task.client_name && <span className="text-muted">· {task.client_name}</span>}
        </span>
      </label>
      {showClient && (
        <Link href={`/briefing/${runId}`} className="shrink-0 text-xs text-accent hover:underline">Briefing</Link>
      )}
    </li>
  );
}

/** A suggested task, faded until hovered; "+" adds it as a real task. */
function SuggestionRow({ s, busy, onAdd }: { s: Suggestion; busy: boolean; onAdd: () => void }) {
  return (
    <li className="group flex items-start gap-3 py-2 opacity-55 transition-opacity hover:opacity-100 focus-within:opacity-100">
      <button type="button" onClick={onAdd} disabled={busy} aria-label={`Add task: ${s.description}`} title="Add this task"
        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-dashed border-accent text-sm leading-none text-accent hover:border-solid hover:bg-accent hover:text-white disabled:opacity-50">
        {busy ? "…" : "+"}
      </button>
      <span className="min-w-0 flex-1" title={s.reason}>
        <span className="block text-sm">{s.description}</span>
        <span className="block text-xs text-muted">due {day(s.due_date)} · {s.timing}</span>
      </span>
    </li>
  );
}

/** Tasks created from this briefing, plus faded suggestions from Opus that can be added with "+". */
export function TasksPanel({ tasks, runId, user, onChange }: {
  tasks: Task[]; runId: string; user: string; onChange: (t: Task) => void;
}) {
  const models = useModels();
  const [loaded, setLoaded] = useState<Suggestions | null>(null);
  const suggestions = loaded?.suggestions ?? null;
  const [failed, setFailed] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  // Hide folds the suggestions into one line (with Show to bring them back); remembered per briefing.
  const hideKey = `suggestions-hidden:${runId}`;
  const [hidden, setHidden] = useState(false);
  function toggleHidden(next: boolean) {
    setHidden(next);
    try { if (next) localStorage.setItem(hideKey, "1"); else localStorage.removeItem(hideKey); } catch { /* storage unavailable */ }
  }

  useEffect(() => {
    try { setHidden(localStorage.getItem(hideKey) === "1"); } catch { /* storage unavailable */ }
    loadSuggestions(runId, user).then(setLoaded).catch(() => setFailed(true));
  }, [runId, user, hideKey]);

  async function add(s: Suggestion) {
    setAdding(s.description);
    try {
      const task = await apiPost<Task>(`/api/briefings/${runId}/actions/create_task`,
        { description: s.description, due_date: s.due_date }, user);
      onChange(task);
    } catch {
      setFailed(true);
    } finally {
      setAdding(null);
    }
  }

  const made = new Set(tasks.map((t) => t.description));
  const shown = (suggestions ?? []).filter((s) => !made.has(s.description));
  const label = loaded?.source === "rules" ? "Suggested from the briefing (offline rules)" : `Suggested by ${models.opus}`;
  const open = tasks.filter((t) => t.status === "open").length;

  return (
    <section className="rounded-xl border border-line bg-surface">
      <header className="flex items-baseline justify-between border-b border-line px-5 py-3">
        <h2 className="text-[15px] font-semibold">Tasks</h2>
        <Link href="/tasks" className="text-xs text-accent hover:underline">All my tasks</Link>
      </header>
      <div className="px-5 py-2">
        {tasks.length > 0 && (
          <>
            <p className="pt-1 text-xs text-muted">{open} open · {tasks.length - open} done</p>
            <ul className="divide-y divide-line">
              {tasks.map((t) => <TaskRow key={t.task_id} task={t} runId={runId} user={user} onChange={onChange} />)}
            </ul>
          </>
        )}

        {!suggestions && !failed && (
          <p className="flex items-center gap-2 py-2 text-xs text-muted"><WorkingDots className="text-accent" /> Finding tasks to suggest</p>
        )}
        {shown.length > 0 && (
          <div className={tasks.length ? "mt-1 border-t border-line pt-2" : "pt-1"}>
            <p className="flex items-center justify-between gap-3 text-xs text-muted">
              <span>{hidden ? `${shown.length} suggested task${shown.length > 1 ? "s" : ""} hidden` : `${label} · click + to add`}</span>
              <button type="button" onClick={() => toggleHidden(!hidden)} aria-expanded={!hidden}
                className="shrink-0 font-medium text-accent hover:underline">{hidden ? "Show" : "Hide"}</button>
            </p>
            {!hidden && (
              <ul>
                {shown.map((s) => <SuggestionRow key={s.description} s={s} busy={adding === s.description} onAdd={() => add(s)} />)}
              </ul>
            )}
          </div>
        )}
        {tasks.length === 0 && suggestions && shown.length === 0 && (
          <p className="py-1 text-sm text-muted">None yet. Use More → Create task.</p>
        )}
      </div>
    </section>
  );
}

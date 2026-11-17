"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { API_BASE, apiDelete, apiPost } from "@/lib/api";
import { SuggestedTasks } from "@/components/SuggestedTasks";
import type { Task } from "@/lib/types";

type Result =
  | { kind: "email"; subject: string; body: string; status: string }
  | { kind: "task"; task_id: string; description: string; due_date: string | null; status: string }
  | { kind: "export"; filename: string; markdown: string }
  | { kind: "pdf"; filename: string }
  | { kind: "schedule"; trigger_at: string; meeting_start: string; status: string }
  | { kind: "confirm-delete" }
  | { kind: "task-form" }
  | { kind: "error"; message: string };

function saveBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Primary action (Export PDF) plus a "More" menu. Nothing is sent or written to a real system. */
export function ActionsBar({ runId, user, ready, onTaskCreated }: {
  runId: string; user: string; ready: boolean; onTaskCreated?: (task: Task) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [menu, setMenu] = useState(false);
  const [desc, setDesc] = useState("");
  const [due, setDue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => menuRef.current && !menuRef.current.contains(e.target as Node) && setMenu(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  async function run(action: string, body: object = {}) {
    setMenu(false);
    setBusy(action);
    try {
      const r = await apiPost<Record<string, unknown>>(`/api/briefings/${runId}/actions/${action}`, body, user);
      const kind = ({ draft_email: "email", create_task: "task", export: "export", schedule: "schedule" } as const)[action as "export"];
      setResult({ kind, ...r } as Result);
      if (action === "create_task") {
        onTaskCreated?.(r as unknown as Task);
        setDesc("");
        setDue("");
      }
    } catch (e) {
      setResult({ kind: "error", message: String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function downloadPdf() {
    setBusy("pdf");
    try {
      const res = await fetch(`${API_BASE}/api/briefings/${runId}/export.pdf`, { headers: { "X-User-Id": user } });
      if (!res.ok) throw new Error(`PDF export failed (${res.status})`);
      const name = res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ?? `briefing-${runId}.pdf`;
      saveBlob(name, await res.blob());
      setResult({ kind: "pdf", filename: name });
    } catch (e) {
      setResult({ kind: "error", message: String(e) });
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("delete");
    try {
      await apiDelete(`/api/briefings/${runId}`, user);
      router.push("/");
    } catch (e) {
      setResult({ kind: "error", message: String(e) });
      setBusy(null);
    }
  }

  const close = () => setResult(null);
  const item = "flex w-full items-center px-3 py-2 text-left text-sm hover:bg-canvas disabled:opacity-50";

  return (
    <>
      <div className="flex items-center gap-2" title={ready ? undefined : "Available when the briefing is complete"}>
        {!ready && <span className="text-xs text-muted">Actions unlock when complete</span>}
        <button disabled={!ready || !!busy} onClick={downloadPdf}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40">
          {busy === "pdf" ? "Preparing PDF…" : "Export PDF"}
        </button>
        <div className="relative" ref={menuRef}>
          <button disabled={!ready || !!busy} onClick={() => setMenu((m) => !m)} aria-haspopup="menu" aria-expanded={menu}
            className="rounded-lg border border-line bg-surface px-3 py-2 text-sm hover:border-accent disabled:cursor-not-allowed disabled:opacity-40">
            {busy && busy !== "pdf" ? "Working…" : "More ▾"}
          </button>
          {menu && (
            <div role="menu" className="absolute right-0 z-30 mt-1 w-60 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-lg">
              <button role="menuitem" className={item} onClick={() => run("draft_email")}>Draft follow-up email</button>
              <button role="menuitem" className={item} onClick={() => { setMenu(false); setResult({ kind: "task-form" }); }}>Create task</button>
              <button role="menuitem" className={item} onClick={() => run("schedule")}>Auto-brief before the meeting</button>
              <button role="menuitem" className={item} onClick={() => run("export")}>Markdown version</button>
              <div className="my-1 border-t border-line" />
              <button role="menuitem" className={`${item} text-risk`} onClick={() => { setMenu(false); setResult({ kind: "confirm-delete" }); }}>
                Delete briefing
              </button>
            </div>
          )}
        </div>
      </div>

      {result && result.kind !== "pdf" && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/20 p-4" onClick={close}>
          <div role="dialog" className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 overflow-y-auto rounded-xl bg-surface p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}>
            {result.kind === "confirm-delete" && <>
              <h2 className="text-lg font-semibold">Delete this briefing?</h2>
              <p className="text-sm text-muted">It is removed from your list along with its chat and tasks. The audit log keeps a record
                that it existed and was deleted.</p>
              <div className="flex gap-2">
                <button className="rounded-lg bg-risk px-4 py-2 text-sm font-medium text-white disabled:opacity-50" disabled={busy === "delete"}
                  onClick={remove}>{busy === "delete" ? "Deleting…" : "Delete"}</button>
                <button className="rounded-lg border border-line px-4 py-2 text-sm" onClick={close}>Cancel</button>
              </div>
            </>}
            {result.kind === "task-form" && (
              <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); run("create_task", { description: desc, due_date: due || null }); }}>
                <h2 className="text-lg font-semibold">Create a task</h2>
                <SuggestedTasks runId={runId} user={user} onAdded={(t) => onTaskCreated?.(t)}
                  onEdit={(d, dueDate) => { setDesc(d); setDue(dueDate); document.getElementById("task-desc")?.focus(); }} />
                <p className="text-xs font-medium uppercase tracking-wide text-muted">Or write your own</p>
                <label className="flex flex-col gap-1 text-sm">Description
                  <input id="task-desc" required value={desc} onChange={(e) => setDesc(e.target.value)} className="rounded-md border border-line px-3 py-2"
                    placeholder="e.g. Confirm the agreement renewal date with procurement" />
                </label>
                <label className="flex flex-col gap-1 text-sm">Due date
                  <input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-fit rounded-md border border-line px-3 py-2" />
                </label>
                <div className="flex gap-2">
                  <button type="submit" className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white">Create task</button>
                  <button type="button" className="rounded-lg border border-line px-4 py-2 text-sm" onClick={close}>Cancel</button>
                </div>
              </form>
            )}
            {result.kind === "email" && <>
              <h2 className="text-lg font-semibold">Draft email <span className="text-sm font-normal text-muted">({result.status})</span></h2>
              <p className="text-sm"><span className="text-muted">Subject: </span>{result.subject}</p>
              <textarea id="email-body" readOnly value={result.body} rows={12} className="w-full rounded-md border border-line p-3 text-sm leading-relaxed" />
              <button className="w-fit rounded-lg border border-line px-3 py-1.5 text-sm"
                onClick={() => navigator.clipboard?.writeText(`${result.subject}\n\n${result.body}`).catch(() => {})}>Copy</button>
            </>}
            {result.kind === "task" && <>
              <h2 className="text-lg font-semibold">Task created</h2>
              <p className="text-sm"><span className="font-mono">{result.task_id}</span>: {result.description}{result.due_date ? `, due ${result.due_date}` : ""}</p>
              <p className="text-xs text-muted">Added to the Tasks panel on this page and to your Tasks list. In production it would be
                created in the bank&apos;s CRM after approval.</p>
            </>}
            {result.kind === "export" && <>
              <h2 className="text-lg font-semibold">Markdown version</h2>
              <pre className="max-h-[50vh] overflow-auto rounded-md bg-canvas p-3 font-mono text-xs whitespace-pre-wrap">{result.markdown}</pre>
              <button className="w-fit rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
                onClick={() => saveBlob(result.filename, new Blob([result.markdown], { type: "text/markdown" }))}>
                Download {result.filename}
              </button>
            </>}
            {result.kind === "schedule" && <>
              <h2 className="text-lg font-semibold">Automatic briefing scheduled</h2>
              <p className="text-sm">A fresh briefing will be prepared at <span className="font-mono">{result.trigger_at}</span>, before the meeting at <span className="font-mono">{result.meeting_start}</span>.</p>
              <p className="text-xs text-muted">{result.status}</p>
            </>}
            {result.kind === "error" && <p className="text-sm text-risk">{result.message}</p>}
            {!["confirm-delete", "task-form"].includes(result.kind) && (
              <button className="mt-1 w-fit text-sm text-muted hover:text-ink" onClick={close}>Close</button>
            )}
          </div>
        </div>
      )}
      {result?.kind === "pdf" && (
        <div role="status" className="fixed bottom-4 right-4 z-40 flex items-center gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm shadow-lg">
          <span>Downloaded <span className="font-mono text-xs">{result.filename}</span></span>
          <button className="text-muted hover:text-ink" onClick={close} aria-label="Dismiss">✕</button>
        </div>
      )}
    </>
  );
}

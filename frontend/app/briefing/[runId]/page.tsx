"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActionsBar } from "@/components/Actions";
import { ChatPanel } from "@/components/Chat";
import { EvidenceDrawer } from "@/components/Evidence";
import { PlanTimeline } from "@/components/Plan";
import { SectionCard, UncertaintyPanel } from "@/components/Sections";
import { TasksPanel } from "@/components/Tasks";
import { WorkingDots } from "@/components/WorkingDots";
import { ApiError, apiGet, streamUrl } from "@/lib/api";
import { formatMeeting } from "@/lib/format";
import { engineLabel, useModels } from "@/lib/models";
import { SECTION_ORDER, type Evidence, type Plan, type Section, type Task, type TaskStatus } from "@/lib/types";
import { useUser } from "@/lib/user";

type Start = { client_name: string; meeting: string; mode: string; user: { name: string; clearance: string } };

const count = (s?: Section) => (s?.status === "ok" ? s.statements.filter((x) => !x.empty).length : undefined);

/** Summary tiles: what needs attention, before the detail. Each jumps to its section. */
function AtAGlance({ sections }: { sections: Record<string, Section> }) {
  const tiles = [
    { id: "metrics", label: "Material signals", value: count(sections.metrics), tone: "text-ink" },
    { id: "commitments", label: "Asks and promises", value: count(sections.commitments), tone: "text-ink" },
    { id: "opportunities", label: "Opportunities", value: count(sections.opportunities), tone: "text-accent" },
    { id: "uncertainty", label: "Needs attention", value: count(sections.uncertainty), tone: "text-warn" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map((t) => (
        <a key={t.id} href={`#sec-${t.id}`}
          className="flex flex-col gap-0.5 rounded-xl border border-line bg-surface px-4 py-3 hover:border-accent">
          <span className="text-xs text-muted">{t.label}</span>
          <span className={`text-2xl font-semibold tabular-nums ${t.tone}`}>
            {t.value ?? <span className="inline-block h-6 w-8 rounded bg-canvas align-middle animate-pulse-soft" />}
          </span>
        </a>
      ))}
    </div>
  );
}

export default function BriefingPage() {
  const { runId } = useParams<{ runId: string }>();
  const { user } = useUser();
  const models = useModels();
  const [start, setStart] = useState<Start | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tasks, setTasks] = useState<Record<string, TaskStatus>>({});
  const [sections, setSections] = useState<Record<string, Section>>({});
  const [arrived, setArrived] = useState<Record<string, number>>({});
  const [evidence, setEvidence] = useState<Record<string, Evidence>>({});
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [taskList, setTaskList] = useState<Task[]>([]);
  const t0 = useRef<number>(0);

  useEffect(() => {
    if (!done || !user) return;
    apiGet<Task[]>(`/api/briefings/${runId}/tasks`, user.user_id).then(setTaskList).catch(() => setTaskList([]));
  }, [done, runId, user]);
  const upsertTask = useCallback((t: Task) =>
    setTaskList((all) => (all.some((x) => x.task_id === t.task_id) ? all.map((x) => (x.task_id === t.task_id ? { ...x, ...t } : x)) : [...all, t])), []);

  useEffect(() => {
    if (!user) return;
    t0.current = performance.now();
    const es = new EventSource(streamUrl(runId, user.user_id));
    // Only server messages carry data. The browser also fires a plain "error" event (no data) when the connection
    // drops, e.g. a backend restart; that one is handled by es.onerror below, not parsed here.
    const on = (kind: string, fn: (d: never) => void) =>
      es.addEventListener(kind, (e) => {
        const data = (e as MessageEvent).data;
        if (typeof data !== "string" || !data) return;
        try { fn(JSON.parse(data) as never); } catch { /* malformed message: ignore it rather than crash the page */ }
      });
    on("start", (d: Start) => setStart(d));
    on("plan", (d: Plan) => setPlan(d));
    on("task", (d: { id: string; status: TaskStatus }) => setTasks((t) => ({ ...t, [d.id]: d.status })));
    on("section", (d: Section) => {
      setSections((s) => ({ ...s, [d.id]: d }));
      setArrived((a) => (a[d.id] !== undefined ? a : { ...a, [d.id]: (performance.now() - t0.current) / 1000 }));
      if (d.evidence) setEvidence((ev) => ({ ...ev, ...d.evidence }));
    });
    on("error", (d: { message: string }) => setError(d.message));
    on("end", () => { setDone(true); es.close(); });
    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED) return;      // the browser is retrying by itself
      apiGet(`/api/briefings/${runId}`, user.user_id).catch((e: unknown) => {
        const status = e instanceof ApiError ? e.status : 0;
        setError(status === 404 ? "This briefing is no longer available. It may have been deleted; go back to Clients and prepare it again."
          : status === 403 ? "This briefing belongs to another user. Switch back to the user who prepared it, or prepare your own."
          : "Could not reach the briefing service. Check that the backend is running, then reload this page.");
      });
    };
    return () => es.close();
  }, [runId, user]);

  const addEvidence = useCallback((ev: Record<string, Evidence>) => setEvidence((e) => ({ ...e, ...ev })), []);
  const open = useCallback((id: string) => setOpenId(id), []);
  const total = plan?.tasks.length ?? 0;
  const finished = Object.values(tasks).filter((s) => s === "done" || s === "unavailable").length;

  // Nothing ever arrived (deleted briefing, another user's, backend down): show the message, not a page of
  // placeholders whose "working" dots would suggest something is still happening.
  if (error && !start) {
    return (
      <div className="flex max-w-2xl flex-col gap-4">
        <Link href="/" className="text-sm text-muted hover:text-ink">← Clients</Link>
        <h1 className="text-2xl font-semibold tracking-tight">Briefing not available</h1>
        <p className="rounded-md bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>
        <Link href="/" className="w-fit rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">Back to clients</Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link href="/" className="text-sm text-muted hover:text-ink">← Clients</Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{start?.client_name ?? "Preparing briefing…"}</h1>
          {start && (
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
              <span>{formatMeeting(start.meeting)}</span>
              <span aria-hidden="true">·</span>
              <span>for {start.user.name} ({start.user.clearance})</span>
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] ${done ? "bg-ok-soft text-ok" : "bg-info-soft text-info"}`}>
                {done ? "complete" : <><WorkingDots /> agents working {finished}/{total || "…"}</>}
              </span>
              <span className="rounded-full bg-canvas px-2 py-0.5 font-mono text-[10px]">
                {engineLabel(start.mode, models)}
              </span>
            </p>
          )}
        </div>
        {user && <ActionsBar runId={runId} user={user.user_id} ready={done} onTaskCreated={upsertTask} />}
      </div>

      {error && <p className="rounded-md bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>}

      <AtAGlance sections={sections} />

      {/* Plan on the left (wide screens), the briefing in the middle, chat on the right and always in view
          (sticky), so it is visible as soon as the page opens. On a phone they stack: briefing, then chat. */}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[220px_minmax(0,1fr)_400px]">
        <aside className="hidden xl:block">
          <div className="sticky top-6"><PlanTimeline plan={plan} status={tasks} done={done} live={start?.mode === "anthropic"} /></div>
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <div className="xl:hidden"><PlanTimeline plan={plan} status={tasks} done={done} live={start?.mode === "anthropic"} /></div>
          {SECTION_ORDER.map((id) => (
            <SectionCard key={id} id={id} section={sections[id]} arrivedAt={arrived[id]} status={tasks} onOpen={open} />
          ))}
          <UncertaintyPanel section={sections.uncertainty} onOpen={open} />
          {done && user && <TasksPanel tasks={taskList} runId={runId} user={user.user_id} onChange={upsertTask} />}
        </div>

        <aside className="min-w-0">
          <div className="h-[70vh] lg:sticky lg:top-6 lg:h-[calc(100vh-3rem)]">
            {user && <ChatPanel runId={runId} user={user.user_id} ready={done} onEvidence={addEvidence} onOpen={open} />}
          </div>
        </aside>
      </div>

      <EvidenceDrawer evidence={openId ? evidence[openId] ?? null : null} onClose={() => setOpenId(null)} />
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { RecentBriefings } from "@/components/RecentBriefings";
import { apiGet, apiPost } from "@/lib/api";
import { ago, when } from "@/lib/format";
import { engineLabel, useModels } from "@/lib/models";
import type { BriefingSummary, ClientSnapshot } from "@/lib/types";
import { useUser } from "@/lib/user";

/** Demo controls, kept out of the way in a small menu. */
function DemoOptions({ mode, setMode, failNews, setFailNews, live }: {
  mode: "live" | "offline"; setMode: (m: "live" | "offline") => void;
  failNews: boolean; setFailNews: (v: boolean) => void; live: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const models = useModels();
  const summary = `${mode === "live" ? engineLabel("anthropic", models) : "Offline"}${failNews ? " · news failure on" : ""}`;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="rounded-lg border border-line bg-surface px-3 py-2 text-sm hover:border-accent">
        Demo options <span className="text-muted">· {summary}</span> ▾
      </button>
      {open && (
        <fieldset className="absolute right-0 z-30 mt-1 flex w-80 flex-col gap-3 rounded-lg border border-line bg-surface p-4 text-sm shadow-lg">
          <legend className="sr-only">Demo options</legend>
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">Engine</span>
            <label className="flex items-start gap-2">
              <input type="radio" id="mode-live" name="mode" checked={mode === "live"} onChange={() => setMode("live")} disabled={!live} className="mt-1" />
              <span>{models.opus} + {models.haiku} (live)<span className="block text-xs text-muted">About 50 s, writes naturally. {models.opus} plans and writes; {models.haiku} reads the emails</span></span>
            </label>
            <label className="flex items-start gap-2">
              <input type="radio" id="mode-offline" name="mode" checked={mode === "offline"} onChange={() => setMode("offline")} className="mt-1" />
              <span>Offline (rules + templates)<span className="block text-xs text-muted">Under 2 s, no AI; the safety net</span></span>
            </label>
          </div>
          <label className="flex items-start gap-2 border-t border-line pt-3">
            <input type="checkbox" id="fail-news" checked={failNews} onChange={(e) => setFailNews(e.target.checked)} className="mt-1" />
            <span>Simulate news agent failure<span className="block text-xs text-muted">Shows retry, then &ldquo;unavailable&rdquo;</span></span>
          </label>
        </fieldset>
      )}
    </div>
  );
}

/** Small "→" that slides right when its card is hovered, so the card reads as clickable. */
function Arrow() {
  return (
    <span aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent transition-transform duration-200 group-hover:translate-x-1 group-hover:bg-accent group-hover:text-white">
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 8h10M9 4l4 4-4 4" />
      </svg>
    </span>
  );
}

/** One client. The whole card is clickable: it opens the latest briefing, or prepares one. */
function ClientCard({ c, last, starting, onPrepare }: {
  c: ClientSnapshot; last?: BriefingSummary; starting: boolean; onPrepare: () => void;
}) {
  const router = useRouter();
  const next = c.meetings[0];
  const primary = () => (last ? router.push(`/briefing/${last.run_id}`) : onPrepare());
  return (
    <article className="group relative flex flex-col gap-4 rounded-xl border border-line bg-surface p-5 transition-shadow hover:border-accent hover:shadow-md">
      <button onClick={primary} disabled={starting} className="absolute inset-0 rounded-xl"
        aria-label={last ? `Open the latest briefing for ${c.client_name}` : `Prepare a briefing for ${c.client_name}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-snug">{c.client_name}</h2>
          <p className="text-sm text-muted">{c.industry} · {c.segment} · {c.tier} tier</p>
        </div>
        <Arrow />
      </div>

      {next ? (
        <div className="rounded-lg bg-canvas px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Upcoming meeting</p>
          <p className="text-sm"><span className="font-medium text-accent">{when(next.start_time)}</span> · {next.title}</p>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-line px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted">No meeting booked</p>
          <p className="text-sm text-muted">You can still prepare a catch-up briefing.</p>
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-sm">
        <span className="font-medium text-accent">
          {starting ? "Starting…" : last ? `Open briefing · ${ago(last.created_at)}` : next ? "Prepare briefing" : "Prepare catch-up briefing"}
        </span>
        {last && (
          <button onClick={onPrepare} disabled={starting}
            className="relative z-10 rounded-md border border-line px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent disabled:opacity-50">
            Prepare a fresh one
          </button>
        )}
      </div>
    </article>
  );
}

export default function Home() {
  const { user, health } = useUser();
  const router = useRouter();
  const [clients, setClients] = useState<ClientSnapshot[] | null>(null);
  const [recent, setRecent] = useState<BriefingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"live" | "offline">("live");
  const [failNews, setFailNews] = useState(false);
  const [starting, setStarting] = useState<string | null>(null);
  const live = health?.llm_mode === "anthropic";

  useEffect(() => {
    if (health && !live) setMode("offline");
  }, [health, live]);

  useEffect(() => {
    if (!user) return;
    setClients(null);
    setRecent(null);
    apiGet<ClientSnapshot[]>("/api/clients", user.user_id).then(setClients).catch((e) => setError(String(e)));
    apiGet<BriefingSummary[]>("/api/briefings", user.user_id).then(setRecent).catch(() => setRecent([]));
  }, [user]);

  // the newest finished briefing for the client's next meeting (or its latest catch-up when no meeting is
  // booked), so it can be reopened instead of regenerated
  const lastFor = (c: ClientSnapshot) => recent?.find((b) => b.status === "complete" && b.client_id === c.client_id
    && b.meeting_id === (c.meetings[0]?.meeting_id ?? null));

  /** Brief a client: for its next meeting if it has one, otherwise a catch-up with no meeting. */
  async function prepare(c: ClientSnapshot) {
    if (!user || starting !== null) return;
    setStarting(c.client_id);
    const meeting = c.meetings[0]?.meeting_id;
    try {
      const { run_id } = await apiPost<{ run_id: string }>("/api/briefings", {
        ...(meeting ? { meeting_id: meeting } : { client_id: c.client_id }),
        mode: mode === "offline" ? "offline" : undefined,
        fail_tasks: failNews ? ["news"] : [],
      }, user.user_id);
      router.push(`/briefing/${run_id}`);
    } catch (e) {
      setError(String(e));
      setStarting(null);
    }
  }

  const upcoming = clients?.filter((c) => c.meetings.length) ?? [];
  const others = clients?.filter((c) => !c.meetings.length) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Upcoming clients</h1>
          <p className="text-sm text-muted">
            Upcoming meetings · {user ? `${user.name} (${user.clearance}) · ` : ""}Monday 16 November 2026 · only clients you cover
          </p>
        </div>
        <DemoOptions mode={mode} setMode={setMode} failNews={failNews} setFailNews={setFailNews} live={live} />
      </div>

      {error && <p className="rounded-md bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>}
      {!clients && !error && <p className="text-sm text-muted">Loading your clients…</p>}
      {clients && !upcoming.length && <p className="text-sm text-muted">None of your clients has a meeting coming up.</p>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {upcoming.map((c) => (
          <ClientCard key={c.client_id} c={c} last={lastFor(c)} starting={starting === c.client_id} onPrepare={() => prepare(c)} />
        ))}
      </div>

      {others.length > 0 && (
        <section className="flex flex-col gap-3">
          <div>
            <h2 className="text-base font-semibold">Other clients you cover</h2>
            <p className="text-xs text-muted">No meeting booked. You can still prepare a catch-up briefing, for a call or a quick check.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {others.map((c) => (
              <ClientCard key={c.client_id} c={c} last={lastFor(c)} starting={starting === c.client_id} onPrepare={() => prepare(c)} />
            ))}
          </div>
        </section>
      )}

      {user && (
        <RecentBriefings items={recent} user={user.user_id}
          onDeleted={(id) => setRecent((r) => r?.filter((b) => b.run_id !== id) ?? null)} />
      )}
    </div>
  );
}

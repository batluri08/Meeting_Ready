"use client";

import { StatementText } from "@/components/Evidence";
import { LABEL } from "@/components/Plan";
import { WorkingDots } from "@/components/WorkingDots";
import { SECTION_NEEDS, SECTION_QUESTIONS, SECTION_TITLES, type Section, type Statement, type TaskStatus } from "@/lib/types";

/** A section's content: the direct answer first (highlighted), then the labelled points as a list or a
 *  two-column table (the writer picks), then "why it matters". Sections without roles (offline mode, older
 *  briefings) are shown as a plain list. */
function SectionBody({ section, onOpen }: { section: Section; onOpen: (id: string) => void }) {
  const st = section.statements;
  const answer = st.filter((s) => s.role === "answer");
  const why = st.filter((s) => s.role === "why");
  const points = st.filter((s) => s.role !== "answer" && s.role !== "why");
  const labelled = points.some((s) => s.label);

  const plain = (items: Statement[]) => (
    <ul className="flex flex-col divide-y divide-line text-[14.5px] leading-relaxed">
      {items.map((s, i) => (
        <li key={i} className="py-2 first:pt-0 last:pb-0">
          {s.label && <span className="font-semibold">{s.label}: </span>}
          <StatementText s={s} onOpen={onOpen} />
        </li>
      ))}
    </ul>
  );

  return (
    <div className="flex flex-col gap-3">
      {answer.map((s, i) => (
        <div key={i} className="rounded-lg border-l-[3px] border-accent bg-accent-soft/50 px-4 py-2.5">
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-accent">Answer</p>
          <p className="text-[15px] font-medium leading-relaxed"><StatementText s={s} onOpen={onOpen} /></p>
        </div>
      ))}

      {points.length > 0 && (section.layout === "table" && labelled ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[14px] leading-relaxed">
            <tbody>
              {points.map((s, i) => (
                <tr key={i} className="border-b border-line last:border-0 align-top">
                  <th scope="row" className="w-[28%] py-2 pr-4 font-semibold">{s.label}</th>
                  <td className="py-2"><StatementText s={s} onOpen={onOpen} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : plain(points))}

      {why.map((s, i) => (
        <p key={i} className="rounded-lg bg-warn-soft/60 px-4 py-2 text-[14px] leading-relaxed">
          <span className="font-semibold text-warn">Why it matters: </span><StatementText s={s} onOpen={onOpen} />
        </p>
      ))}
    </div>
  );
}

/** What a section is waiting for, in words: the agents still gathering, or the writer. */
function waitingText(id: string, status: Record<string, TaskStatus>): string {
  const pending = (SECTION_NEEDS[id] ?? []).filter((t) => !["done", "unavailable"].includes(status[t] ?? ""));
  if (!Object.keys(status).length) return "Planning";
  return pending.length ? `Waiting for ${pending.map((t) => LABEL[t] ?? t).join(" and ")}` : "Writing this section";
}

/** One briefing question. Shows animated dots and what it is waiting for until its section arrives. */
export function SectionCard({ id, section, arrivedAt, status, onOpen }: {
  id: string; section?: Section; arrivedAt?: number; status: Record<string, TaskStatus>; onOpen: (id: string) => void;
}) {
  return (
    <section id={`sec-${id}`} className="scroll-mt-20 lg:scroll-mt-6 rounded-xl border border-line bg-surface">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold">{SECTION_TITLES[id]}</h2>
          <p className="text-xs text-muted">Q: {SECTION_QUESTIONS[id]}</p>
        </div>
        {arrivedAt !== undefined
          ? <span className="shrink-0 font-mono text-[10px] text-muted" title="Arrived after">{arrivedAt.toFixed(1)}s</span>
          : <WorkingDots className="shrink-0 text-accent" />}
      </header>
      <div className="px-5 py-3">
        {!section && (
          <div className="flex flex-col gap-2 py-1" aria-busy="true">
            <p className="text-xs text-muted">{waitingText(id, status)}…</p>
            <div className="h-3 w-11/12 rounded bg-canvas animate-pulse-soft" />
            <div className="h-3 w-8/12 rounded bg-canvas animate-pulse-soft" />
          </div>
        )}
        {section?.status === "unavailable" && (
          <p className="text-sm text-risk">
            Unavailable: the agent behind this section failed twice. Everything else is complete; the gap is listed under
            &ldquo;What is uncertain&rdquo;.
          </p>
        )}
        {section?.status === "ok" && <SectionBody section={section} onOpen={onOpen} />}
        {section && section.dropped.length > 0 && (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer">Verifier removed {section.dropped.length} unsupported statement(s)</summary>
            <ul className="mt-2 flex flex-col gap-1.5">
              {section.dropped.map((d, i) => (
                <li key={i}><span className="line-through">{d.text}</span> <span className="text-risk">({d.reason})</span></li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}

const KIND_BADGE: Record<string, { label: string; cls: string }> = {
  conflict: { label: "Conflict", cls: "bg-warn-soft text-warn" },
  stale: { label: "Out of date", cls: "bg-warn-soft text-warn" },
  restricted: { label: "Restricted", cls: "bg-risk-soft text-risk" },
  low_confidence: { label: "Low confidence", cls: "bg-info-soft text-info" },
  security: { label: "Security", cls: "bg-risk-soft text-risk" },
  unavailable: { label: "Unavailable", cls: "bg-risk-soft text-risk" },
  gap: { label: "Gap", cls: "bg-info-soft text-info" },
};
const PREFIXES = ["Conflicting information: ", "Out of date: ", "Unavailable: "];

export function UncertaintyPanel({ section, onOpen }: { section?: Section; onOpen: (id: string) => void }) {
  return (
    <section id="sec-uncertainty" className="scroll-mt-20 lg:scroll-mt-6 rounded-xl border border-warn/40 bg-surface">
      <header className="border-b border-line px-5 py-3">
        <h2 className="text-[15px] font-semibold">What is uncertain</h2>
        <p className="text-xs text-muted">Shown, never hidden: conflicts, stale facts, restricted data, gaps.</p>
      </header>
      <div className="px-5 py-3">
        {!section && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <WorkingDots className="text-warn" /> Assembled once every agent has finished
          </p>
        )}
        <ul className="flex flex-col divide-y divide-line">
          {section?.statements.map((s, i) => {
            const badge = KIND_BADGE[s.kind ?? ""];
            const text = badge ? PREFIXES.reduce((t, p) => (t.startsWith(p) ? t.slice(p.length) : t), s.text) : s.text;
            return (
              <li key={i} className="flex flex-col gap-1 py-2.5 text-[13.5px] leading-relaxed first:pt-0 last:pb-0">
                {badge && <span className={`w-fit rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${badge.cls}`}>{badge.label}</span>}
                <StatementText s={{ ...s, text }} onOpen={onOpen} />
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

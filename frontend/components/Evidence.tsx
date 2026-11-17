"use client";

import { useEffect, useState } from "react";
import type { Evidence, Statement } from "@/lib/types";

/** Citation chips after a statement. Shows two, then "+N" to expand. Clicking a chip opens the evidence drawer. */
export function Citations({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) {
  const [all, setAll] = useState(false);
  if (!ids.length) return null;
  const shown = all ? ids : ids.slice(0, 2);
  const chip = "rounded px-1 py-px font-mono text-[10px] leading-4 align-[1px]";
  return (
    <span className="ml-1 inline-flex flex-wrap gap-0.5">
      {shown.map((id) => (
        <button key={id} onClick={() => onOpen(id)} title="Open the source of this statement"
          className={`${chip} bg-canvas text-muted hover:bg-accent hover:text-white`}>
          {id}
        </button>
      ))}
      {!all && ids.length > 2 && (
        <button onClick={() => setAll(true)} title={`Show ${ids.length - 2} more sources`}
          className={`${chip} text-muted hover:text-accent`}>+{ids.length - 2}</button>
      )}
    </span>
  );
}

/** A statement with its citations (no list item: callers choose the wrapper). */
export function StatementText({ s, onOpen }: { s: Statement; onOpen: (id: string) => void }) {
  return (
    <span>
      <span className={s.empty ? "text-muted italic" : ""}>{s.text}</span>
      <Citations ids={s.evidence_ids} onOpen={onOpen} />
    </span>
  );
}

const KIND_LABEL: Record<string, string> = {
  signal: "Materiality rule", profile: "Client record", change: "Change since last meeting", action: "Open action",
  deal: "Pipeline deal", doc: "Document passage", claim: "Statement in a document", news: "Approved news",
  opportunity: "Opportunity basis", sql: "Query result", match: "Entity match", restricted: "Restricted (count only)",
  security: "Security event", system: "System",
};

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="text-sm text-muted">No rows.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full text-left text-xs">
        <thead className="bg-canvas text-muted">
          <tr>{cols.map((c) => <th key={c} className="px-2 py-1.5 font-mono font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((r, i) => (
            <tr key={i} className="border-t border-line">
              {cols.map((c) => <td key={c} className="whitespace-nowrap px-2 py-1.5 font-mono tabular-nums">{String(r[c] ?? "")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Slide-over showing exactly where a fact came from. */
export function EvidenceDrawer({ evidence, onClose }: { evidence: Evidence | null; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!evidence) return null;
  const s = evidence.source;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/20" onClick={onClose}>
      <aside role="dialog" aria-label={`Evidence ${evidence.id}`} onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-xl flex-col gap-4 overflow-y-auto bg-surface p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-accent">{evidence.id} · {KIND_LABEL[evidence.kind] ?? evidence.kind}</p>
            <h2 className="mt-1 text-lg font-semibold">{evidence.title}</h2>
          </div>
          <button onClick={onClose} className="rounded-md border border-line px-2.5 py-1 text-sm text-muted hover:text-ink">Close</button>
        </div>
        {evidence.restricted && (
          <p className="rounded-md bg-risk-soft px-3 py-2 text-sm text-risk">Restricted record: visible only with senior clearance.</p>
        )}
        <div className="rounded-lg bg-canvas p-4 text-sm leading-relaxed whitespace-pre-wrap">{evidence.text}</div>

        {s.type === "sql" && (
          <div className="flex flex-col gap-3">
            {s.rule && (
              <p className="text-sm"><span className="text-muted">Rule </span><span className="font-mono">{s.rule}</span>
                <span className="text-muted"> · value </span><span className="font-mono">{String(s.value)}</span>
                <span className="text-muted"> · threshold </span><span className="font-mono">{String(s.threshold)}</span></p>
            )}
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Query that produced this</p>
              <pre className="overflow-x-auto rounded-md bg-ink p-3 font-mono text-xs leading-relaxed text-white whitespace-pre-wrap">{s.query}</pre>
              {s.params && s.params.length > 0 && <p className="mt-1 font-mono text-xs text-muted">params: {JSON.stringify(s.params)}</p>}
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Rows returned</p>
              <RowsTable rows={s.rows ?? []} />
            </div>
            {s.refs && s.refs.length > 0 && (
              <p className="text-xs text-muted">Source records: <span className="font-mono">{s.refs.join(", ")}</span></p>
            )}
          </div>
        )}

        {s.type === "doc" && (
          <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted">Document</dt><dd className="font-mono">{s.doc_id}</dd>
            {s.doc_type && <><dt className="text-muted">Type</dt><dd>{s.doc_type}</dd></>}
            {s.title && <><dt className="text-muted">Title</dt><dd>{s.title}</dd></>}
            {s.date && <><dt className="text-muted">Date</dt><dd className="font-mono">{s.date}</dd></>}
            {s.section && <><dt className="text-muted">Where</dt><dd>{s.section}</dd></>}
            {!s.section && s.page && <><dt className="text-muted">Page</dt><dd>{s.page}</dd></>}
            {s.chunk_id && <><dt className="text-muted">Chunk</dt><dd className="font-mono">{s.chunk_id}</dd></>}
            {s.sources && <><dt className="text-muted">Outlets</dt><dd>{s.sources.join(" · ")}</dd></>}
            {s.found_by && <><dt className="text-muted">Found by</dt><dd className="text-muted">{s.found_by}</dd></>}
          </dl>
        )}
      </aside>
    </div>
  );
}

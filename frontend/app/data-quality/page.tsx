"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useUser } from "@/lib/user";

type Match = {
  source_system: string; source_id: string; source_name: string; source_domain: string | null;
  client_id: string | null; candidate_client_id: string | null; client_name: string | null;
  match_method: string; confidence: number; status: string; reason: string;
};

const SYSTEMS: { id: string; label: string }[] = [{ id: "crm", label: "CRM" }, { id: "billing", label: "Billing" }];

/** Same name after lower-casing and removing legal words? If not, the systems spell it differently. */
function spelledDifferently(source: string, client: string | null) {
  const clean = (s: string) => s.toLowerCase().replace(/[^a-z ]/g, "").replace(/\b(ltd|limited|plc|pvt|grp|group)\b/g, "").replace(/\s+/g, " ").trim();
  return !!client && clean(source) !== clean(client);
}

/** Why a record was linked, in a few words. */
function why(m: Match): string {
  if (m.status === "master") return "Main record: the client is defined here";
  if (m.status === "review") return "No website to check; a person must decide";
  if (m.status === "unmatched") return "Not linked to any client";
  if (m.match_method === "domain+name") return `Same website (${m.source_domain}) and same name`;
  if (m.match_method === "domain") return `Same website (${m.source_domain})`;
  return m.reason;
}

function Tile({ value, label, tone = "" }: { value: number | string; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <p className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  );
}

/** One record as a small chip: a tick when linked, its name if spelled differently. */
function RecordChip({ r }: { r: Match }) {
  const odd = r.status !== "master" && spelledDifferently(r.source_name, r.client_name);
  const ok = r.status === "master" || r.status === "merged";
  return (
    <span className={`inline-flex max-w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs ${ok ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn"}`}
      title={`${r.source_id}: “${r.source_name}”. ${why(r)}`}>
      <span aria-hidden="true">{ok ? "✓" : "?"}</span>
      <span className="truncate">{odd ? `as “${r.source_name}”` : r.status === "master" ? "main record" : "linked"}</span>
    </span>
  );
}

export default function DataQuality() {
  const { user } = useUser();
  const [rows, setRows] = useState<Match[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setRows(null);
    apiGet<Match[]>("/api/matches", user.user_id).then(setRows).catch((e) => setError(String(e)));
  }, [user]);

  const review = rows?.filter((r) => r.status === "review") ?? [];
  const clients = new Map<string, Match[]>();
  rows?.forEach((r) => {
    const key = r.client_name ?? r.source_name;
    clients.set(key, [...(clients.get(key) ?? []), r]);
  });
  const linked = rows?.filter((r) => r.status === "merged").length ?? 0;
  const spelled = rows?.filter((r) => r.status === "merged" && spelledDifferently(r.source_name, r.client_name)).length ?? 0;
  const systems = new Set(rows?.map((r) => r.source_system)).size;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Do we have the right records for each client?</h1>
        <p className="max-w-3xl text-[15px] text-muted">
          Each bank system names clients its own way (the CRM says &ldquo;Kestrel Foods Ltd&rdquo;, billing says
          &ldquo;KESTREL FDS LTD&rdquo;). Before a briefing uses them, the system links each record to the right client.
        </p>
      </div>

      {error && <p className="rounded-md bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>}
      {!rows && !error && <p className="text-sm text-muted">Loading…</p>}

      {rows && (
        <>
          <section className={`flex w-fit max-w-full items-center gap-2.5 rounded-lg border px-3 py-1.5 ${review.length ? "border-warn/50 bg-warn-soft/50" : "border-ok/40 bg-ok-soft/50"}`}>
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white ${review.length ? "bg-warn" : "bg-ok"}`} aria-hidden="true">
              {review.length ? "!" : "✓"}
            </span>
            <p className="text-sm">
              {review.length
                ? <><span className="font-semibold">{review.length} record{review.length > 1 ? "s need" : " needs"} a decision.</span> Everything else is linked.</>
                : <><span className="font-semibold">All records are linked to the right client.</span> Nothing is waiting for a person.</>}
            </p>
          </section>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile value={clients.size} label="your clients" />
            <Tile value={rows.length} label={`records from ${systems} systems`} />
            <Tile value={linked} label="linked automatically" tone="text-ok" />
            <Tile value={spelled} label="spelled differently, still linked" />
          </div>

          {review.length > 0 && (
            <section className="rounded-xl border border-warn/50 bg-surface p-5">
              <h2 className="text-[15px] font-semibold text-warn">Needs a decision</h2>
              <ul className="mt-2 flex flex-col gap-2">
                {review.map((r) => (
                  <li key={r.source_id} className="text-sm leading-relaxed">
                    Is billing&apos;s <span className="font-medium">&ldquo;{r.source_name}&rdquo;</span> the same as{" "}
                    <span className="font-medium">{r.client_name}</span>? No website to confirm ({Math.round(r.confidence * 100)}% sure),
                    so its revenue stays out of briefings until a person decides.
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-line">
                  <th className="px-5 py-2.5 font-medium">Client</th>
                  {SYSTEMS.map((s) => <th key={s.id} className="px-4 py-2.5 font-medium">{s.label}</th>)}
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {[...clients.entries()].map(([name, recs]) => {
                  const waiting = recs.some((r) => r.status === "review" || r.status === "unmatched");
                  return (
                    <tr key={name} className="border-b border-line align-top last:border-0">
                      <td className="px-5 py-3">
                        <details>
                          <summary className="cursor-pointer font-medium">{name}</summary>
                          <ul className="mt-2 flex flex-col gap-1.5 text-xs text-muted">
                            {recs.map((r) => (
                              <li key={`${r.source_system}-${r.source_id}`}>
                                <span className="font-mono">{r.source_id}</span> &ldquo;{r.source_name}&rdquo;: {why(r)}
                                {r.status !== "master" && ` (${Math.round(r.confidence * 100)}% sure)`}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </td>
                      {SYSTEMS.map((s) => {
                        const inSys = recs.filter((r) => r.source_system === s.id);
                        return (
                          <td key={s.id} className="px-4 py-3">
                            <div className="flex flex-col items-start gap-1">
                              {inSys.length ? inSys.map((r) => <RecordChip key={r.source_id} r={r} />) : <span className="text-xs text-muted">–</span>}
                            </div>
                          </td>
                        );
                      })}
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium ${waiting ? "text-warn" : "text-ok"}`}>
                          {waiting ? "Needs a decision" : recs.length > 1 ? `All ${recs.length} records linked` : "One record"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
          <p className="-mt-3 text-xs text-muted">Click a client for each record and why it was linked. Hover a record for its ID.</p>

          <details className="rounded-xl border border-line bg-surface px-5 py-3">
            <summary className="cursor-pointer text-sm font-medium">How records are linked</summary>
            <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-sm text-muted">
              <li><span className="text-ink">Compare</span> each record&apos;s website and its name, with words like Ltd and PLC removed.</li>
              <li><span className="text-ink">Decide:</span> same website means the same company; a different website means a different company, however similar the name (Kestrel Foods is not Kestrel Fuels).</li>
              <li><span className="text-ink">Ask when unsure:</span> a name with no website to check is never linked automatically; a person decides.</li>
            </ol>
          </details>
        </>
      )}
    </div>
  );
}

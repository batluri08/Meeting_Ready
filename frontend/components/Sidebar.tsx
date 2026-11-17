"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API_BASE, apiGet } from "@/lib/api";
import type { Task } from "@/lib/types";
import { useUser } from "@/lib/user";

/** Small line icons (16px, stroke = currentColor). */
const ICONS: Record<string, React.ReactNode> = {
  clients: <><circle cx="6" cy="5.5" r="2.5" /><path d="M1.5 13.5c.6-2.3 2.3-3.5 4.5-3.5s3.9 1.2 4.5 3.5" /><path d="M11 3.2a2.4 2.4 0 0 1 0 4.6M12.5 10.3c1 .5 1.7 1.6 2 3.2" /></>,
  tasks: <><rect x="2" y="2" width="12" height="12" rx="2.5" /><path d="M5 8.2l2 2 4-4.4" /></>,
  quality: <><ellipse cx="8" cy="3.8" rx="5.5" ry="2" /><path d="M2.5 3.8v8.4c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V3.8" /><path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" /></>,
  evaluation: <><path d="M8 1.8l5.2 2v4.1c0 3.1-2.2 5.3-5.2 6.3-3-1-5.2-3.2-5.2-6.3V3.8z" /><path d="M5.6 8.1l1.7 1.7 3.2-3.4" /></>,
  design: <><rect x="1.8" y="2.5" width="12.4" height="11" rx="2" /><path d="M1.8 6h12.4M6 6v7.5" /></>,
};

function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
  );
}

const WORK = [
  { href: "/", label: "Clients", icon: "clients" },
  { href: "/tasks", label: "Tasks", icon: "tasks" },
];
const TRUST = [
  { href: "/data-quality", label: "Data quality", icon: "quality" },
  { href: "/evaluation", label: "Evaluation", icon: "evaluation" },
];
const DESIGN = [
  { href: "/architecture/prototype/prototype.html", label: "Prototype" },
  { href: "/architecture/production/production.html", label: "Production" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" || pathname.startsWith("/briefing") : pathname.startsWith(href);
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return <p className="mb-1 mt-6 hidden px-3 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-side-muted lg:block">{children}</p>;
}

/**
 * Left navigation. Work (Clients, Tasks) is prominent; Trust & data and Design are smaller and quieter
 * but always visible. On narrow screens it becomes a compact bar across the top.
 */
export function Sidebar() {
  const { users, user, setUserId, backendError } = useUser();
  const pathname = usePathname();
  const router = useRouter();
  const [openTasks, setOpenTasks] = useState<number | null>(null);

  useEffect(() => {
    if (!user) return;
    apiGet<Task[]>("/api/tasks", user.user_id)
      .then((t) => setOpenTasks(t.filter((x) => x.status !== "done").length))
      .catch(() => setOpenTasks(null));
  }, [user, pathname]);

  const item = (active: boolean, size: "main" | "small") =>
    `group relative flex items-center gap-2.5 rounded-lg px-3 ${size === "main" ? "py-2 text-[14px]" : "py-1.5 text-[13px]"} transition-colors ${
      active ? "bg-side-active text-white font-medium" : size === "main" ? "text-side-ink hover:bg-side-hover hover:text-white" : "text-side-muted hover:bg-side-hover hover:text-side-ink"}`;
  const bar = (active: boolean) => active && (
    <span aria-hidden="true" className="absolute inset-y-1.5 left-0 hidden w-[3px] rounded-full bg-side-accent lg:block" />
  );

  return (
    <aside className="sticky top-0 z-30 flex shrink-0 flex-col bg-side text-side-ink lg:h-screen lg:w-60">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-4 py-3 lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-0 lg:px-3 lg:py-5">
        <Link href="/" className="flex items-center gap-2.5 lg:px-2">
          <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-lg bg-side-accent text-side shadow-sm">
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3.5 8.5l3 3 6-7" />
            </svg>
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-[15px] font-semibold tracking-tight text-white">MeetingReady</span>
            <span className="hidden text-[11px] text-side-muted sm:block">client meeting briefings</span>
          </span>
        </Link>

        <nav className="order-last -mx-1 flex w-full items-center gap-1 overflow-x-auto lg:order-none lg:mx-0 lg:mt-2 lg:w-auto lg:flex-col lg:items-stretch lg:overflow-visible" aria-label="Main">
          <GroupLabel>Work</GroupLabel>
          {WORK.map((n) => {
            const active = isActive(pathname, n.href);
            return (
              <Link key={n.href} href={n.href} className={item(active, "main")} aria-current={active ? "page" : undefined}>
                {bar(active)}<Icon name={n.icon} /><span>{n.label}</span>
                {n.href === "/tasks" && !!openTasks && (
                  <span className="ml-auto hidden rounded-full bg-side-accent/20 px-1.5 text-[11px] font-semibold tabular-nums text-side-accent lg:inline">{openTasks}</span>
                )}
              </Link>
            );
          })}

          <GroupLabel>Trust &amp; data</GroupLabel>
          {TRUST.map((n) => {
            const active = isActive(pathname, n.href);
            return (
              <Link key={n.href} href={n.href} className={item(active, "small")} aria-current={active ? "page" : undefined}>
                {bar(active)}<Icon name={n.icon} /><span className="whitespace-nowrap">{n.label}</span>
              </Link>
            );
          })}

          <GroupLabel>Design</GroupLabel>
          {DESIGN.map((d) => (
            <a key={d.href} href={`${API_BASE}${d.href}`} target="_blank" rel="noopener noreferrer" className={`${item(false, "small")} hidden lg:flex`}
              title={`Open the ${d.label.toLowerCase()} architecture diagram in a new tab`}>
              <Icon name="design" /><span>{d.label}</span>
              <span aria-hidden="true" className="ml-auto text-[11px] opacity-60 transition-opacity group-hover:opacity-100">↗</span>
            </a>
          ))}
        </nav>

        <select aria-label="Signed in as" value={user?.user_id ?? ""}
          className="ml-auto max-w-[9rem] rounded-md border border-white/15 bg-white/5 px-2 py-1.5 text-xs text-white lg:hidden"
          onChange={(e) => { setUserId(e.target.value); if (pathname.startsWith("/briefing")) router.push("/"); }}>
          {users.map((u) => <option key={u.user_id} value={u.user_id} className="text-ink">{u.name}</option>)}
        </select>
      </div>

      <div className="mt-auto hidden border-t border-white/10 px-4 py-4 lg:block">
        {backendError && <p className="mb-2 text-xs text-[#ffb4a8]">Backend not reachable</p>}
        <label htmlFor="user-switcher" className="mb-1 block text-[10.5px] font-semibold uppercase tracking-[0.08em] text-side-muted">Signed in as</label>
        <select id="user-switcher" value={user?.user_id ?? ""}
          className="w-full rounded-lg border border-white/15 bg-white/5 px-2.5 py-2 text-sm text-white focus:border-side-accent"
          onChange={(e) => {
            setUserId(e.target.value);
            if (pathname.startsWith("/briefing")) router.push("/");   // a briefing belongs to the user who ran it
          }}>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id} className="text-ink">{u.name} ({u.clearance})</option>
          ))}
        </select>
      </div>
    </aside>
  );
}

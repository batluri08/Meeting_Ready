"use client";

import { useEffect, useState } from "react";
import { TaskRow, TODAY } from "@/components/Tasks";
import { apiGet } from "@/lib/api";
import type { Task } from "@/lib/types";
import { useUser } from "@/lib/user";

const key = (t: Task) => `${t.run_id}/${t.task_id}`;

export default function TasksPage() {
  const { user } = useUser();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setTasks(null);
    apiGet<Task[]>("/api/tasks", user.user_id).then(setTasks).catch((e) => setError(String(e)));
  }, [user]);

  const update = (t: Task) => setTasks((all) => all?.map((x) => (key(x) === key(t) ? { ...x, ...t } : x)) ?? null);
  const byDue = (a: Task, b: Task) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999");
  const open = (tasks ?? []).filter((t) => t.status === "open").sort(byDue);
  const groups = [
    { title: "Overdue", items: open.filter((t) => t.due_date && t.due_date < TODAY), tone: "text-risk" },
    { title: "Upcoming", items: open.filter((t) => !t.due_date || t.due_date >= TODAY), tone: "text-ink" },
    { title: "Done", items: (tasks ?? []).filter((t) => t.status === "done"), tone: "text-muted" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">My tasks</h1>
        <p className="max-w-3xl text-sm text-muted">
          Follow-ups you created from briefings, across all your clients. In this prototype they are kept with each
          briefing; in production they would be created in the bank&apos;s CRM (after approval) and listed from there.
        </p>
      </div>
      {error && <p className="rounded-md bg-risk-soft px-4 py-3 text-sm text-risk">{error}</p>}
      {!tasks && !error && <p className="text-sm text-muted">Loading…</p>}
      {tasks?.length === 0 && (
        <p className="rounded-xl border border-line bg-surface px-5 py-4 text-sm text-muted">
          No tasks yet. Open a briefing and use More → Create task.
        </p>
      )}
      {tasks && tasks.length > 0 && groups.map((g) => g.items.length > 0 && (
        <section key={g.title} className="rounded-xl border border-line bg-surface">
          <header className="flex items-baseline justify-between border-b border-line px-5 py-3">
            <h2 className={`text-[15px] font-semibold ${g.tone}`}>{g.title}</h2>
            <span className="text-xs text-muted">{g.items.length}</span>
          </header>
          <ul className="divide-y divide-line px-5">
            {g.items.map((t) => (
              <TaskRow key={key(t)} task={t} runId={t.run_id!} user={user!.user_id} onChange={update} showClient />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

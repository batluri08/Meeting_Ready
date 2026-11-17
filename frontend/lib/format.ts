/** "2026-11-19T10:00" -> "Thu 19 Nov, 10:00" */
export function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "Kestrel Foods quarterly review (2026-11-19T10:00)" -> "Kestrel Foods quarterly review · Thu 19 Nov, 10:00" */
export function formatMeeting(meeting: string | null | undefined): string {
  if (!meeting) return "";
  return meeting.replace(/\s*\((\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\)/, (_, iso: string) => ` · ${when(iso)}`);
}

export function ago(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

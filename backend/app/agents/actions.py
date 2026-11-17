"""Workflow actions from a briefing: draft a follow-up email, create a task, export a one-pager,
schedule a pre-meeting briefing, suggest follow-up tasks.

Nothing is sent or written to a real system: emails are drafts for a person to review, tasks go to a mock
task list standing in for the CRM (suggested tasks only become tasks when a person adds them), and the
schedule stands in for a calendar trigger.
"""
import copy
from datetime import datetime, timedelta

from app.agents.evidence import statement_text
from app.gateway.gateway import Gateway, models_in_use

EMAIL_VERSION = "draft-email-v1"
EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}
EMAIL_SYSTEM = (
    "Draft a short, professional follow-up email from the bank's relationship team to the client after the "
    "meeting. Acknowledge the client's open requests and concerns, and state what the bank will do next, using ONLY "
    "the points given. No new numbers, no promises beyond the points given. Plain text, under 180 words. Keep "
    "name tokens like [PERSON_1] as they are."
)


def _engine(briefing: dict) -> str:
    """Which models wrote the briefing, by name ('Opus 5.5 + Haiku 5.5'), or 'offline' for rules + templates."""
    if briefing.get("mode") != "anthropic":
        return "offline (rules + templates)"
    m = models_in_use()
    return f"{m['opus']} + {m['haiku']}"


def _meeting(briefing: dict) -> str:
    """'Kestrel Foods quarterly review (2026-11-19T10:00)' -> 'Kestrel Foods quarterly review, Thu 19 Nov 2026, 10:00'."""
    import re
    def fmt(m):
        d = datetime.fromisoformat(m.group(1))
        return f", {d:%a} {d.day} {d:%b %Y, %H:%M}"
    return re.sub(r"\s*\((\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\)", fmt, briefing.get("meeting") or "")


def _section(briefing: dict, sid: str) -> list[str]:
    s = next((s for s in briefing["sections"] if s["id"] == sid), None)
    return [statement_text(st) for st in (s["statements"] if s else []) if not st.get("empty")]


def draft_email(briefing: dict, gateway: Gateway) -> dict:
    points = _section(briefing, "commitments")
    def offline():
        lines = "\n".join(f"- {p}" for p in points) or "- (no open items)"
        return {"subject": f"Follow-up: {briefing['client_name']}",
                "body": f"Dear team,\n\nThank you for your time. As agreed, these are the open points we are "
                        f"following up on:\n{lines}\n\nWe will come back to you on each of them.\n\nKind regards,\n"
                        f"{briefing['user']['name']}"}
    draft = gateway.call("write", EMAIL_VERSION, EMAIL_SYSTEM,
                         f"Client: {briefing['client_name']}\nSender: {briefing['user']['name']}\nPoints:\n"
                         + "\n".join(f"- {p}" for p in points), EMAIL_SCHEMA, offline=offline)
    draft = {k: gateway.masker.unmask(v) for k, v in draft.items()}
    gateway.audit.log("action", type="draft_email", chars=len(draft["body"]))
    return {**draft, "status": "draft (not sent)"}


def _numbered(briefing: dict) -> tuple[list[dict], list[str]]:
    """Sections with each statement's citations turned into source numbers [1], [2]..., in reading order."""
    cited: list[str] = []
    sections = []
    for s in briefing["sections"]:
        items = []
        for st in s["statements"]:
            nums = []
            for eid in st.get("evidence_ids", []):
                if eid not in cited:
                    cited.append(eid)
                nums.append(cited.index(eid) + 1)
            items.append({"text": st["text"], "label": st.get("label") or "", "role": st.get("role") or "point",
                          "refs": nums, "kind": st.get("kind")})
        sections.append({"id": s["id"], "question": s["question"], "status": s["status"], "items": items})
    return sections, cited


def _source_line(briefing: dict, eid: str) -> str:
    e = briefing["evidence"][eid]
    src = e["source"]
    where = src.get("doc_id") or ", ".join(src.get("refs", [])) or e["kind"]
    title = e["title"]
    if "_" in title and " " not in title:            # internal codes such as 'issue_opened' -> 'Issue opened'
        title = title.replace("_", " ").capitalize()
    title = title[:1].upper() + title[1:]
    return f"{title} ({where}{', ' + src['date'] if src.get('date') else ''})"


_LABEL_PREFIXES = ("Conflicting information: ", "Out of date: ")


def _filename(briefing: dict, ext: str) -> str:
    return f"briefing-{briefing['client_id']}-{briefing['run_id']}.{ext}"


def export_markdown(briefing: dict) -> dict:
    sections, cited = _numbered(briefing)
    lines = [f"# Briefing: {briefing['client_name']}", "",
             f"{_meeting(briefing)} · prepared for {briefing['user']['name']} · run {briefing['run_id']}", ""]
    for s in sections:
        lines += [f"## {s['question']}", ""]
        if s["status"] != "ok":
            lines += ["_Unavailable: this section could not be completed._", ""]
            continue
        for i in s["items"]:
            refs = " ".join(f"[{n}]" for n in i["refs"])
            if i["role"] == "answer":
                lines += [f"**{i['text']}** {refs}".rstrip(), ""]
            elif i["role"] == "why":
                lines += ["", f"_Why it matters:_ {i['text']} {refs}".rstrip()]
            else:
                lines.append(f"- {'**' + i['label'] + ':** ' if i['label'] else ''}{i['text']} {refs}".rstrip())
        lines.append("")
    lines += ["## Sources", ""] + [f"{n}. {_source_line(briefing, eid)}" for n, eid in enumerate(cited, 1)]
    return {"filename": _filename(briefing, "md"), "markdown": "\n".join(lines)}


# Characters outside the PDF standard fonts' character set, mapped to plain equivalents.
_PDF_SAFE = str.maketrans({"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "≠": "!=", "✓": "", " ": " "})


def export_pdf(briefing: dict) -> tuple[str, bytes]:
    """A printable one-pager: header, the seven questions with numbered citations, sources, page numbers.
    Marked CONFIDENTIAL when it cites restricted records (only possible for senior users)."""
    import io
    from datetime import datetime
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    accent, muted, risk = (colors.HexColor(c) for c in ("#0e6763", "#5d6b78", "#a3342b"))
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, alignment=TA_LEFT)
    styles = {
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21),
        "meta": ParagraphStyle("meta", parent=base, fontSize=8.5, textColor=muted, leading=11),
        "banner": ParagraphStyle("banner", parent=base, fontName="Helvetica-Bold", fontSize=8.5, textColor=risk),
        "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=accent,
                            spaceBefore=9, spaceAfter=3),
        "item": base,
        "answer": ParagraphStyle("answer", parent=base, fontSize=10, leading=14, spaceAfter=3),
        "why": ParagraphStyle("why", parent=base, textColor=muted, spaceBefore=3),
        "unavail": ParagraphStyle("unavail", parent=base, textColor=risk),
        "src": ParagraphStyle("src", parent=base, fontSize=7.5, leading=9.5, textColor=muted),
    }
    label = {"conflict": "CONFLICT", "stale": "OUT OF DATE", "restricted": "RESTRICTED", "low_confidence": "LOW CONFIDENCE",
             "security": "SECURITY", "unavailable": "UNAVAILABLE", "gap": "GAP"}

    def safe(text: str) -> str:
        return escape((text or "").translate(_PDF_SAFE))

    sections, cited = _numbered(briefing)
    restricted = any(briefing["evidence"][e].get("restricted") for e in cited)
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    story = []
    if restricted:
        story.append(Paragraph("CONFIDENTIAL: contains restricted information. Senior clearance only.", styles["banner"]))
        story.append(Spacer(1, 2 * mm))
    story += [Paragraph(f"Client briefing: {safe(briefing['client_name'])}", styles["title"]),
              Paragraph(f"{safe(_meeting(briefing))} &middot; prepared for {safe(briefing['user']['name'])} "
                        f"({safe(briefing['user']['clearance'])}) &middot; generated {generated} &middot; "
                        f"{_engine(briefing)} &middot; run {safe(briefing['run_id'])}",
                        styles["meta"]),
              Paragraph("Every statement cites its source [n]; numbers come from database queries, not the AI.",
                        styles["meta"]), Spacer(1, 2 * mm)]

    for s in sections:
        block = [Paragraph(safe(s["question"]), styles["h"])]
        if s["status"] != "ok":
            block.append(Paragraph("Unavailable: this section could not be completed.", styles["unavail"]))
        else:
            bullets, answer, why = [], [], []
            for i in s["items"]:
                text = i["text"]
                tag = ""
                if i.get("kind") in label:                   # the label says it; drop the repeated wording
                    tag = f'<font color="#9a5a00"><b>{label[i["kind"]]}</b></font> '
                    text = next((text[len(p):] for p in _LABEL_PREFIXES if text.startswith(p)), text)
                elif i.get("label"):
                    tag = f"<b>{safe(i['label'])}:</b> "
                refs = f' <font color="#0e6763" size="7">{" ".join(f"[{n}]" for n in i["refs"])}</font>' if i["refs"] else ""
                if i.get("role") == "answer":
                    answer.append(Paragraph(f"<b>{safe(text)}</b>{refs}", styles["answer"]))
                elif i.get("role") == "why":
                    why.append(Paragraph(f"<i>Why it matters:</i> {safe(text)}{refs}", styles["why"]))
                else:
                    bullets.append(ListItem(Paragraph(f"{tag}{safe(text)}{refs}", styles["item"]), leftIndent=10))
            block += answer
            if bullets:
                block.append(ListFlowable(bullets, bulletType="bullet", start="•", leftIndent=10, bulletFontSize=7))
            block += why
        story.append(KeepTogether(block[:2]) if len(block) > 1 else block[0])
        story += block[2:]

    story += [Paragraph("Sources", styles["h"])]
    story += [Paragraph(f"[{n}] {safe(_source_line(briefing, eid))}", styles["src"]) for n, eid in enumerate(cited, 1)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 10 * mm, f"MeetingReady · {briefing['client_name']} · {briefing['run_id']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        if restricted:
            canvas.setFillColor(risk)
            canvas.drawCentredString(A4[0] / 2, A4[1] - 9 * mm, "CONFIDENTIAL")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=17 * mm,
                            title=f"Briefing: {briefing['client_name']}", author=briefing["user"]["name"])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return _filename(briefing, "pdf"), buf.getvalue()


def schedule_briefing(meeting: dict, hours_before: int = 24) -> dict:
    start = datetime.fromisoformat(meeting["start_time"])
    return {"meeting_id": meeting["meeting_id"], "meeting_start": meeting["start_time"],
            "trigger_at": (start - timedelta(hours=hours_before)).isoformat(timespec="minutes"),
            "status": "scheduled (demo: stands in for a calendar trigger)"}


# ---------------------------------------------------------------- suggested tasks
TASKS_VERSION = "suggest-tasks-v1"
TASKS_SYSTEM = (
    "You suggest follow-up tasks for a bank's relationship team, from the points of a client briefing. Suggest 3 to 5 "
    "concrete tasks. Each is one action a person can do, starts with a verb, and is about 15 words. Base them ONLY on "
    "the briefing points given: client asks nobody is tracking, overdue or open actions, client concerns, deals "
    "closing soon, and opportunities to follow up. Do not repeat a task that already exists. For each, give a short "
    "reason naming the briefing point it comes from, cite that point's evidence ids, and say whether it should be "
    "done before or after the meeting. Copy any number exactly from the points; never make up numbers or dates. Keep "
    "name tokens like [PERSON_1] as they are."
)
TASKS_SCHEMA = {
    "type": "object",
    "properties": {"tasks": {"type": "array", "items": {
        "type": "object",
        "properties": {"description": {"type": "string"}, "reason": {"type": "string"},
                       "timing": {"type": "string", "enum": ["before the meeting", "after the meeting"]},
                       "evidence_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["description", "reason", "timing", "evidence_ids"], "additionalProperties": False}}},
    "required": ["tasks"], "additionalProperties": False,
}
SUGGEST_FROM = ("commitments", "metrics", "opportunities")


def _due(timing: str, meeting_start: str | None, today) -> str:
    """Due dates are set by code, not the model: the day before the meeting, or a week after it.
    With no meeting booked: in 2 days, or in 9."""
    if meeting_start:
        day = datetime.fromisoformat(meeting_start).date()
        due = day - timedelta(days=1) if timing == "before the meeting" else day + timedelta(days=7)
        return max(due, today).isoformat()
    return (today + timedelta(days=2 if timing == "before the meeting" else 9)).isoformat()


def suggest_tasks(briefing: dict, existing: list[dict], meeting_start: str | None, today, gateway: Gateway) -> dict:
    """Up to 5 suggested tasks from the briefing's asks, actions, concerns, flagged items and opportunities.
    Every suggestion cites the briefing evidence it comes from and passes the same verifier as the briefing."""
    from app.agents.chat import evidence_from_briefing
    from app.agents.verifier import check

    points = [(s["id"], st) for s in briefing["sections"] if s["id"] in SUGGEST_FROM and s["status"] == "ok"
              for st in s["statements"] if not st.get("empty") and st.get("evidence_ids")]
    ids = sorted({e for _, st in points for e in st["evidence_ids"]}, key=lambda e: int(e[1:]))
    if not ids:
        return {"suggestions": []}
    existing_txt = "\n".join(f"- {t['description']}" for t in existing) or "(none)"

    def offline():   # rules: one task per untracked ask, open or overdue action, and client concern
        import re
        action_rx = re.compile(r"^(ACT-\d+) \(open, owner ([^,]+), due [\d-]+\): (.+)$")

        def core(text: str) -> str:
            """The client's own words, without the briefing's prefix, cut to one short sentence."""
            for p in ("Client ask not tracked as an action: ", "Client concern: ", "We said: "):
                text = text.removeprefix(p)
            first = re.split(r"(?<=[.!?])\s", text.strip())[0].rstrip(".")
            return first if len(first) <= 110 else first[:110].rsplit(" ", 1)[0] + "…"

        out = []
        for _, st in points:
            text, label = statement_text(st), (st.get("label") or "").lower()
            if "not tracked" in text.lower() or "not tracked" in label:
                out.append((f"Reply to the client's request: \"{core(st['text'])}\"", st))
            elif m := action_rx.match(st["text"]):
                out.append((f"Chase {m[1]} with {m[2]}: {core(m[3])}", st))
            elif "overdue" in text.lower() or "open action" in label:
                out.append((f"Chase the open action: {core(st['text'])}", st))
            elif "concern" in text.lower() or "concern" in label:
                out.append((f"Prepare an answer to the concern: \"{core(st['text'])}\"", st))
        return {"tasks": [{"description": d, "reason": "From the briefing (offline rules)", "timing": "before the meeting",
                           "evidence_ids": st["evidence_ids"]} for d, st in out[:5]]}

    schema = copy.deepcopy(TASKS_SCHEMA)
    schema["properties"]["tasks"]["items"]["properties"]["evidence_ids"]["items"] = {"type": "string", "enum": ids}
    content = (f"Today is {today.isoformat()}. Do not suggest doing anything before a date that has already passed.\n\n"
               "Briefing points (evidence ids in brackets):\n"
               + "\n".join(f"- ({sid}) [{', '.join(st['evidence_ids'])}] {statement_text(st)}" for sid, st in points)
               + f"\n\nTasks that already exist:\n{existing_txt}")
    result = gateway.call("write", TASKS_VERSION, TASKS_SYSTEM, content, schema, offline=offline)

    store, allowed, out = evidence_from_briefing(briefing), set(ids), []
    for t in result.get("tasks", [])[:5]:
        st = {"text": gateway.masker.unmask(t["description"]), "evidence_ids": t.get("evidence_ids", [])}
        reason = check(st, allowed, store)          # same rule as the briefing: cited, and numbers in the source
        if reason:
            gateway.audit.log("verifier_drop", section="suggested_tasks", text=st["text"][:200], reason=reason)
            continue
        out.append({"description": st["text"], "reason": gateway.masker.unmask(t.get("reason", "")),
                    "timing": t.get("timing", "before the meeting"), "evidence_ids": st["evidence_ids"],
                    "due_date": _due(t.get("timing", ""), meeting_start, today)})
    gateway.audit.log("action", type="suggest_tasks", suggested=len(out))
    return {"suggestions": out}

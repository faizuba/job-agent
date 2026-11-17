"""
tools.py — the agent's hands.

Two halves:
  1. TOOL_SCHEMAS: what we TELL the model about each tool (name, description, inputs).
     The model never sees your Python code, only these descriptions. Clear
     descriptions are the single biggest factor in whether the agent uses tools well.
  2. run_tool(): what actually HAPPENS when the model asks for a tool.
     The model only *requests*; your code decides whether and how to run it.
     That's where guardrails live.
"""

from datetime import date

import tracker_db

STATUSES = list(tracker_db.STATUS_RANK)

TOOL_SCHEMAS = [
    {
        "name": "search_emails",
        "description": (
            "Search the user's inbox. Returns a list of emails (id, from, subject, date, snippet) "
            "and whether each was already processed on a previous run. Uses Gmail search syntax, "
            "e.g. 'application OR interview OR assessment OR offer OR unfortunately'. "
            "Skip emails marked already_processed=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail-style search query."},
                "newer_than_days": {"type": "integer", "description": "Only emails from the last N days."},
                "max_results": {"type": "integer", "description": "Default 20, max 50."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_email",
        "description": "Read the full text of one email by id. Use when the snippet isn't enough "
                       "to tell the company, role, or what happened.",
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string"}},
            "required": ["email_id"],
        },
    },
    {
        "name": "find_application",
        "description": "Look up existing tracker rows for a company (partial, case-insensitive match). "
                       "Call this before update_application so you reuse the exact role name already stored.",
        "input_schema": {
            "type": "object",
            "properties": {"company": {"type": "string"}},
            "required": ["company"],
        },
    },
    {
        "name": "update_application",
        "description": (
            "Create or update a job application in the tracker based on one email. "
            "Status meanings: applied = confirmation received; assessment = online test / HireVue / case; "
            "interview = interview scheduled or completed; offer = offer extended; "
            "rejected = they declined; withdrawn = the user withdrew. "
            "Statuses never move backwards; the tool will tell you if it kept the old status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name, e.g. 'Skyline Airways'."},
                "role": {"type": "string", "description": "Job title as written in the email."},
                "status": {"type": "string", "enum": STATUSES},
                "event_date": {"type": "string", "description": "Email date, YYYY-MM-DD."},
                "summary": {"type": "string", "description": "One sentence: what this email said."},
                "email_id": {"type": "string", "description": "The email this update came from."},
                "notes": {"type": "string", "description": "Optional: deadlines, interviewer names, links."},
            },
            "required": ["company", "role", "status", "event_date", "summary", "email_id"],
        },
    },
    {
        "name": "skip_email",
        "description": "Mark an email as not about one of the user's own applications (job alerts, "
                       "newsletters, marketing, personal mail) so future runs ignore it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string"},
                "reason": {"type": "string", "description": "Short reason, e.g. 'LinkedIn job alert'."},
            },
            "required": ["email_id", "reason"],
        },
    },
    {
        "name": "list_stale_applications",
        "description": "List applications still in 'applied' or 'assessment' with no update for N days. "
                       "These are candidates for a polite follow-up.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Default 14."}},
        },
    },
    {
        "name": "create_draft",
        "description": "Save a follow-up email as a DRAFT for the user to review. It is never sent automatically. "
                       "Keep it short (under 120 words), polite, and specific to the company and role.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient address (from the original email)."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]


class ToolContext:
    """Everything tools need, plus per-run guardrail counters."""

    def __init__(self, inbox, conn, max_drafts: int = 3):
        self.inbox = inbox
        self.conn = conn
        self.max_drafts = max_drafts
        self.drafts_created = 0
        self.log = []   # human-readable record of every action, printed at the end


def run_tool(name: str, args: dict, ctx: ToolContext):
    """Dispatch a tool request from the model to real code. Returns JSON-able data."""
    if name == "search_emails":
        results = ctx.inbox.search(
            args["query"],
            max_results=min(int(args.get("max_results", 20)), 50),
            newer_than_days=args.get("newer_than_days"),
        )
        for r in results:
            r["already_processed"] = tracker_db.is_processed(ctx.conn, r["id"])
        return results

    if name == "read_email":
        return ctx.inbox.read(args["email_id"])

    if name == "find_application":
        return tracker_db.find_applications(ctx.conn, args["company"]) or "No matching applications."

    if name == "update_application":
        result = tracker_db.upsert_application(
            ctx.conn, args["company"], args["role"], args["status"],
            args.get("event_date") or date.today().isoformat(),
            args["summary"], email_id=args.get("email_id"), notes=args.get("notes"),
        )
        ctx.log.append(f"{args['company']} / {args['role']}: {result['action']}")
        return result

    if name == "skip_email":
        tracker_db.mark_processed(ctx.conn, args["email_id"], f"skipped: {args['reason']}")
        return {"ok": True}

    if name == "list_stale_applications":
        return tracker_db.stale_applications(ctx.conn, int(args.get("days", 14))) or "None."

    if name == "create_draft":
        # GUARDRAIL: cap drafts per run, enforced in code, not just in the prompt.
        if ctx.drafts_created >= ctx.max_drafts:
            return {"error": f"Draft limit reached ({ctx.max_drafts} per run). Do not create more."}
        result = ctx.inbox.create_draft(args["to"], args["subject"], args["body"])
        ctx.drafts_created += 1
        ctx.log.append(f"Drafted follow-up: '{args['subject']}' -> {args['to']}")
        return result

    raise ValueError(f"Unknown tool: {name}")

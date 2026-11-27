"""
mcp_server.py: lets AI assistants (like the Claude desktop app) read your job tracker.

WHAT IS MCP?
The Model Context Protocol is a standard plug for AI tools. In agent.py, YOU wrote the
tool descriptions and ran the loop. MCP flips that around: this file offers tools, and
any MCP-compatible assistant (Claude desktop, Claude Code, others) can plug in and use
them. Then you can ask Claude "what does my pipeline look like?" and it calls
pipeline_summary() here to answer.

    Claude desktop  --(asks to run a tool)-->  this server  --(SQL query)-->  tracker.db
                    <--(JSON result)---------               <--(rows)-------

READ-ONLY ON PURPOSE (a guardrail in code, like the rest of this project):
the database is opened in SQLite's read-only mode, so even if an assistant asked to
change something, the database itself would refuse. Only the agent updates the tracker.

Run it:
    python mcp_server.py               serves your real tracker (tracker.db)
    python mcp_server.py --practice    serves the practice tracker (tracker_practice.db)
You normally don't run it by hand: the Claude desktop app starts it for you
(setup steps are in the README, "Ask Claude about your tracker").
"""

import argparse
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

HERE = Path(__file__).resolve().parent     # Claude desktop starts us from another folder,
REAL_DB = HERE / "tracker.db"               # so always build paths from this file's location
PRACTICE_DB = HERE / "tracker_practice.db"
STATUSES = ["applied", "assessment", "interview", "offer", "rejected", "withdrawn"]
READ_ONLY = ToolAnnotations(read_only_hint=True)   # tells the assistant these tools change nothing


# ---------------------------------------------------------------------------
# Plain functions: the actual logic. They take a database connection, so tests
# can call them directly without starting a server.
# ---------------------------------------------------------------------------
def open_readonly(path: Path) -> sqlite3.Connection:
    """Open the tracker in read-only mode ("?mode=ro"): writes raise an error."""
    if not path.exists():
        raise FileNotFoundError(f"No tracker database at {path}. Run the agent first.")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_applications(conn, status: str | None = None, company: str | None = None) -> list[dict]:
    sql, params = "SELECT company, role, status, applied_date, last_update, notes FROM applications", []
    where = []
    if status:
        where.append("status = ?")
        params.append(status.lower().strip())
    if company:
        where.append("company LIKE ?")
        params.append(f"%{company.strip()}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    return [dict(r) for r in conn.execute(sql + " ORDER BY last_update DESC", params)]


def pipeline_summary(conn, stale_days: int = 14) -> dict:
    rows = [dict(r) for r in conn.execute("SELECT * FROM applications")]
    total = len(rows)
    by_status = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
    heard_back = total - by_status["applied"]          # anything past "applied", rejections included
    cutoff = (date.today() - timedelta(days=stale_days)).isoformat()
    stale = [f"{r['company']} / {r['role']} (last news {r['last_update']})" for r in rows
             if r["status"] in ("applied", "assessment") and r["last_update"] <= cutoff]
    return {
        "total_applications": total,
        "by_status": by_status,
        "still_active": by_status["applied"] + by_status["assessment"] + by_status["interview"],
        "response_rate": f"{heard_back}/{total} ({heard_back / total:.0%})" if total else "n/a",
        "reached_interview_or_better": by_status["interview"] + by_status["offer"],
        f"no_news_in_{stale_days}_days": stale,
    }


def application_history(conn, company: str) -> list[dict]:
    apps = list_applications(conn, company=company)
    for app in apps:
        app["events"] = [dict(r) for r in conn.execute(
            "SELECT e.event_date, e.status, e.summary FROM events e "
            "JOIN applications a ON a.id = e.application_id "
            "WHERE a.company = ? AND a.role = ? ORDER BY e.event_date, e.id",
            (app["company"], app["role"]))]
    return apps


# ---------------------------------------------------------------------------
# The MCP server: wraps each function above as a tool. The docstrings become the
# tool descriptions the assistant reads, so they're written for the AI, like
# TOOL_SCHEMAS in tools.py.
# ---------------------------------------------------------------------------
def build_server(db_path: Path) -> MCPServer:
    server = MCPServer(
        "job-tracker",
        instructions="Read-only access to the user's job-application tracker, which an "
                     "email-reading agent keeps up to date. Statuses: " + ", ".join(STATUSES) + ".",
    )

    @server.tool(annotations=READ_ONLY)
    def get_applications(status: str | None = None, company: str | None = None) -> list[dict]:
        """List tracked job applications, newest first. Optionally filter by status
        (applied, assessment, interview, offer, rejected, withdrawn) and/or by part of a company name."""
        with closing(open_readonly(db_path)) as conn:   # closing() = always close it after
            return list_applications(conn, status, company)

    @server.tool(annotations=READ_ONLY)
    def get_pipeline_summary(stale_days: int = 14) -> dict:
        """Recruiting funnel overview: counts per status, response rate, how many reached
        interview, and applications with no news in `stale_days` days."""
        with closing(open_readonly(db_path)) as conn:   # closing() = always close it after
            return pipeline_summary(conn, stale_days)

    @server.tool(annotations=READ_ONLY)
    def get_application_history(company: str) -> list[dict]:
        """Full timeline of every application at a company (partial name match): each
        status change, its date, and a one-line summary of the email behind it."""
        with closing(open_readonly(db_path)) as conn:   # closing() = always close it after
            return application_history(conn, company)

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only MCP server for the job tracker")
    parser.add_argument("--practice", action="store_true", help="serve tracker_practice.db")
    args = parser.parse_args()
    build_server(PRACTICE_DB if args.practice else REAL_DB).run()   # talks over stdin/stdout

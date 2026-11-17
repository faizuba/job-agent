"""
tracker_db.py — the agent's long-term memory.

The AI model forgets everything between runs. This SQLite database is what lets
the agent "remember" your applications from one morning to the next.

Three tables:
  applications      one row per (company, role) you applied to
  events            history: every email that changed an application
  processed_emails  email IDs the agent already handled, so it never re-reads them
"""

import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = "tracker.db"

# Allowed statuses, in the order an application normally moves through them.
STATUS_RANK = {
    "applied": 1,
    "assessment": 2,   # online test, HireVue, case study
    "interview": 3,
    "offer": 4,
    "rejected": 5,
    "withdrawn": 5,
}
FINAL_STATUSES = {"offer", "rejected", "withdrawn"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company       TEXT NOT NULL,
    role          TEXT NOT NULL,
    status        TEXT NOT NULL,
    applied_date  TEXT,
    last_update   TEXT NOT NULL,
    notes         TEXT,
    UNIQUE(company, role)
);
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER REFERENCES applications(id),
    email_id        TEXT,
    status          TEXT,
    event_date      TEXT,
    summary         TEXT
);
CREATE TABLE IF NOT EXISTS processed_emails (
    email_id      TEXT PRIMARY KEY,
    processed_at  TEXT NOT NULL,
    outcome       TEXT
);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.executescript(SCHEMA)
    return conn


def find_applications(conn, company: str) -> list[dict]:
    """Case-insensitive partial match, so 'skyline' finds 'Skyline Airways'."""
    rows = conn.execute(
        "SELECT * FROM applications WHERE company LIKE ? ORDER BY last_update DESC",
        (f"%{company.strip()}%",),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_application(conn, company, role, status, event_date, summary,
                       email_id=None, notes=None) -> dict:
    """
    Create the application if it's new, otherwise move its status forward.

    Guardrail: status never moves backwards (a late 'we received your application'
    email must not overwrite 'interview'), and final statuses are never changed.
    """
    status = status.lower().strip()
    if status not in STATUS_RANK:
        raise ValueError(f"status must be one of {sorted(STATUS_RANK)}")
    event_date = event_date or date.today().isoformat()

    existing = conn.execute(
        "SELECT * FROM applications WHERE lower(company)=lower(?) AND lower(role)=lower(?)",
        (company, role),
    ).fetchone()

    if existing is None:
        cur = conn.execute(
            "INSERT INTO applications (company, role, status, applied_date, last_update, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (company, role, status, event_date, event_date, notes),
        )
        app_id, action = cur.lastrowid, "created"
    else:
        app_id = existing["id"]
        old = existing["status"]
        if old in FINAL_STATUSES or STATUS_RANK[status] < STATUS_RANK[old]:
            action = f"kept status '{old}' (won't move from '{old}' to '{status}')"
            conn.execute("UPDATE applications SET last_update=max(last_update, ?) WHERE id=?",
                         (event_date, app_id))
        else:
            action = f"updated '{old}' -> '{status}'"
            conn.execute(
                "UPDATE applications SET status=?, last_update=max(last_update, ?), "
                "notes=coalesce(?, notes) WHERE id=?",
                (status, event_date, notes, app_id),
            )

    conn.execute(
        "INSERT INTO events (application_id, email_id, status, event_date, summary) VALUES (?,?,?,?,?)",
        (app_id, email_id, status, event_date, summary),
    )
    if email_id:
        mark_processed(conn, email_id, f"application {app_id}: {action}", commit=False)
    conn.commit()
    return {"application_id": app_id, "action": action}


def is_processed(conn, email_id: str) -> bool:
    return conn.execute("SELECT 1 FROM processed_emails WHERE email_id=?",
                        (email_id,)).fetchone() is not None


def mark_processed(conn, email_id: str, outcome: str, commit: bool = True):
    conn.execute(
        "INSERT OR REPLACE INTO processed_emails (email_id, processed_at, outcome) VALUES (?,?,?)",
        (email_id, datetime.now().isoformat(timespec="seconds"), outcome),
    )
    if commit:
        conn.commit()


def stale_applications(conn, days: int = 14) -> list[dict]:
    """Applications still waiting (applied/assessment) with no news for `days` days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM applications WHERE status IN ('applied','assessment') "
        "AND last_update <= ? ORDER BY last_update",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def all_applications(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM applications ORDER BY last_update DESC").fetchall()]

"""
main.py — the command line you actually run.

  python main.py run --fake        practice run on the sample inbox (start here)
  python main.py run               real run on your Gmail
  python main.py show              print your tracker table (no AI, no cost)
  python main.py reset --fake      delete the practice database to start over
"""

import argparse
import os
from pathlib import Path

import tracker_db

PRACTICE_DB = "tracker_practice.db"


def load_env_file(filename: str = ".env") -> None:
    """Copy KEY=value lines from .env into the environment, so you don't have to
    `export ANTHROPIC_API_KEY=...` in every new terminal.

    It's a tiny version of what the python-dotenv library does. A value you already
    exported in your shell wins over the one in the file.
    """
    path = Path(__file__).with_name(filename)     # look next to main.py, not wherever you ran it from
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue                              # skip blank lines and comments
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def cmd_run(args):
    from agent import MODEL, run_agent    # imported here so `show` works without the AI library
    from inbox import FakeInbox, GmailInbox
    from prompts import daily_task
    from tools import ToolContext

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("No ANTHROPIC_API_KEY found. Run ./setup.sh to save it in .env.")

    inbox = FakeInbox() if args.fake else GmailInbox()
    conn = tracker_db.connect(PRACTICE_DB if args.fake else tracker_db.DB_PATH)
    ctx = ToolContext(inbox, conn, max_drafts=args.max_drafts)

    print(f"Running agent on {MODEL} ({'practice inbox' if args.fake else 'Gmail'})...\n")
    summary = run_agent(daily_task(args.days), ctx)

    print("\n=== Actions taken ===")
    print("\n".join(f"- {line}" for line in ctx.log) or "- none")
    print("\n=== Agent summary ===\n" + summary)
    print_table(conn)


def cmd_show(args):
    print_table(tracker_db.connect(PRACTICE_DB if args.fake else tracker_db.DB_PATH))


def cmd_reset(args):
    path = Path(PRACTICE_DB if args.fake else tracker_db.DB_PATH)
    if not args.fake and input(f"Delete {path}? This erases your real tracker. Type yes: ") != "yes":
        return
    path.unlink(missing_ok=True)
    print(f"Deleted {path}")


def print_table(conn):
    rows = tracker_db.all_applications(conn)
    print(f"\n=== Tracker ({len(rows)} applications) ===")
    if not rows:
        return
    print(f"{'Company':<24}{'Role':<36}{'Status':<12}{'Applied':<12}{'Last update':<12}")
    for r in rows:
        print(f"{r['company'][:23]:<24}{r['role'][:35]:<36}{r['status']:<12}"
              f"{(r['applied_date'] or '')[:10]:<12}{r['last_update'][:10]:<12}")


if __name__ == "__main__":
    load_env_file()
    p = argparse.ArgumentParser(description="Job application tracker agent")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the agent")
    run.add_argument("--fake", action="store_true", help="use the practice inbox")
    run.add_argument("--days", type=int, default=30, help="how far back to look (default 30)")
    run.add_argument("--max-drafts", type=int, default=3)
    run.set_defaults(func=cmd_run)

    show = sub.add_parser("show", help="print the tracker")
    show.add_argument("--fake", action="store_true")
    show.set_defaults(func=cmd_show)

    reset = sub.add_parser("reset", help="delete the tracker database")
    reset.add_argument("--fake", action="store_true")
    reset.set_defaults(func=cmd_reset)

    args = p.parse_args()
    args.func(args)

"""
Tests for the read-only MCP server (mcp_server.py). No AI, no internet.

They build a small tracker in a temp folder, then check:
  - the summary numbers are right
  - the database really is read-only through the server's connection
  - a real MCP client can connect, see the 3 tools, and call them
"""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mcp_server
import tracker_db


def make_tracker(path: Path) -> None:
    with closing(tracker_db.connect(str(path))) as conn:
        add = lambda c, r, s, d, e: tracker_db.upsert_application(conn, c, r, s, d, f"{s} email", email_id=e)
        add("Harbor Capital", "Business Analyst Intern", "applied", "2026-01-01", "e1")
        add("Harbor Capital", "Business Analyst Intern", "interview", "2026-01-10", "e2")
        add("Atlas Retail", "Pricing Analyst Intern", "rejected", "2026-01-05", "e3")
        add("Skyline Airways", "Sales Strategy Intern", "applied", "2026-01-02", "e4")


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "tracker.db"
        make_tracker(self.db)

    def test_pipeline_summary(self):
        with closing(mcp_server.open_readonly(self.db)) as conn:
            s = mcp_server.pipeline_summary(conn, stale_days=14)
        self.assertEqual(s["total_applications"], 3)
        self.assertEqual(s["by_status"]["interview"], 1)
        self.assertEqual(s["response_rate"], "2/3 (67%)")       # Harbor + Atlas heard back
        self.assertEqual(len(s["no_news_in_14_days"]), 1)       # Skyline, dated long ago

    def test_history_has_every_event_in_order(self):
        with closing(mcp_server.open_readonly(self.db)) as conn:
            apps = mcp_server.application_history(conn, "harbor")
        self.assertEqual([e["status"] for e in apps[0]["events"]], ["applied", "interview"])

    def test_database_is_read_only(self):
        with closing(mcp_server.open_readonly(self.db)) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM applications")

    def test_missing_database_gives_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            mcp_server.open_readonly(self.db.with_name("nope.db"))

    def test_mcp_client_can_list_and_call_tools(self):
        from mcp import Client

        async def talk():
            async with Client(mcp_server.build_server(self.db)) as client:
                tools = (await client.list_tools()).tools
                result = await client.call_tool("get_pipeline_summary", {})
                return tools, result

        tools, result = asyncio.run(talk())
        self.assertEqual(sorted(t.name for t in tools),
                         ["get_application_history", "get_applications", "get_pipeline_summary"])
        self.assertTrue(all(t.annotations.read_only_hint for t in tools))
        self.assertFalse(result.is_error)
        self.assertEqual(json.loads(result.content[0].text)["total_applications"], 3)


if __name__ == "__main__":
    unittest.main()

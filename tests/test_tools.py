"""
Tests for the tools and database. No AI and no internet needed:
    python -m unittest discover tests

Testing tools on their own is a habit worth keeping. If a tool is buggy, the
agent will look "dumb" and you'll waste time blaming the prompt.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tracker_db
from inbox import FakeInbox
from tools import ToolContext, run_tool


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = tracker_db.connect(os.path.join(self.tmp, "test.db"))
        self.ctx = ToolContext(FakeInbox(drafts_dir=os.path.join(self.tmp, "drafts")),
                               self.conn, max_drafts=2)

    def update(self, status, email_id, company="Harbor Capital", role="Business Analyst Intern",
               day="2026-11-01"):
        return run_tool("update_application", {
            "company": company, "role": role, "status": status,
            "event_date": day, "summary": "test", "email_id": email_id}, self.ctx)

    def test_search_finds_and_flags_processed(self):
        results = run_tool("search_emails", {"query": "application"}, self.ctx)
        self.assertTrue(len(results) >= 5)
        self.update("applied", results[0]["id"])
        again = run_tool("search_emails", {"query": "application"}, self.ctx)
        self.assertTrue(again[0]["already_processed"])

    def test_status_moves_forward(self):
        self.update("applied", "e03")
        out = self.update("interview", "e05")
        self.assertIn("-> 'interview'", out["action"])

    def test_status_never_moves_backwards(self):
        self.update("interview", "e05")
        out = self.update("applied", "e06")          # the late duplicate confirmation
        self.assertIn("kept status 'interview'", out["action"])
        self.assertEqual(tracker_db.find_applications(self.conn, "harbor")[0]["status"], "interview")

    def test_final_status_is_locked(self):
        self.update("rejected", "e07", company="Atlas Retail", role="Pricing Analyst Intern")
        self.update("interview", "x1", company="Atlas Retail", role="Pricing Analyst Intern")
        self.assertEqual(tracker_db.find_applications(self.conn, "atlas")[0]["status"], "rejected")

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            self.update("ghosted", "e01")

    def test_stale_detection(self):
        self.update("applied", "e02", company="Northbridge Consulting", role="Data Analyst Intern",
                    day="2020-01-01")
        stale = run_tool("list_stale_applications", {"days": 14}, self.ctx)
        self.assertEqual(stale[0]["company"], "Northbridge Consulting")

    def test_skip_marks_processed(self):
        run_tool("skip_email", {"email_id": "e08", "reason": "job alert"}, self.ctx)
        self.assertTrue(tracker_db.is_processed(self.conn, "e08"))

    def test_draft_limit_enforced(self):
        args = {"to": "a@b.example", "subject": "Follow-up", "body": "Hi"}
        run_tool("create_draft", args, self.ctx)
        run_tool("create_draft", args, self.ctx)
        third = run_tool("create_draft", args, self.ctx)
        self.assertIn("error", third)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "drafts"))), 2)


if __name__ == "__main__":
    unittest.main()

"""
Tests for cost math (costs.py) and run logs (run_log.py). No AI, no internet.

The fake objects below copy the SHAPE of a real API response (usage numbers,
content blocks), so we can test our code without paying for a real one.
"""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from costs import Usage
from run_log import RunLog


def fake_usage(inp=0, out=0, write=0, read=0):
    return NS(input_tokens=inp, output_tokens=out,
              cache_creation_input_tokens=write, cache_read_input_tokens=read)


class CostTests(unittest.TestCase):
    def test_matches_hand_calculation_without_cache(self):
        # The Sonnet practice run from results/: 65,118 in + 4,107 out = about $0.17
        u = Usage()
        u.add(fake_usage(inp=65_118, out=4_107))
        self.assertAlmostEqual(u.cost("claude-sonnet-5-5"), 0.171306, places=6)
        self.assertEqual(u.cost("claude-sonnet-5-5"), u.cost_without_cache("claude-sonnet-5-5"))

    def test_cache_reads_are_cheaper(self):
        u = Usage()
        u.add(fake_usage(inp=1_000, out=0, write=1_000, read=8_000))
        # Haiku: 1k x $0.10 + 1k x $0.125 + 8k x $0.01, all per million
        self.assertAlmostEqual(u.cost("claude-haiku-5-5"), 0.000305, places=9)
        self.assertAlmostEqual(u.cost_without_cache("claude-haiku-5-5"), 0.001, places=9)
        self.assertEqual(u.total_input, 10_000)

    def test_missing_cache_fields_count_as_zero(self):
        u = Usage()
        u.add(NS(input_tokens=10, output_tokens=5,
                 cache_creation_input_tokens=None, cache_read_input_tokens=None))
        self.assertEqual((u.cache_write, u.cache_read), (0, 0))

    def test_unknown_model_has_no_price(self):
        self.assertIsNone(Usage().cost("some-future-model"))


class RunLogTests(unittest.TestCase):
    def test_writes_every_step_to_json(self):
        tmp = tempfile.mkdtemp()
        log = RunLog("claude-haiku-5-5", "practice", True, "test task", runs_dir=tmp)
        response = NS(
            stop_reason="tool_use",
            usage=fake_usage(inp=100, out=20, write=500, read=0),
            content=[NS(type="text", text="Let me search."),
                     NS(type="tool_use", id="t1", name="search_emails", input={"query": "offer"})],
        )
        log.add_step(1, response, 1.234, [{"name": "search_emails", "input": {"query": "offer"},
                                           "output": [], "is_error": False}])
        path = log.finish("All done.", {"cost_usd": 0.001}, ["something happened"])

        data = json.loads(path.read_text())
        self.assertEqual(data["model"], "claude-haiku-5-5")
        self.assertTrue(data["prompt_caching"])
        step = data["steps"][0]
        self.assertEqual(step["usage"]["cache_write_tokens"], 500)
        self.assertEqual(step["model_output"][1]["name"], "search_emails")
        self.assertEqual(step["tool_calls"][0]["input"], {"query": "offer"})
        self.assertEqual(data["final_summary"], "All done.")


if __name__ == "__main__":
    unittest.main()

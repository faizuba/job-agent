"""
run_log.py: saves a complete record of every agent run to runs/<time>_<model>.json.

The terminal only shows one short line per tool call. This file keeps EVERYTHING:
what the model said at each step, the exact inputs it gave each tool, what each tool
returned, how many tokens each step used, and how long it took. When the agent does
something strange, open the file and you can see exactly why. In industry this is called
"observability" (being able to see inside a running system).

Privacy: on a real Gmail run these files contain pieces of your real emails, so the
runs/ folder is in .gitignore and never goes to GitHub.
"""

import json
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).with_name("runs")


class RunLog:
    def __init__(self, model: str, inbox: str, prompt_caching: bool, task: str, runs_dir=RUNS_DIR):
        self.started = datetime.now()
        self.runs_dir = Path(runs_dir)
        self.data = {
            "started_at": self.started.isoformat(timespec="seconds"),
            "model": model,
            "inbox": inbox,                    # "practice" or "gmail"
            "prompt_caching": prompt_caching,
            "task": task,
            "steps": [],
        }

    def add_step(self, step: int, response, seconds: float, tool_calls: list[dict]) -> None:
        """Record one trip around the loop: the model's reply plus the tools it ran."""
        self.data["steps"].append({
            "step": step,
            "seconds": round(seconds, 2),
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": response.usage.input_tokens or 0,
                "cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
                "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                "output_tokens": response.usage.output_tokens or 0,
            },
            "model_output": [_block_to_dict(b) for b in response.content],
            "tool_calls": tool_calls,
        })

    def finish(self, final_text: str, usage: dict, actions: list[str], stopped_early: bool = False) -> Path:
        """Add the totals and write the file. Returns the file's path."""
        self.data.update({
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "seconds": round((datetime.now() - self.started).total_seconds(), 1),
            "stopped_early": stopped_early,
            "totals": usage,
            "actions": actions,
            "final_summary": final_text,
        })
        self.runs_dir.mkdir(exist_ok=True)
        path = self.runs_dir / f"{self.started:%Y%m%d_%H%M%S}_{self.data['model']}.json"
        path.write_text(json.dumps(self.data, indent=2, default=str))
        return path


def _block_to_dict(block) -> dict:
    """Turn one piece of the model's reply into plain JSON."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if block.type == "thinking":
        # Newer models hide their raw reasoning by default, so this text is usually empty.
        return {"type": "thinking", "text": getattr(block, "thinking", "")}
    return {"type": block.type}

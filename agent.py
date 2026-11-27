"""
agent.py — THE AGENT LOOP. This is the file to understand.

Everything that makes this an "agent" instead of a chatbot is in run_agent():

    messages = [task]
    repeat:
        ask the model what to do next (giving it the tool list)
        if it asked to use tools -> run them, add the results to messages, loop again
        if it answered in plain text -> that's the final answer, stop

The model decides WHICH tools and in WHAT ORDER. Your code just keeps the loop
going, runs the tools, and enforces limits.

Two extras on top of the basic loop:
  - Prompt caching (on by default): the loop re-sends the whole conversation every
    step, so most of each request is text the model already saw. Caching lets the API
    reuse that work at about a tenth of the price. See "PROMPT CACHING" below.
  - Run logs: every step is recorded to runs/*.json (see run_log.py).
"""

import json
import os
import time

import anthropic

from costs import Usage
from prompts import system_prompt
from run_log import RunLog
from tools import TOOL_SCHEMAS, ToolContext, run_tool

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 25          # guardrail: an agent stuck in a loop should not run (and bill you) forever
CACHE = {"type": "ephemeral"}   # "ephemeral" = keep it for 5 minutes; every cache hit restarts the timer


def run_agent(task: str, ctx: ToolContext, verbose: bool = True,
              cache: bool = True, log: RunLog | None = None) -> str:
    client = anthropic.Anthropic()     # reads ANTHROPIC_API_KEY from your environment
    messages = [{"role": "user", "content": task}]
    usage = Usage()

    # Build the system prompt ONCE. Caching only works if the start of every request is
    # byte-for-byte identical, so nothing in it should change between steps.
    system = system_prompt()

    # PROMPT CACHING: two "bookmarks" tell the API what it may save and reuse.
    #  1. cache_control on the system prompt: the tools + instructions (identical every step)
    #     get cached after step 1.
    #  2. cache_control at the top level: the API also caches the conversation so far, and
    #     moves that bookmark forward every step. So step 5 re-reads steps 1-4 from the cache.
    if cache:
        system_param = [{"type": "text", "text": system, "cache_control": CACHE}]
        extra = {"cache_control": CACHE}
    else:
        system_param, extra = system, {}

    for step in range(1, MAX_STEPS + 1):
        # 1) Ask the model for its next move.
        started = time.monotonic()
        response = client.messages.create(
            model=MODEL,
            # A ceiling, not a target: you only pay for tokens actually used. Newer models
            # think before answering, and that thinking counts toward this limit, so a
            # small value (like 2000) can cut a reply off mid-step.
            max_tokens=16000,
            system=system_param,
            tools=TOOL_SCHEMAS,
            messages=messages,
            **extra,
        )
        seconds = time.monotonic() - started
        usage.add(response.usage)

        # 2) Save the model's turn into the conversation (the agent's short-term memory).
        messages.append({"role": "assistant", "content": response.content})

        # 3) No tool requested -> the model thinks it's done.
        if response.stop_reason != "tool_use":
            final = "".join(b.text for b in response.content if b.type == "text")
            if log:
                log.add_step(step, response, seconds, tool_calls=[])
                ctx.log_path = log.finish(final, usage.to_dict(MODEL), ctx.log)
            if verbose:
                print(f"\n[done in {step} steps | {_usage_line(usage)}]")
            return final

        # 4) Run every tool the model asked for, and collect the results.
        tool_results, tool_calls = [], []
        for block in response.content:
            if block.type == "text" and block.text.strip() and verbose:
                print(f"\n  thinking: {block.text.strip()[:200]}")
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  step {step}: {block.name}({_short(block.input)})")
            try:
                output = run_tool(block.name, block.input, ctx)
                is_error = False
            except Exception as e:
                # Errors go BACK to the model, so it can read them and fix its own mistake.
                output, is_error = f"Error: {e}", True
                if verbose:
                    print(f"           -> error: {e}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,          # links this result to the request it answers
                "content": json.dumps(output, default=str),
                "is_error": is_error,
            })
            tool_calls.append({"name": block.name, "input": block.input,
                               "output": output, "is_error": is_error})

        if log:
            log.add_step(step, response, seconds, tool_calls)

        # 5) Tool results go back to the model as the next "user" message. Loop again.
        messages.append({"role": "user", "content": tool_results})

    final = f"Stopped after {MAX_STEPS} steps without finishing (guardrail). Check the log above."
    if log:
        ctx.log_path = log.finish(final, usage.to_dict(MODEL), ctx.log, stopped_early=True)
    return final


def _usage_line(usage: Usage) -> str:
    """One readable line: tokens, cache use, and what the run cost."""
    line = (f"{usage.total_input:,} input + {usage.output:,} output tokens"
            f" | cache: {usage.cache_read:,} read, {usage.cache_write:,} written")
    cost, uncached = usage.cost(MODEL), usage.cost_without_cache(MODEL)
    if cost is not None:
        line += f" | cost ≈ ${cost:.4f}"
        if usage.cache_read and uncached:
            line += f" (without caching ≈ ${uncached:.4f}, saved {1 - cost / uncached:.0%})"
    return line


def _short(d: dict, n: int = 90) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in d.items())
    return s if len(s) <= n else s[: n - 3] + "..."

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
"""

import json
import os

import anthropic

from prompts import system_prompt
from tools import TOOL_SCHEMAS, ToolContext, run_tool

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 25          # guardrail: an agent stuck in a loop should not run (and bill you) forever


def run_agent(task: str, ctx: ToolContext, verbose: bool = True) -> str:
    client = anthropic.Anthropic()     # reads ANTHROPIC_API_KEY from your environment
    messages = [{"role": "user", "content": task}]
    tokens_in = tokens_out = 0

    for step in range(1, MAX_STEPS + 1):
        # 1) Ask the model for its next move.
        response = client.messages.create(
            model=MODEL,
            # A ceiling, not a target: you only pay for tokens actually used. Newer models
            # think before answering, and that thinking counts toward this limit, so a
            # small value (like 2000) can cut a reply off mid-step.
            max_tokens=16000,
            system=system_prompt(),
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens

        # 2) Save the model's turn into the conversation (the agent's short-term memory).
        messages.append({"role": "assistant", "content": response.content})

        # 3) No tool requested -> the model thinks it's done.
        if response.stop_reason != "tool_use":
            final = "".join(b.text for b in response.content if b.type == "text")
            if verbose:
                print(f"\n[done in {step} steps | {tokens_in:,} input + {tokens_out:,} output tokens]")
            return final

        # 4) Run every tool the model asked for, and collect the results.
        tool_results = []
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

        # 5) Tool results go back to the model as the next "user" message. Loop again.
        messages.append({"role": "user", "content": tool_results})

    return f"Stopped after {MAX_STEPS} steps without finishing (guardrail). Check the log above."


def _short(d: dict, n: int = 90) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in d.items())
    return s if len(s) <= n else s[: n - 3] + "..."

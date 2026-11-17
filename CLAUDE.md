## What the agent does
Every morning it reads my Gmail, finds emails about my own job applications, updates a SQLite tracker
(applied → assessment → interview → offer / rejected / withdrawn), skips noise (job alerts, newsletters,
personal mail), and saves polite follow-up DRAFTS for applications with no reply in 14+ days.
It never sends email.

## Current state
- Working starter code, written by hand without an agent framework so I learn the loop:
  - `agent.py`: the agent loop (call model → run requested tools → send results back → repeat; max 25 steps)
  - `tools.py`: tool schemas the model sees + `run_tool()` that executes them (draft cap enforced here)
  - `tracker_db.py`: SQLite memory (applications, events, processed_emails); statuses never move backwards
  - `inbox.py`: `FakeInbox` (practice, `sample_data/fake_inbox.json`) and `GmailInbox` (real Gmail API)
  - `prompts.py`: system prompt; `main.py`: CLI (`run --fake`, `run`, `show`, `reset`)
  - `tests/test_tools.py`: 8 passing tests (`python -m unittest discover tests`)
- The README's "What a correct practice run looks like" table is the expected outcome for the fake inbox.

## What I want next (in this order)
1. **Add beginner-friendly comments to every file** explaining each part: what it does and why, in plain
   English. Don't change behavior. Re-run the tests after.
2. **Make setup one command on my Mac:** a `setup.sh` that creates `.venv`, installs requirements,
   asks for my Anthropic API key and saves it to `.env` (gitignored), and runs the tests. Make `main.py`
   load `.env` so I don't have to export the key every time.
3. Help me run `python main.py run --fake` and walk me through the log step by step.
4. Then teach me the fundamentals one at a time, each with a small exercise:
   1 Python setup · 2 calling the model API · 3 tools · 4 the agent loop · 5 SQLite memory ·
   6 system prompt · 7 guardrails · 8 Gmail OAuth · 9 testing & evaluation · 10 scheduling (cron) ·
   11 GitHub + README
5. Later: connect real Gmail, schedule it daily, write an automated eval (`tests/test_eval.py`),
   and build a Power BI / Tableau dashboard on the SQLite data.

## Rules
- Never commit `credentials.json`, `token.json`, `.env`, or any `*.db` file (already in `.gitignore`).
- The agent must stay drafts-only and read-only on Gmail. Keep guardrails enforced in code, not just in the prompt.
- Model is set by the `AGENT_MODEL` env var (default `claude-sonnet-5-5`).
- Before running anything that costs API tokens, tell me first.

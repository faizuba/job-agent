#!/usr/bin/env bash
# setup.sh: one-command setup for the job agent on a Mac.
#
#   ./setup.sh
#
# What it does, in order:
#   1. Checks you have Python 3.10 or newer.
#   2. Creates a private Python environment in .venv/ (so this project's libraries
#      don't mix with anything else on your computer).
#   3. Installs the libraries listed in requirements.txt into that environment.
#   4. Asks for your Anthropic API key and saves it to .env (a secrets file that
#      .gitignore keeps out of GitHub). main.py reads it automatically.
#   5. Runs the tests. These are free: they never call the AI.
#
# Safe to run again: it skips anything that's already done.

set -euo pipefail          # stop at the first error instead of carrying on half-broken
cd "$(dirname "$0")"       # always run from the project folder, wherever you call it from

echo "== 1/5 Checking Python =="
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ from https://www.python.org/downloads/ and re-run."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "You have $(python3 --version). This project needs Python 3.10 or newer."
  exit 1
fi
echo "Found $(python3 --version)"

echo "== 2/5 Creating .venv =="
if [ -d .venv ]; then
  echo ".venv already exists (skipping)"
else
  python3 -m venv .venv
  echo "Created .venv"
fi

echo "== 3/5 Installing requirements =="
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Done"

echo "== 4/5 Anthropic API key =="
# Safety check: never write a secret to a file that git would commit.
if ! grep -qx '.env' .gitignore 2>/dev/null; then
  echo ".env is not listed in .gitignore. Refusing to save your key. Add '.env' to .gitignore and re-run."
  exit 1
fi
if grep -q '^ANTHROPIC_API_KEY=.' .env 2>/dev/null; then
  echo "Key already saved in .env (skipping). To replace it, delete .env and re-run."
else
  echo "Create one at https://console.anthropic.com -> API Keys (and add a few dollars of credit)."
  read -rsp "Paste your key here (it stays hidden as you type) and press Enter: " KEY
  echo
  if [ -z "$KEY" ]; then
    echo "No key entered. Skipping; re-run ./setup.sh when you have one."
  else
    if [[ "$KEY" != sk-ant-* ]]; then
      echo "Note: Anthropic keys usually start with 'sk-ant-'. Saving it anyway."
    fi
    echo "ANTHROPIC_API_KEY=$KEY" >> .env
    chmod 600 .env          # only your user account can read this file
    echo "Saved to .env"
  fi
fi

echo "== 5/5 Running tests (free, no AI calls) =="
.venv/bin/python -m unittest discover tests

echo
echo "All set. Next:"
echo "  source .venv/bin/activate"
echo "  python main.py run --fake      # practice run (uses a few cents of API credit)"

"""
make_demo_svg.py: turns a saved run into an animated "terminal replay" for the README.

    python scripts/make_demo_svg.py results/2026-11-26_haiku-5-5_cache-run1.txt

It reads the text a real run printed, keeps the interesting parts (tool calls, the
model's notes, the cost line, the guardrail catching a mistake, the final tracker) and
writes docs/demo.svg. Each line fades in one after another, then the replay loops.

Why an SVG instead of a screen recording? It's plain text, so it's tiny, sharp at
any size, needs no extra software, and is generated from a real run (no faking).
Standard library only.
"""

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "demo.svg"

MAX_CHARS = 110          # longer lines are cut with "..."
LINE_H, FONT = 18, 13    # pixels
CHAR_W = 7.85            # approx width of one monospace character at FONT px
DELAY, HOLD = 0.32, 7.0  # seconds between lines; seconds to hold the finished screen

COLORS = {"text": "#c9d1d9", "dim": "#8b949e", "cmd": "#7ee787", "step": "#79c0ff",
          "note": "#d2a8ff", "good": "#3fb950", "warn": "#e3b341", "head": "#f0f6fc"}


def pick_lines(raw: str) -> list[tuple[str, str]]:
    """Choose which lines to show, each paired with a color name."""
    log, _, rest = raw.partition("=== Actions taken ===")
    actions, _, rest = rest.partition("=== Agent summary ===")
    _, _, tracker = rest.partition("=== Tracker")

    lines = [("$ python main.py run --fake", "cmd")]
    seen = set()          # (company, role) pairs already given a status this run
    steps = [l.rstrip() for l in log.splitlines()]
    i = 0
    while i < len(steps):
        line = steps[i]
        m = re.match(r"\s+step (\d+): (\w+)\(", line)
        if m:
            # Collapse long runs of the same tool in the same step: show the first, count the rest.
            j = i
            while j + 1 < len(steps) and re.match(rf"\s+step {m[1]}: {m[2]}\(", steps[j + 1]):
                j += 1
            group = [_step_line(l, seen) for l in steps[i:j + 1]]
            # Always show the first call, plus any downgrade attempt (never hide the interesting part).
            shown = [g for k, g in enumerate(group) if k == 0 or g[1] == "warn"]
            lines.extend(shown)
            if len(group) > len(shown):
                lines.append((f"{' ' * 10}... +{len(group) - len(shown)} more {m[2]} calls", "dim"))
            i = j + 1
            continue
        if line.strip().startswith("thinking:"):
            lines.append((line.replace("thinking:", "model:", 1), "note"))
        elif line.startswith("[done"):
            head, sep, tail = line.partition(" | cost")
            lines.append((head, "good"))
            if sep:
                lines.append(("  " + sep.strip() + tail, "good"))
        elif line.startswith("Running agent"):
            lines.append((line, "dim"))
        elif not line.strip() and lines[-1][0]:
            lines.append(("", "text"))
        i += 1

    lines.append(("=== Guardrail check ===", "head"))
    for a in actions.splitlines():
        if "kept status" in a:
            lines.append((a.split(" (won't")[0] + "  <- downgrade blocked in code", "warn"))
        elif "Drafted" in a:
            lines.append(("- Drafted follow-up -> " + a.split("-> ")[-1] + "  (draft only, never sent)", "text"))
    lines.append(("", "text"))
    lines.append(("=== Tracker" + tracker.splitlines()[0], "head"))
    for row in tracker.splitlines()[1:]:
        if row.strip():
            lines.append((row, "dim" if row.startswith(("Company", "Full")) else "text"))
    return [(l if len(l) <= MAX_CHARS else l[: MAX_CHARS - 3] + "...", c) for l, c in lines]


def _step_line(line: str, seen: set) -> tuple[str, str]:
    """Shorten update_application lines to the parts that matter (company, role, status).
    A later 'applied' for a company that already has a status is the model trying to
    move it backwards, so it's highlighted."""
    m = re.match(r"(.*update_application\(company='([^']*)', role='([^']*)'.*?status='([^']*)')", line)
    if not m:
        return line, "step"
    application, status = (m[2], m[3]), m[4]      # one application = company + role
    color = "warn" if status == "applied" and application in seen else "step"
    seen.add(application)
    return m[1] + ", ...)", color


def render(lines: list[tuple[str, str]]) -> str:
    width = int(MAX_CHARS * CHAR_W + 48)
    top = 44
    height = top + LINE_H * len(lines) + 20
    cycle = DELAY * len(lines) + HOLD

    css, texts = [], []
    for n, (text, color) in enumerate(lines):
        start = 100 * (DELAY * n + 0.2) / cycle
        # Hidden until its turn, visible until the end of the cycle, then the replay restarts.
        css.append(f"@keyframes l{n}{{0%,{start:.2f}%{{opacity:0}}{start + 0.4:.2f}%,97%{{opacity:1}}100%{{opacity:0}}}}"
                   f".l{n}{{animation:l{n} {cycle:.1f}s linear infinite}}")
        y = top + LINE_H * (n + 1)
        texts.append(f'<text class="l{n}" x="24" y="{y}" fill="{COLORS[color]}" xml:space="preserve">'
                     f"{escape(text)}</text>")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Replay of a real practice run of the job application tracker agent">
<style>
text {{ font: {FONT}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre; }}
{chr(10).join(css)}
@media (prefers-reduced-motion: reduce) {{ text {{ animation: none !important; }} }}
</style>
<rect width="{width}" height="{height}" rx="10" fill="#0d1117"/>
<rect width="{width}" height="32" rx="10" fill="#161b22"/>
<rect y="22" width="{width}" height="10" fill="#161b22"/>
<circle cx="20" cy="16" r="6" fill="#ff5f56"/><circle cx="40" cy="16" r="6" fill="#ffbd2e"/><circle cx="60" cy="16" r="6" fill="#27c93f"/>
<text x="{width / 2}" y="21" text-anchor="middle" fill="#8b949e" style="font-size:12px">job-agent: replay of a real practice run (fictional inbox)</text>
{chr(10).join(texts)}
</svg>
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/make_demo_svg.py <saved run output .txt>")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(pick_lines(Path(sys.argv[1]).read_text())), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")

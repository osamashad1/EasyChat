"""Generate a complete static website (with 3D and motion graphics) from site-brief.md.

Fully automated loop:
  1. Claude writes every file from the brief.
  2. The static check (check_site.py) and the real-browser check (browser_check.mjs)
     look for broken links, accessibility gaps, JavaScript errors and layout overflow.
  3. Any problems are sent back to Claude, which returns a corrected site.
  4. Repeat until the site passes or --max-repairs is reached.

Usage: python scripts/generate_site.py [--brief site-brief.md] [--out site] [--effort high] [--max-repairs 2]
Needs ANTHROPIC_API_KEY in the environment. Writes run-report.json for the CI summary.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from check_site import find_problems  # noqa: E402

MODEL = "claude-opus-5-5"
ALLOWED_SUFFIXES = {".html", ".css", ".js", ".svg", ".json", ".txt", ".xml", ".webmanifest"}
PROTECTED_DIRS = {"assets/vendor"}  # vendored libraries (three.js) survive regeneration

SYSTEM = """You are a senior web designer, motion designer and front-end engineer.
You turn a website brief into a complete, production-ready static website.

Technology rules:
- Plain HTML, CSS and vanilla JavaScript only. No frameworks, no build step.
- three.js r149 is ALREADY in the site at assets/vendor/three.min.js (UMD build, global THREE).
  Load it with <script src="assets/vendor/three.min.js" defer></script>. Do not write that file
  and do not load three.js from a CDN. Note r149 uses renderer.outputEncoding = THREE.sRGBEncoding.
- No external images: draw icons and illustrations as inline SVG or in three.js.
- The entry page is index.html at the root. Use relative links only. Put shared CSS/JS in assets/.

3D and motion graphics (required):
- The home page hero has a real-time three.js 3D scene that fits the brand (for example floating
  objects, particles, light and gentle mouse parallax). It sits behind or beside the hero copy and
  never covers text: on narrow screens move it aside or lower its opacity.
- Guard the 3D code: if WebGL is unavailable or THREE is undefined, skip it and keep the CSS
  background. Pause rendering when the canvas is off screen or the tab is hidden. Cap pixel ratio at 2.
- Add tasteful motion graphics across the site: headline entrance, scroll-reveal sections,
  hover micro-interactions, animated counters or SVG line drawing where they fit the content.
- Content must be visible without JavaScript; only add hidden start states from JS.
- Respect prefers-reduced-motion: render one still 3D frame and turn off non-essential animation.

Quality rules:
- Every page: <html lang>, <title>, meta viewport, the same navigation, responsive down to 360px
  with no sideways scrolling, semantic HTML, alt text, labelled form fields, good contrast,
  light and dark mode via prefers-color-scheme.
- Real, specific copy from the brief. No lorem ipsum.
- Return every file the site needs with its full contents. When fixing problems, return the
  complete corrected set of files, not just the changed ones."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "files"],
    "additionalProperties": False,
}


def safe_path(out_dir: Path, rel: str) -> Path:
    """Keep model-written paths inside the output directory and away from vendored files."""
    root = out_dir.resolve()
    target = (root / rel).resolve()
    if root not in target.parents:
        raise ValueError(f"refusing path outside output dir: {rel}")
    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"refusing file type: {rel}")
    if any(str(target.relative_to(root)).startswith(d) for d in PROTECTED_DIRS):
        raise ValueError(f"refusing to overwrite vendored file: {rel}")
    return target


def clear_output(out_dir: Path) -> None:
    """Remove the previous site but keep protected (vendored) directories."""
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir.resolve()
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = str(path.relative_to(root))
        if any(rel == d or rel.startswith(d + "/") or d.startswith(rel + "/") for d in PROTECTED_DIRS):
            continue
        if path.is_dir():
            if not any(path.iterdir()):
                path.rmdir()
        else:
            path.unlink()


def write_site(out_dir: Path, files: list[dict]) -> list[str]:
    clear_output(out_dir)
    written, skipped = [], []
    for f in files:
        try:
            target = safe_path(out_dir, f["path"])
        except ValueError as e:
            skipped.append(str(e))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
        written.append(f["path"])
    for s in skipped:
        print(f"  skipped: {s}")
    return written


def browser_problems(out_dir: Path) -> list[str]:
    """Run the Playwright check if Node + Playwright are available; otherwise skip it."""
    script = Path(__file__).parent / "browser_check.mjs"
    if shutil.which("node") is None:
        return []
    proc = subprocess.run(
        ["node", str(script), str(out_dir), "screenshots", "--json"],
        capture_output=True, text=True, timeout=600,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])["errors"]
    except (IndexError, ValueError, KeyError):
        if "Cannot find package 'playwright'" in proc.stderr:
            print("  (browser check skipped: Playwright not installed)")
            return []
        return [f"browser check crashed: {proc.stderr.strip()[-500:]}"]


def ask_claude(client, messages, effort):
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=128000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        # If a safety classifier declines, the API retries on a suitable fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=messages,
    ) as stream:
        return stream.get_final_message()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", default="site-brief.md")
    parser.add_argument("--out", default="site")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-repairs", type=int, default=2)
    args = parser.parse_args()

    started = time.time()
    brief = Path(args.brief).read_text(encoding="utf-8")
    out_dir = Path(args.out)
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": f"Build the website described in this brief:\n\n{brief}"}]
    report = {"model": MODEL, "effort": args.effort, "attempts": [], "input_tokens": 0, "output_tokens": 0}

    for attempt in range(args.max_repairs + 1):
        label = "generate" if attempt == 0 else f"repair {attempt}"
        print(f"[{label}] asking Claude...")
        message = ask_claude(client, messages, args.effort)
        report["input_tokens"] += message.usage.input_tokens
        report["output_tokens"] += message.usage.output_tokens

        if message.stop_reason == "refusal":
            print("Claude declined this brief. Edit site-brief.md and try again.", file=sys.stderr)
            return 1
        if message.stop_reason == "max_tokens":
            print("Output was cut off (max_tokens). Simplify the brief or reduce pages.", file=sys.stderr)
            return 1

        data = json.loads(next(b.text for b in message.content if b.type == "text"))
        written = write_site(out_dir, data["files"])
        print(f"[{label}] wrote {len(written)} files: {data['summary'][:200]}")

        problems = find_problems(str(out_dir)) + browser_problems(out_dir)
        report["attempts"].append({"step": label, "files": len(written), "problems": problems})
        if not problems:
            print(f"[{label}] all checks passed.")
            break

        print(f"[{label}] {len(problems)} problem(s) found:")
        for p in problems:
            print(f"  - {p}")
        if attempt == args.max_repairs:
            print("Repair limit reached; the pipeline will stop at the quality gate.")
            break
        # Self-repair: keep the conversation and send the problems back
        messages.append({"role": "assistant", "content": message.content})
        messages.append({"role": "user", "content": (
            "Automated checks found these problems in the site you returned:\n- "
            + "\n- ".join(problems)
            + "\n\nFix all of them and return the complete corrected set of files."
        )})

    report["seconds"] = round(time.time() - started, 1)
    report["passed"] = not report["attempts"][-1]["problems"]
    Path("run-report.json").write_text(json.dumps(report, indent=2))
    print(f"tokens: in={report['input_tokens']} out={report['output_tokens']} time={report['seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

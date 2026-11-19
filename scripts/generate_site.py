"""Generate a static website from site-brief.md with the Claude API.

Usage: python scripts/generate_site.py [--brief site-brief.md] [--out site]
Needs ANTHROPIC_API_KEY in the environment.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
ALLOWED_SUFFIXES = {".html", ".css", ".js", ".svg", ".json", ".txt", ".xml", ".webmanifest"}

SYSTEM = """You are a senior web designer and front-end engineer.
You turn a website brief into a complete, production-ready static website.
Rules:
- Output only plain HTML, CSS, vanilla JS and inline SVG. No frameworks, no build step,
  no external images (draw icons and illustrations as inline SVG).
- The entry page must be index.html at the root. Use relative links only.
- Every page must be responsive, accessible (semantic HTML, labels, alt text, contrast)
  and share the same navigation.
- Write real, specific copy from the brief, not lorem ipsum.
- Return every file the site needs, with its full contents."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "files"],
    "additionalProperties": False,
}


def safe_path(out_dir: Path, rel: str) -> Path:
    """Keep model-written paths inside the output directory."""
    target = (out_dir / rel).resolve()
    if out_dir.resolve() not in target.parents and target != out_dir.resolve():
        raise ValueError(f"refusing path outside output dir: {rel}")
    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"refusing file type: {rel}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", default="site-brief.md")
    parser.add_argument("--out", default="site")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    args = parser.parse_args()

    brief = Path(args.brief).read_text(encoding="utf-8")
    out_dir = Path(args.out)

    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={
            "effort": args.effort,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        # If a safety classifier declines, retry on a suitable fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": f"Build the website described in this brief:\n\n{brief}"}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        print("Claude declined this brief. Edit site-brief.md and try again.", file=sys.stderr)
        return 1
    if message.stop_reason == "max_tokens":
        print("Output was cut off (max_tokens). Simplify the brief or reduce pages.", file=sys.stderr)
        return 1

    text = next(b.text for b in message.content if b.type == "text")
    data = json.loads(text)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for f in data["files"]:
        target = safe_path(out_dir, f["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
        print(f"wrote {target.relative_to(out_dir.resolve())}")

    print(f"\n{data['summary']}")
    print(f"tokens: in={message.usage.input_tokens} out={message.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

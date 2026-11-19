# EasyChat — AI Website Pipeline

Write a brief, push, get a live website. Claude writes the site, a quality
gate checks it, and GitHub Pages publishes it.

```
site-brief.md ──push──▶ Claude generates site/ ──▶ check_site.py ──▶ PR preview / GitHub Pages
```

## Setup (once)

1. **Settings → Secrets and variables → Actions** → add `ANTHROPIC_API_KEY`.
2. **Settings → Pages** → Source: **GitHub Actions**.
3. Edit `site-brief.md`, push to `main`, and watch the **Actions** tab.

## What runs when

| Event | Result |
|---|---|
| Pull request changing the brief/scripts | Generate + check, preview uploaded as `site-preview` artifact |
| Push to `main` | Generate + check + deploy to GitHub Pages |
| Manual "Run workflow" | Same as push, with an effort level you choose |

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/generate_site.py --effort medium
python scripts/check_site.py site
python -m http.server -d site 8000
```

## Files

- `site-brief.md` — the only file you need to edit
- `scripts/generate_site.py` — calls Claude (structured JSON output), writes files to `site/` (path-confined, web file types only)
- `scripts/check_site.py` — fails on broken links, missing alt/title/lang/viewport
- `.github/workflows/ai-website.yml` — build → check → preview/deploy
- `docs/workflow.html` — visual guide to the pipeline

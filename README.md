# EasyChat — Fully Automated AI Website Pipeline

Write a brief, push, get a live website with 3D and motion graphics.
Claude writes the site, two quality gates test it, Claude repairs anything that
fails, and GitHub Pages publishes it — with no manual step in between.

```
site-brief.md ─push─▶ Claude builds site/ (three.js 3D + motion)
                     ─▶ static check ─▶ real-browser check (desktop + phone, screenshots)
                     ─▶ problems? ─▶ Claude repairs (up to 2 rounds) ─▶ re-check
                     ─▶ PR: preview + comment │ main: commit site + deploy to Pages
```

The finished EasyChat site is already in `site/` (4 pages, passes both gates).
Guide: `docs/workflow.html` · PDF: `docs/AI-Website-Pipeline-Guide.pdf`

## Setup (once)

1. **Settings → Secrets and variables → Actions** → add `ANTHROPIC_API_KEY`.
2. **Settings → Pages** → Source: **GitHub Actions**.
3. Merge to `main`. Then edit `site-brief.md` and push to rebuild.

Without a key, the pipeline still checks and deploys the committed `site/`.

## Run locally

```bash
pip install -r requirements.txt
npm install && npx playwright install chromium
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/generate_site.py --effort medium   # generate + self-repair
npm run check                                     # both quality gates
npm run pdf                                       # rebuild the PDF guide
python -m http.server -d site 8000
```

## Files

| Path | Purpose |
|---|---|
| `site-brief.md` | The only file you need to edit |
| `site/` | Finished website; three.js r149 bundled in `assets/vendor/` |
| `scripts/generate_site.py` | Claude generation + self-repair loop, writes `run-report.json` |
| `scripts/check_site.py` | Gate 1: links, alt text, title, lang, viewport |
| `scripts/browser_check.mjs` | Gate 2: Chromium at 1366px and 390px — JS errors, overflow, 3D canvas, screenshots |
| `scripts/make_pdf.mjs` | Exports the guide to PDF |
| `.github/workflows/ai-website.yml` | The automation |

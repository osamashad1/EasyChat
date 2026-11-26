"""Job Agent: finds English-friendly student jobs in Germany, scores them against your CV
with Claude, and drafts tailored application material. You review and press Submit.

  python job-agent/agent.py --config path/to/agent-profile.yml           # full run
  python job-agent/agent.py --config path/to/agent-profile.yml --no-ai   # free run, rules only

Outputs (in the config's output_dir):
  report-YYYY-MM-DD.html   ranked jobs with reasons and apply links (open in a browser)
  drafts/                  tailored CV summary, bullets and cover letter per top job
  tracker.csv              every job found, with score and a status column you update
  career-ops-pipeline.md   top jobs as a career-ops inbox (for deeper evaluation)
  seen.json                jobs already processed, so each run only shows new ones
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import rules  # noqa: E402
import sources  # noqa: E402


def log(msg):
    print(msg, flush=True)


def load_config(path):
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    base = path.parent
    cfg["_cv_path"] = (base / cfg.get("cv_file", "cv.md")).resolve()
    cfg["_out"] = (base / cfg.get("output_dir", "job-results")).resolve()
    return cfg


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def collect(cfg):
    log("1/5 Searching job boards...")
    jobs = []
    ba = cfg.get("arbeitsagentur")
    if ba:
        jobs += sources.arbeitsagentur(ba["searches"], days=ba.get("days", 21), log=log)
    an = cfg.get("arbeitnow")
    if an:
        jobs += sources.arbeitnow(an.get("max_pages", 5), an.get("regions"), log=log)
    return jobs


def prescreen(cfg, jobs, seen):
    limits = cfg.get("limits", {})
    new = [j for j in jobs if j["id"] not in seen]
    log(f"2/5 Pre-screening {len(new)} new postings ({len(jobs) - len(new)} seen in earlier runs)...")
    for j in new:
        rules.prescreen(j)
    # Fetch full descriptions for the most promising Arbeitsagentur hits
    need = sorted([j for j in new if j["source"] == "Arbeitsagentur" and not j["pre"]["senior"]],
                  key=lambda j: -j["pre"]["score"])[: limits.get("details_for_top", 250)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(sources.arbeitsagentur_details, need))
    for j in new:
        rules.prescreen(j)
    keep = [j for j in new
            if j["pre"]["score"] >= limits.get("min_prescore", 45)
            and not j["pre"]["senior"] and not j["pre"]["german_required"]]
    keep.sort(key=lambda j: (-j["pre"]["score"], j.get("distance_km") or 0))
    # One advert per company + title (chains post the same job for every branch)
    groups = {}
    for j in keep:
        key = (j["company"].lower()[:30], re.sub(r"\W+", " ", j["title"].lower()).strip())
        if key in groups:
            groups[key]["other_locations"].append(j["location"])
        else:
            j["other_locations"] = []
            groups[key] = j
    keep = list(groups.values())[: limits.get("report_max", 60)]
    log(f"  {len(keep)} passed (dropped: German B2+ required, senior roles, low fit)")
    return new, keep


def ai_stage(cfg, keep, use_ai):
    limits = cfg.get("limits", {})
    if not use_ai:
        log("3/5 AI scoring skipped (--no-ai). Ranking by rules only.")
        return None, []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("3/5 AI scoring skipped: ANTHROPIC_API_KEY is not set. Ranking by rules only.")
        return None, []
    from ai import Advisor  # imported only when needed

    advisor = Advisor(cfg["_cv_path"].read_text(encoding="utf-8"), cfg.get("preferences", ""),
                      model=cfg.get("model", "claude-opus-5-5"))
    top = keep[: limits.get("ai_score_top", 30)]
    log(f"3/5 Claude is scoring the top {len(top)} jobs against your CV...")

    def score_one(j):
        try:
            j["ai"] = advisor.score(j)
        except Exception as e:  # one failure should not stop the run
            j["ai"] = None
            log(f"  scoring failed for {j['title'][:50]}: {e}")
        return j

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(score_one, top))
    scored = sorted([j for j in top if j.get("ai")], key=lambda j: -j["ai"]["score"])
    best = [j for j in scored if j["ai"]["score"] >= limits.get("drafts_for_score_at_least", 4)
            and j["ai"]["verdict"] != "skip"][: limits.get("max_drafts", 8)]
    log(f"4/5 Drafting tailored CV text and cover letters for {len(best)} best matches...")
    drafts_dir = cfg["_out"] / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    for j in best:
        try:
            d = advisor.draft(j)
        except Exception as e:
            log(f"  drafting failed for {j['title'][:50]}: {e}")
            continue
        if not d:
            continue
        path = drafts_dir / f"{dt.date.today()}-{slug(j['company'])}-{slug(j['title'])}.md"
        path.write_text(
            f"# {j['title']} — {j['company']}\n\nApply: {j['url']}\n\n"
            f"Score {j['ai']['score']}/5 · {j['ai']['one_line']}\n\n"
            f"## CV headline\n{d['cv_headline']}\n\n## CV summary\n{d['cv_summary']}\n\n"
            f"## Put these points first\n" + "\n".join(f"- {b}" for b in d["cv_bullets_to_highlight"]) +
            f"\n\n## Skills to list first\n{', '.join(d['skills_to_list_first'])}\n\n"
            f"## Cover letter\n\n{d['cover_letter']}\n\n## Email subject\n{d['email_subject']}\n\n"
            f"## Short message (portal / LinkedIn)\n{d['short_message']}\n\n"
            "_Check every line before sending. Claude was told to use only facts from your CV._\n",
            encoding="utf-8")
        j["draft_file"] = str(path.relative_to(cfg["_out"]))
    return advisor, scored


def rank(keep, scored):
    if scored:
        rest = [j for j in keep if not j.get("ai")]
        return scored + rest
    return keep


def write_outputs(cfg, ranked, advisor, stats):
    out = cfg["_out"]
    out.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    log("5/5 Writing report, tracker and career-ops inbox...")

    # Tracker (append)
    tracker = out / "tracker.csv"
    new_file = not tracker.exists()
    with tracker.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["found", "score", "verdict", "title", "company", "location", "english",
                        "source", "url", "draft", "status", "notes"])
        for j in ranked:
            ai = j.get("ai") or {}
            w.writerow([today, ai.get("score", round(j["pre"]["score"] / 20, 1)), ai.get("verdict", ""),
                        j["title"], j["company"], j["location"],
                        "yes" if (ai.get("english_ok") or j["pre"]["english_friendly"]) else "check",
                        j["source"], j["url"], j.get("draft_file", ""), "new", ""])

    # career-ops inbox
    top = [j for j in ranked if (j.get("ai") or {}).get("score", 0) >= 3.5] or ranked[:15]
    (out / "career-ops-pipeline.md").write_text(
        "# Pipeline\n\n## Pending\n\n" +
        "".join(f"- [ ] {j['url']} | {j['company']} | {j['title']}\n" for j in top), encoding="utf-8")

    # Machine-readable results (used by the browser Job Finder page)
    def export(j):
        ai = j.get("ai") or {}
        return {
            "id": re.sub(r"[^A-Za-z0-9_-]", "_", j["id"])[:120],
            "title": j["title"], "company": j["company"], "location": j["location"],
            "url": j["url"], "posted": j["posted"], "source": j["source"],
            "distance_km": j.get("distance_km"), "remote": j["remote"],
            "language": j["pre"]["language"], "student_type": j["pre"]["student_type"],
            "prescore": j["pre"]["score"], "other_locations": len(j.get("other_locations") or []),
            "description": j["description"][:4000], "found": today,
            **({"aiScore": ai["score"], "verdict": ai["verdict"], "oneLine": ai["one_line"],
                "why": ai["why"], "gaps": ai["gaps"], "germanLevel": ai["german_level_needed"],
                "pay": ai["pay"]} if ai else {}),
        }
    (out / "jobs.json").write_text(json.dumps({"date": today, "found": stats["found"], "new": stats["new"],
                                               "jobs": [export(j) for j in ranked]}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    # HTML report
    report = out / f"report-{today}.html"
    report.write_text(render_html(ranked, advisor, stats, today), encoding="utf-8")
    log(f"\nDone. Open {report}")
    if advisor:
        u = advisor.usage
        log(f"Claude usage: {u['input']:,} input ({u['cache_read']:,} from cache) / {u['output']:,} output tokens")


def render_html(ranked, advisor, stats, today):
    e = html.escape

    def card(j):
        ai = j.get("ai") or {}
        p = j["pre"]
        score = ai.get("score")
        badge = f"AI score {score:.1f}/5" if score is not None else f"Rules match {p['score']}/100"
        tone = "good" if (score or 0) >= 4 else "ok" if (score or 0) >= 3 or (score is None and p["score"] >= 70) else "low"
        chips = []
        chips.append("English posting" if p["language"] == "en" else "German posting" if p["language"] == "de" else "Mixed language")
        if p["student_type"]:
            chips.append("Student-friendly")
        if j["remote"]:
            chips.append("Home office")
        if j.get("distance_km") is not None:
            chips.append(f"{j['distance_km']} km")
        if j.get("other_locations"):
            chips.append(f"+{len(j['other_locations'])} more locations")
        if ai.get("german_level_needed"):
            chips.append("German: " + ai["german_level_needed"])
        if ai.get("pay"):
            chips.append(ai["pay"])
        why = "".join(f"<li>{e(x)}</li>" for x in ai.get("why", []))
        gaps = "".join(f"<li>{e(x)}</li>" for x in ai.get("gaps", []))
        draft = f'<a class="draft" href="{e(j["draft_file"])}">Open tailored draft</a>' if j.get("draft_file") else ""
        return f"""<article class="card {tone}">
  <div class="top"><span class="badge">{e(badge)}</span><span class="src">{e(j['source'])} · {e(j['posted'])}</span></div>
  <h2><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></h2>
  <p class="co">{e(j['company'])} · {e(j['location'])}</p>
  {f'<p class="line">{e(ai["one_line"])}</p>' if ai.get("one_line") else ''}
  <div class="chips">{''.join(f'<span>{e(c)}</span>' for c in chips)}</div>
  {f'<details><summary>Why it fits / what is missing</summary><ul class="why">{why}</ul><ul class="gaps">{gaps}</ul></details>' if why or gaps else ''}
  <div class="actions"><a class="apply" href="{e(j['url'])}" target="_blank" rel="noopener">View &amp; apply</a>{draft}</div>
</article>"""

    usage = ""
    if advisor:
        u = advisor.usage
        usage = f" · Claude: {u['input']:,} in / {u['output']:,} out tokens"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Job matches {today}</title>
<style>
:root{{--bg:#f5f7fa;--card:#fff;--fg:#17202c;--muted:#5d6878;--line:#dfe5ec;--good:#1d8a5a;--ok:#2f6fdf;--low:#98a2b3}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f141b;--card:#18202b;--fg:#e7ecf2;--muted:#9aa6b6;--line:#2a3443;--good:#46c08a;--ok:#6ea3ff;--low:#5d6878}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;padding:24px 16px}}
main{{max-width:900px;margin:0 auto;display:grid;gap:14px}}h1{{margin:0;font-size:26px}}.meta{{color:var(--muted)}}
.card{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--low);border-radius:10px;padding:16px 18px;display:grid;gap:6px}}
.card.good{{border-left-color:var(--good)}}.card.ok{{border-left-color:var(--ok)}}
.top{{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}}.badge{{font-weight:700}}.good .badge{{color:var(--good)}}.ok .badge{{color:var(--ok)}}
.src,.co{{color:var(--muted);font-size:13.5px;margin:0}}h2{{margin:0;font-size:17px}}h2 a{{color:inherit}}.line{{margin:0}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}.chips span{{font-size:12px;border:1px solid var(--line);border-radius:99px;padding:2px 9px;color:var(--muted)}}
details{{font-size:14px}}.why li::marker{{content:"+ "}}.gaps li::marker{{content:"- "}}
.actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}}.actions a{{font-weight:600;font-size:14px;padding:7px 14px;border-radius:8px;text-decoration:none}}
.apply{{background:var(--ok);color:#fff}}.draft{{border:1px solid var(--line);color:var(--fg)}}
</style></head><body><main>
<h1>Job matches · {today}</h1>
<p class="meta">{stats['found']} postings found · {stats['new']} new · {len(ranked)} worth a look{usage}</p>
{''.join(card(j) for j in ranked) or '<p>No new matches today. The agent will look again on the next run.</p>'}
<p class="meta">You decide and you submit. Check every tailored draft before sending.</p>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="path to your agent-profile.yml")
    ap.add_argument("--no-ai", action="store_true", help="rules only, no Claude calls (free)")
    ap.add_argument("--reset", action="store_true", help="forget previously seen jobs")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg["_out"].mkdir(parents=True, exist_ok=True)
    seen_path = cfg["_out"] / "seen.json"
    seen = set() if args.reset or not seen_path.exists() else set(json.loads(seen_path.read_text()))

    jobs = collect(cfg)
    new, keep = prescreen(cfg, jobs, seen)
    advisor, scored = ai_stage(cfg, keep, use_ai=not args.no_ai)
    ranked = rank(keep, scored)
    write_outputs(cfg, ranked, advisor, {"found": len(jobs), "new": len(new)})
    seen_path.write_text(json.dumps(sorted(seen | {j["id"] for j in new})))


if __name__ == "__main__":
    main()

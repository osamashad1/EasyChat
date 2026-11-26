# Job Agent

An AI job finder for international students in Germany. Every run, it:

1. **Searches** the Federal Employment Agency (Arbeitsagentur, ~all German job ads) and
   Arbeitnow (English-friendly board) with your keywords, cities and job types.
2. **Pre-screens for free** with rules: drops jobs that need fluent German (B2+), senior roles,
   full-time-only jobs, vocational training, and anything outside Germany; groups chain adverts
   (one Netto job, not 40 branches); ranks English postings, student jobs and career-relevant
   work higher.
3. **Scores** the best 30 with Claude against your CV and the student work rules (1–5, with
   reasons, gaps, German level needed, pay).
4. **Drafts** tailored CV summary, bullet order and a cover letter for every job scoring 4+.
   Claude may only use facts from your CV.
5. **Reports**: a ranked HTML page with apply links, a `tracker.csv`, and a career-ops inbox.
   Each run only shows jobs it has not shown you before.

It never applies, sends or submits anything. You read, you decide, you press Submit.

## Setup (once, on your computer)

```bash
git clone https://github.com/osamashad1/EasyChat.git
pip install -r EasyChat/job-agent/requirements.txt
```

Put your private files in a folder **outside** this repo (it is public), e.g. `~/job-kit/`:
`cv.md` and `agent-profile.yml` (see the example below). Then:

```bash
python EasyChat/job-agent/agent.py --config ~/job-kit/agent-profile.yml --no-ai   # free test run
export ANTHROPIC_API_KEY=sk-ant-...       # Windows: setx ANTHROPIC_API_KEY sk-ant-...
python EasyChat/job-agent/agent.py --config ~/job-kit/agent-profile.yml           # full AI run
```

Open `~/job-kit/job-results/report-<date>.html` in your browser.

## Run it automatically every morning

**Windows** (Task Scheduler, from PowerShell):
```powershell
schtasks /Create /SC DAILY /ST 07:30 /TN "Job Agent" /TR "python C:\path\EasyChat\job-agent\agent.py --config C:\path\job-kit\agent-profile.yml"
```
**macOS / Linux** (`crontab -e`):
```
30 7 * * * cd ~ && python3 EasyChat/job-agent/agent.py --config ~/job-kit/agent-profile.yml >> ~/job-kit/agent.log 2>&1
```

## Cost

The free `--no-ai` mode costs nothing. A full run scores up to 30 jobs (short, low-effort calls
with the CV cached) and drafts up to 8 applications; check the token count printed at the end.
Lower `ai_score_top` / `max_drafts` in your profile to spend less.

## Use it with career-ops

Each run writes `career-ops-pipeline.md`. Copy its lines into career-ops' `data/pipeline.md`
and run `/career-ops pipeline` for the full A–H evaluation and a tailored PDF CV.

## Config example (`agent-profile.yml`)

```yaml
cv_file: cv.md
output_dir: job-results
preferences: |
  Non-EU student, German A1, English fluent. Wants Werkstudent / minijob / internship in logistics.
arbeitsagentur:
  days: 21
  searches:
    - where: Duisburg
      radius_km: 30
      offer_types: [job, internship_or_working_student]   # job, internship_or_working_student
      hours: [part_time, minijob]                          # optional: part_time, minijob, shifts, home_office
      keywords: [Werkstudent Logistik, Working Student]
arbeitnow:
  max_pages: 5
  regions: [Duisburg, Düsseldorf, Essen]
limits: {min_prescore: 55, details_for_top: 250, report_max: 60, ai_score_top: 30,
         drafts_for_score_at_least: 4, max_drafts: 8}
```

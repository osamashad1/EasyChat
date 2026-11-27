"""Job sources: Bundesagentur fuer Arbeit (Jobsuche API) and Arbeitnow.

Both are public. Each source returns a list of dicts in one common shape:
  id, source, title, company, location, distance_km, url, posted, description,
  job_type, remote, raw_flags
"""
import base64
import html
import math
import json
import re
import time
import urllib.parse
import urllib.request

UA = "job-agent/1.0 (personal job search; contact via GitHub)"
BA_SEARCH = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
BA_DETAIL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
BA_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"
BA_KEY = "jobboerse-jobsuche"  # public key used by arbeitsagentur.de itself
ARBEITNOW = "https://www.arbeitnow.com/api/job-board-api"


def _get_json(url, headers=None, retries=2):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                return None
            if attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(1.5 * (attempt + 1))


def strip_html(text):
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text or "", flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


# ---------------------------------------------------------------- Arbeitsagentur
BA_TYPES = {"job": 1, "internship_or_working_student": 34}
BA_HOURS = {"part_time": "tz", "minijob": "mj", "shifts": "snw", "home_office": "ho"}


def km_between(a, b):
    """Great-circle distance in km between two (lat, lon) points."""
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)))


def arbeitsagentur(searches, days=21, size=50, log=print, home=None):
    """searches: list of {keywords:[...], where:'Duisburg', radius_km:30,
    offer_types:['job','internship_or_working_student'], hours:['part_time','minijob']}"""
    found = {}
    for s in searches:
        for kw in s["keywords"]:
            for ot in s.get("offer_types", ["job"]):
                params = {
                    "was": kw, "size": size, "page": 1, "veroeffentlichtseit": days,
                    "angebotsart": BA_TYPES[ot],
                }
                if s.get("where"):
                    params.update({"wo": s["where"], "umkreis": s.get("radius_km", 30)})
                if s.get("hours"):
                    params["arbeitszeit"] = ";".join(BA_HOURS[h] for h in s["hours"])
                url = BA_SEARCH + "?" + urllib.parse.urlencode(params)
                try:
                    data = _get_json(url, {"X-API-Key": BA_KEY}) or {}
                except Exception as e:  # keep going if one query fails
                    log(f"  arbeitsagentur '{kw}' failed: {e}")
                    continue
                for j in data.get("ergebnisliste", []):
                    ref = j.get("referenznummer")
                    if not ref or ref in found:
                        continue
                    # A nationwide search (no city) is only for home-office jobs: the API's
                    # home-office filter is loose, so drop on-site jobs far from home here.
                    if not s.get("where") and not j.get("homeofficemoeglich"):
                        continue
                    place = (j.get("stellenlokationen") or [{}])[0]
                    loc = place.get("adresse", {})
                    # Distance from the candidate's home, not from this search's centre city
                    dist = j.get("entfernung")
                    if home and place.get("breite") is not None and place.get("laenge") is not None:
                        dist = km_between(home, (place["breite"], place["laenge"]))
                    found[ref] = {
                        "id": "ba:" + ref,
                        "source": "Arbeitsagentur",
                        "title": j.get("stellenangebotsTitel", ""),
                        "company": j.get("firma", ""),
                        "location": " ".join(x for x in [loc.get("plz"), loc.get("ort")] if x),
                        "distance_km": dist,
                        "lat": place.get("breite"), "lon": place.get("laenge"),
                        "url": BA_PAGE + urllib.parse.quote(ref, safe=""),
                        "posted": j.get("datumErsteVeroeffentlichung", ""),
                        "description": "",
                        "job_type": j.get("stellenangebotsart", ""),
                        "remote": bool(j.get("homeofficemoeglich")),
                        "raw_flags": {
                            "minijob": bool(j.get("istGeringfuegigeBeschaeftigung")),
                            "full_time_only": bool(j.get("arbeitszeitVollzeit")) and not any(
                                j.get(k) for k in ("arbeitszeitTeilzeitVormittag", "arbeitszeitTeilzeitNachmittag",
                                                   "arbeitszeitTeilzeitAbend", "arbeitszeitTeilzeitFlexibel")),
                            "career_changer_ok": bool(j.get("quereinstiegGeeignet")),
                            "shifts": bool(j.get("arbeitszeitSchichtNachtWochenende")),
                        },
                    }
                time.sleep(0.25)
    log(f"  Arbeitsagentur: {len(found)} unique postings")
    return list(found.values())


def arbeitsagentur_details(job):
    ref = job["id"].split(":", 1)[1]
    d = _get_json(BA_DETAIL + base64.b64encode(ref.encode()).decode(), {"X-API-Key": BA_KEY})
    if d:
        job["description"] = strip_html(d.get("stellenangebotsBeschreibung", ""))
    return job


# ---------------------------------------------------------------- Arbeitnow
def arbeitnow(max_pages=5, regions=None, log=print):
    """Arbeitnow's whole board, newest first; keeps Germany + remote."""
    out = []
    for page in range(1, max_pages + 1):
        data = _get_json(f"{ARBEITNOW}?page={page}") or {}
        rows = data.get("data", [])
        for j in rows:
            loc = j.get("location", "")
            if regions and not j.get("remote") and not any(r.lower() in loc.lower() for r in regions):
                continue
            out.append({
                "id": "an:" + j["slug"],
                "source": "Arbeitnow",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": loc + (" (remote)" if j.get("remote") else ""),
                "distance_km": None,
                "url": j.get("url", ""),
                "posted": time.strftime("%Y-%m-%d", time.gmtime(j.get("created_at", 0))),
                "description": strip_html(j.get("description", "")),
                "job_type": ", ".join(j.get("job_types") or []),
                "remote": bool(j.get("remote")),
                "raw_flags": {},
            })
        if len(rows) < 100:
            break
        time.sleep(0.5)
    log(f"  Arbeitnow: {len(out)} postings in your regions or remote")
    return out

"""Free, instant pre-screening (no AI): language, German level, job type, seniority."""
import datetime as dt
import re

EN_WORDS = {"the", "and", "you", "with", "for", "our", "are", "your", "will", "we", "team", "to", "of", "in", "is", "as", "an", "on", "be", "or"}
DE_WORDS = {"und", "die", "der", "das", "mit", "für", "wir", "sie", "du", "ist", "eine", "ein", "zu", "auf", "bei", "von", "den", "dich", "unsere", "oder"}


def posting_language(text):
    words = re.findall(r"[a-zäöüß]+", (text or "").lower())
    if len(words) < 25:
        return "unknown"
    en = sum(w in EN_WORDS for w in words)
    de = sum(w in DE_WORDS for w in words)
    if en > de * 1.5:
        return "en"
    if de > en * 1.5:
        return "de"
    return "mixed"


# German required at a level a beginner (A1/A2) cannot meet
GERMAN_REQUIRED = [
    r"(fließend|fliessend|verhandlungssicher|sehr gute?|gute?|exzellente?|perfekte?)\w*\s+(deutsch|deutschkenntnisse)",
    r"deutsch\w*\s*(kenntnisse)?\s*(in wort und schrift|auf (mindestens )?(b2|c1|c2)|\((b2|c1|c2)\)|\s(b2|c1|c2)\b)",
    r"(fluent|native|proficient|business[- ]level|very good|excellent|strong)\s+(command of\s+)?german",
    r"german\s*\(?\s*(b2|c1|c2|native|fluent)",
    r"german (is|are) (a )?(must|required|mandatory)",
    r"muttersprache deutsch|deutsch als muttersprache",
]
GERMAN_NOT_NEEDED = [
    r"no german (required|needed|necessary)",
    r"german (is )?(not required|a plus|nice to have|is a bonus|optional)",
    r"(english|englisch)[- ]speaking",
    r"working language (is )?english",
    r"(keine|ohne) deutschkenntnisse",
    r"deutschkenntnisse (sind )?(nicht erforderlich|kein muss|von vorteil)",
]
SENIOR = r"\b(senior|lead|head of|principal|director|leiter|leitung|teamleitung|manager(in)?\b(?! ?trainee)|mehrjährige|several years|\b[3-9]\+? years)"
ENTRY_TERMS = r"(junior|entry[- ]level|einstieg|berufseinsteiger|trainee|quereinsteiger|no experience|keine (berufs)?erfahrung|ohne vorkenntnisse|graduate|absolvent)"
HANDS_ON = r"(lager|kommission|logistik|picker|packer|versand|warehouse|fulfil|hub|zusteller|fahrrad|rider|reinigung|produktionshelfer)"
GERMANY = r"(germany|deutschland|deutschlandweit|nrw|nordrhein|berlin|hamburg|münchen|munich|köln|cologne|düsseldorf|frankfurt|duisburg|essen|dortmund)"
NOT_FOR_YOU = r"(schülerpraktikum|schulpraktikum|ausbildung\b|azubi|auszubildende|duales studium|freiwilliges soziales)"
CAREER_RELEVANT = r"(logisti|supply chain|scm|spedition|lager|warehouse|operations|einkauf|procurement|transport|mobilit|it[- ]support|helpdesk|marketing|social media|video|grafik|design|e-commerce|data|excel)"
STUDENT_TERMS = r"(werkstudent|working student|student assistant|studentische|minijob|aushilfe|teilzeit|part[- ]time|praktikum|internship|intern\b|nebenjob|student job|hiwi|ferienjob)"


def prescreen(job):
    text = f"{job['title']}\n{job['description']}"
    low = text.lower()
    lang = posting_language(job["description"] or job["title"])
    german_required = any(re.search(p, low) for p in GERMAN_REQUIRED)
    german_ok = any(re.search(p, low) for p in GERMAN_NOT_NEEDED)
    senior = bool(re.search(SENIOR, job["title"].lower())) or bool(re.search(r"\b[3-9]\+? (years|jahre)", low))
    student_type = bool(re.search(STUDENT_TERMS, low)) or job["raw_flags"].get("minijob") or \
        job["job_type"] in ("PRAKTIKUM_TRAINEE",)
    entry = bool(re.search(ENTRY_TERMS, low))
    hands_on = bool(re.search(HANDS_ON, job["title"].lower()))
    in_germany = job["source"] == "Arbeitsagentur" or bool(re.search(GERMANY, (job["location"] + " " + low[:3000])))
    full_time_only = job["raw_flags"].get("full_time_only", False) or bool(
        re.search(r"\b(full[- ]time|vollzeit)\b", job["title"].lower()))

    score = 50
    score += {"en": 25, "mixed": 8, "unknown": 0, "de": -20}[lang]
    if lang == "de" and hands_on and not german_required:
        score += 12  # warehouse/hub work: little German needed day to day
    score += 15 if german_ok else 0
    score -= 35 if german_required and not german_ok else 0
    score += 15 if student_type else 0
    score += 5 if entry else 0
    score -= 25 if not (student_type or entry or hands_on) else 0  # beginner level only
    score -= 30 if senior else 0
    score -= 20 if full_time_only else 0
    score -= 40 if not in_germany else 0
    score += 10 if re.search(CAREER_RELEVANT, job["title"].lower()) else 0
    score -= 60 if re.search(NOT_FOR_YOU, job["title"].lower()) else 0
    try:  # adverts first posted long ago and re-listed are often stale
        age = (dt.date.today() - dt.date.fromisoformat(job["posted"][:10])).days
        score -= 15 if age > 120 else 0
    except ValueError:
        pass
    if job.get("distance_km") is not None:
        score -= min(15, max(0, (job["distance_km"] - 20) // 5))
    job["pre"] = {
        "score": max(0, min(100, score)),
        "language": lang,
        "german_required": german_required and not german_ok,
        "english_friendly": lang == "en" or german_ok,
        "student_type": bool(student_type),
        "senior": senior,
        "full_time_only": full_time_only,
        "hands_on": hands_on,
        "in_germany": in_germany,
    }
    return job

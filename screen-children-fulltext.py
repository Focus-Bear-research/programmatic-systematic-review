"""First-pass FULL-TEXT eligibility screen for the child-review papers we just retrieved.

Advisory single-rater (Claude Sonnet via Bedrock) pass over each retrieved full text,
judging the review's inclusion criteria. Recall-safe: a paper is only marked exclude on a
CLEAR failure; anything genuinely unclear -> review (for human confirmation).

Inclusion (must pass ALL):
  1. Population — children/adolescents (<18) with ADHD and/or autism (parent-mediated counts).
  2. Intervention — digital/technology-based.
  3. Target outcome — >=1 of attention / executive_function / emotional_regulation.
  4. Design — controlled (RCT or non-randomised controlled).
  5. Sample size — >=20 who received the intervention (unstated N is kept, not excluded).

Usage: poetry run python screen-children-fulltext.py [max_workers]
Outputs children/fulltext_screen_firstpass.csv and prints a summary.
"""
import os
import re
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps import llm
from steps.config import load_config, set_active
from steps.io import normalize_doi

MASTER = "search-results-from-database/children/fulltext_review_master.csv"
CONFIRMED = "search-results-from-database/children/manual_matches_confirmed.csv"
CHAPTERS = "search-results-from-database/children/book_chapter_extractions.csv"
SNOW, DB = "full_text_snowball", "full_text"
OUT = "search-results-from-database/children/fulltext_screen_firstpass.csv"

EXCERPT_LIMIT = 12000
KEY_TERMS = re.compile(r"particip|random|control group|control condition|sample|recruit|"
                       r"\bn\s*=|attention|executive|working memory|inhibit|emotion|regulat|"
                       r"diagnos|years old|aged|adolesc", re.I)

SYS = """You screen the FULL TEXT of a study for a systematic review of DIGITAL interventions \
for CHILDREN/ADOLESCENTS (under 18) with ADHD and/or autism. Judge each criterion from the text. \
Be RECALL-SAFE: if a criterion is genuinely unclear, use "unclear" — do not guess "fail".

1. population: "pass" if participants are children/adolescents (majority <18, or a clearly \
reported <18 subgroup) with ADHD and/or autism (diagnosed or strongly indicated). Parent-mediated \
counts (parent/caregiver delivers to the under-18 child). "fail" if adults-only or a population \
without ADHD/autism. "unclear" otherwise.
2. intervention: "pass" if a digital/technology-based intervention (mobile/web app, software, video \
game, VR/AR, neuro/biofeedback, computerised cognitive training, robot, wearable, e-learning, video \
modelling, AAC device, telehealth, or digitally-DELIVERED CBT/mindfulness/parent-training). "fail" if \
non-digital (face-to-face only, medication, physical-only). "unclear" otherwise.
3. target_outcome: array — which of ["attention","executive_function","emotional_regulation"] the study \
MEASURES as an outcome. Executive function includes working memory, inhibition, cognitive flexibility, \
planning. Return [] if it measures none of these (e.g. only social skills, communication, academic, \
motor, adaptive/daily-living).
4. design: one of ["rct","non_randomized_controlled","uncontrolled_prepost","single_case",\
"qualitative","review_or_nonempirical","other"]. Controlled = has a comparison/control group.
5. n_received: integer = participants who actually RECEIVED the intervention (analysed intervention-arm \
sample); null if truly unstated.

Return ONLY JSON: {"reasoning":"<=2 sentences","population":"pass|fail|unclear",\
"intervention":"pass|fail|unclear","target_outcome":[...],"design":"<one>","n_received":<int|null>,\
"evidence":"<short quote: age/diagnosis + outcome>"}"""

CONTROLLED = {"rct", "non_randomized_controlled"}
NONCONTROLLED = {"uncontrolled_prepost", "single_case", "qualitative", "review_or_nonempirical"}


def fkey(doi):
    d = normalize_doi(doi) or ""
    return d.replace("/", "_").replace(":", "_")


def clean_pmid(p):
    m = re.match(r"^(\d+)", str(p).strip())
    return m.group(1) if m else ""


def title_slug(t):
    return re.sub(r"[^a-z0-9]+", "_", str(t).strip().lower()).strip("_")[:80]


def excerpt(text):
    head = text[:5000]
    wins, used = [], 0
    for mo in KEY_TERMS.finditer(text[5000:]):
        s = 5000 + mo.start() - 300
        wins.append(text[max(0, s):s + 600])
        used += 600
        if used > EXCERPT_LIMIT - 5000:
            break
    return (head + "\n...\n" + "\n...\n".join(wins))[:EXCERPT_LIMIT]


def verdict(r):
    """Recall-safe overall status from the per-criterion labels."""
    reasons = []
    if r.get("population") == "fail":
        reasons.append("population")
    if r.get("intervention") == "fail":
        reasons.append("not_digital")
    if not r.get("target_outcome"):
        reasons.append("off_target_outcome")
    if r.get("design") in NONCONTROLLED:
        reasons.append("not_controlled")
    n = r.get("n_received")
    if isinstance(n, int) and n < 20:
        reasons.append("n_lt_20")
    if reasons:
        return "exclude", ";".join(reasons)
    # all hard criteria clear-or-unclear; distinguish clean include vs needs-review
    unclear = [k for k in ("population", "intervention") if r.get(k) == "unclear"]
    if r.get("design") not in CONTROLLED:
        unclear.append("design")
    if unclear:
        return "review", "unclear:" + ",".join(unclear)
    return "include", ""


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cfg = load_config("children")
    set_active(cfg)
    rater = cfg.rater_b  # stronger model for the first pass
    print(f"rater: {rater.label} ({rater.model_id}) profile={rater.aws_profile}")

    m = pd.read_csv(MASTER, keep_default_na=False)
    pmid_by_doi = {normalize_doi(d): clean_pmid(p) for d, p in zip(m["DOI"], m["PMID"]) if normalize_doi(d)}
    pmid_by_title = {str(t).strip().lower(): clean_pmid(p) for t, p in zip(m["Title"], m["PMID"])}
    title_by_doi = {normalize_doi(d): t for d, t in zip(m["DOI"], m["Title"]) if normalize_doi(d)}

    # assemble the papers we just retrieved: confirmed single-paper matches + extracted chapters
    targets = {}  # doi -> title
    conf = pd.read_csv(CONFIRMED, keep_default_na=False)
    for _, r in conf.iterrows():
        targets[normalize_doi(r["match_doi"]) or r["match_title"]] = r["match_title"]
    if os.path.exists(CHAPTERS):
        ch = pd.read_csv(CHAPTERS, keep_default_na=False)
        for _, r in ch[ch["status"] == "EXTRACTED"].iterrows():
            targets[normalize_doi(r["doi"]) or r["chapter"]] = r["chapter"]

    def resolve(doi, title):
        key = fkey(doi)
        if key and os.path.exists(f"{SNOW}/{key}.txt"):
            return f"{SNOW}/{key}.txt"
        pmid = pmid_by_doi.get(normalize_doi(doi)) or pmid_by_title.get(str(title).strip().lower(), "")
        if pmid and os.path.exists(f"{DB}/{pmid}.txt"):
            return f"{DB}/{pmid}.txt"
        slug = title_slug(title)
        if os.path.exists(f"{SNOW}/{slug}.txt"):
            return f"{SNOW}/{slug}.txt"
        return None

    jobs = []
    for doi, title in targets.items():
        path = resolve(doi, title)
        jobs.append((doi, title, path))
    missing = [t for d, t, p in jobs if p is None]
    jobs = [(d, t, p) for d, t, p in jobs if p]
    print(f"papers to screen: {len(jobs)}  (text not found: {len(missing)})")

    llm.warm(rater)

    def screen(job):
        doi, title, path = job
        text = open(path, encoding="utf-8").read()
        try:
            raw = llm.invoke_json(rater, system_prompt=SYS,
                                  user_prompt=f"Title: {title}\n\nTEXT:\n{excerpt(text)}",
                                  temperature=0, max_tokens=600)
        except Exception as e:
            return {"doi": doi, "title": title, "status": "error", "reason": str(e)[:80]}
        to = raw.get("target_outcome") or []
        to = [to] if isinstance(to, str) else to
        rec = {"population": raw.get("population"), "intervention": raw.get("intervention"),
               "target_outcome": [str(x).lower() for x in to], "design": raw.get("design"),
               "n_received": raw.get("n_received")}
        status, reason = verdict(rec)
        return {"doi": doi, "title": title[:70], "status": status, "reason": reason,
                "population": rec["population"], "intervention": rec["intervention"],
                "target_outcome": "|".join(rec["target_outcome"]), "design": rec["design"],
                "n_received": rec["n_received"], "evidence": str(raw.get("evidence", ""))[:200],
                "reasoning": str(raw.get("reasoning", ""))[:250]}

    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(screen, j) for j in jobs]
        for f in as_completed(futs):
            rows.append(f.result())
            done += 1
            if done % 25 == 0:
                print(f"  ...{done}/{len(jobs)}")

    df = pd.DataFrame(rows).sort_values(["status", "reason"])
    df.to_csv(OUT, index=False)
    print(f"\n=== first-pass full-text screen: {len(df)} papers ===")
    print(df["status"].value_counts().to_string())
    print("\nexclusion reasons:")
    print(df[df["status"] == "exclude"]["reason"].value_counts().head(12).to_string())
    inc = df[df["status"] == "include"]
    print(f"\n--- INCLUDE ({len(inc)}) ---")
    for _, r in inc.iterrows():
        print(f"  {r['design']:26} N={r['n_received']}  [{r['target_outcome']}]  {r['title']}")
    rev = df[df["status"] == "review"]
    print(f"\n--- REVIEW ({len(rev)}) — unclear, need a human look ---")
    for _, r in rev.head(20).iterrows():
        print(f"  {r['reason']:22} {r['title']}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()

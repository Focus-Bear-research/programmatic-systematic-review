"""FULL-TEXT re-screen of the ADULT AuDHD review under the CORRECTED narrative-inclusion rule.

Parallel to screen-children-fulltext.py (age gate flipped to ADULTS, >=18), applying the rule
the user set 2026-08-23: a study is INCLUDED for the NARRATIVE review if it ENROLLED at least one
ADULT participant with CO-OCCURRING ADHD AND autism (same person, both diagnoses) — the
co-occurring adult(s) do NOT need a separate subgroup analysis, an AuDHD-subgroup N>=20, or to be
in the intervention arm. Subgroup analysis + N>=20 govern META-ANALYSIS eligibility only.

Re-screens the adult full-text corpus that reached full-text assessment: the 78-row adult
fulltext_review_master.csv + the 28 resolved DSCT-snowball referrals. Reuses excerpt()/verdict()
and the recall-safe machinery from screen-children-fulltext.py (single source of truth).

Usage: poetry run python screen-adults-fulltext.py [max_workers]
"""
import os
import sys
import importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps import llm
from steps.config import load_config, set_active
from steps.io import normalize_doi

# Reuse the children screener's shared helpers (excerpt, verdict, fkey, title_slug, regexes)
# rather than duplicating them — keeps the two reviews' gate logic identical.
_spec = importlib.util.spec_from_file_location("screen_children_fulltext",
                                               "screen-children-fulltext.py")
_ch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ch)
excerpt, verdict, fkey, title_slug = _ch.excerpt, _ch.verdict, _ch.fkey, _ch.title_slug

MASTER = "search-results-from-database/adults/fulltext_review_master.csv"
DSCT = "citation-scraping/dsct_resolved.csv"
# ADULT_SCOPING=1 also screens the broader adult digital-intervention scoping set
# (nd_digital_adults_intent.csv, 323 autism/ADHD adult digital studies) for embedded
# co-occurring AuDHD adults under the relaxed population rule — the full abstract-level redo.
SCOPING = "search-results-from-database/adults/nd_digital_adults_intent.csv"
SNOW, DB = "full_text_snowball", "full_text"
OUT = "search-results-from-database/adults/adults_fulltext_screen_narrative.csv"

SYS = """You screen the FULL TEXT of a study for a systematic review of DIGITAL interventions \
for ADULTS (18+) with CO-OCCURRING ADHD AND autism (AuDHD). Judge each criterion from the text. \
Be RECALL-SAFE: if a criterion is genuinely unclear, use "unclear" — do not guess "fail".

1. population: This is a NARRATIVE review. It INCLUDES any study that ENROLLED at least one ADULT \
participant (age 18+) with CO-OCCURRING ADHD AND autism (the SAME person has BOTH an ADHD diagnosis \
AND an autism diagnosis). The co-occurring adult(s) do NOT need to be analysed as a separate \
subgroup, do NOT need to number >=20, and do NOT need to be in the intervention arm — it is ENOUGH \
that they were ENROLLED. Adults must be the DIRECT study subjects (a study of children where only \
the PARENTS are adults does NOT count). Be RECALL-SAFE: do not exclude just because the headline says \
only "ADHD" or only "autism"; read the sample/eligibility/demographics for co-occurrence. Judge:
   - "pass" if the sample includes adults (18+, or a clearly reported adult subgroup) and at least one \
enrolled adult carries BOTH ADHD AND autism — e.g. an explicit count ("n=16 with both ASD and ADHD"), \
a demographics/comorbidity table showing co-occurrence, OR an autism sample reporting a comorbid-ADHD \
percentage/count (or an ADHD sample reporting comorbid autism). Even a small embedded co-occurring \
subset PASSES, regardless of arm or whether analysed separately.
   - "unclear" (do NOT fail) if co-occurring adult AuDHD PLAUSIBLY exists but cannot be confirmed: \
diagnoses reported only as SEPARATE counts with no overlap stated, a mixed neurodevelopmental sample \
not broken out, or a sample whose age is unclear/spans childhood with no adult breakdown for the \
co-occurring participants. When in doubt between pass and fail, choose "unclear".
   - "fail" ONLY when co-occurring adult AuDHD is clearly absent/impossible: children-only (no 18+ \
participants as direct subjects); a non-ADHD/non-autism population; or a single-diagnosis sample where \
the OTHER condition is only MEASURED as a symptom score / questionnaire "feature" (NOT diagnosed) or \
appears ONLY as background/prevalence/citation and never in an actual enrolled participant.
2. intervention: "pass" if a digital/technology-based intervention (mobile/web app, software tool, \
video game / serious game, VR/AR, neuro/biofeedback, EEG-neurofeedback, computerised cognitive \
training, robot, wearable, e-learning, or an app-DELIVERED CBT/mindfulness program the adult uses \
directly). "fail" if non-digital (face-to-face only, medication, physical-only), if the technology is \
used ONLY to assess/measure/screen/diagnose, OR if the "digital" element is only the DELIVERY CHANNEL \
for human-delivered coaching/therapy — i.e. TELEHEALTH / telecounselling / telecoaching / \
video-conference clinician sessions are EXCLUDED (out of scope per protocol). Brain-STIMULATION \
hardware (tDCS/TMS) is NOT neurofeedback and is out of scope. "unclear" otherwise.
3. target_outcome: array of the ADULT-level clinical/behavioural/functional outcomes the study \
MEASURES, from ["attention","executive_function","emotional_regulation","emotion_recognition",\
"social_communication","language","anxiety_mood","behaviour","adaptive_daily_living","quality_of_life",\
"self_determination","academic","employment","motor"]. Executive function includes working memory, \
inhibition, cognitive flexibility, planning. This review accepts ANY adult-level clinical/behavioural/\
functional outcome. Return [] ONLY when the SOLE outcomes are (a) tolerance/usability/feasibility/\
sensory-comfort of the technology or VR/AR device itself, or (b) caregiver-only outcomes.
4. design: one of ["rct","non_randomized_controlled","uncontrolled_prepost","single_case",\
"qualitative","review_or_nonempirical","other"]. Controlled = has a comparison/control group.
5. n_received: integer = participants who actually RECEIVED the intervention (analysed intervention-arm \
sample); null if truly unstated.

Return ONLY JSON: {"reasoning":"<=2 sentences","population":"pass|fail|unclear",\
"intervention":"pass|fail|unclear","target_outcome":[...],"design":"<one>","n_received":<int|null>,\
"evidence":"<short quote: age/diagnosis + outcome>"}"""


def resolve_master(r):
    f = str(r.get("full_text_filename", "")).strip()
    for cand in ([f, os.path.join(SNOW, os.path.basename(f)),
                  os.path.join(DB, os.path.basename(f))] if f else []):
        if cand and os.path.exists(cand):
            return cand
    key = fkey(r.get("DOI", ""))
    for cand in [os.path.join(SNOW, f"{key}.txt"), os.path.join(DB, f"{key}.txt")] if key else []:
        if os.path.exists(cand):
            return cand
    return None


def resolve_dsct(r):
    key = fkey(r.get("DOI", ""))
    for cand in [os.path.join(SNOW, f"{key}.txt"), os.path.join(DB, f"{key}.txt")] if key else []:
        if os.path.exists(cand):
            return cand
    slug = title_slug(r.get("Title", ""))
    cand = os.path.join(SNOW, f"{slug}.txt")
    return cand if os.path.exists(cand) else None


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    cfg = load_config("adults")
    set_active(cfg)
    rater = cfg.rater_b
    print(f"rater: {rater.label} ({rater.model_id}) profile={rater.aws_profile}")

    jobs = []  # (doi, title, path, origin)
    m = pd.read_csv(MASTER, keep_default_na=False)
    for _, r in m.iterrows():
        p = resolve_master(r)
        if p:
            jobs.append((r["DOI"] or r["Title"], r["Title"], p, "master"))
    if os.path.exists(DSCT):
        d = pd.read_csv(DSCT, keep_default_na=False)
        for _, r in d.iterrows():
            p = resolve_dsct(r)
            if p:
                jobs.append((r["DOI"] or r["Title"], r["Title"], p, "dsct"))
    if os.getenv("ADULT_SCOPING") not in (None, "0", "", "false", "False"):
        sc = pd.read_csv(SCOPING, keep_default_na=False)
        if "is_duplicate" in sc.columns:
            sc = sc[sc["is_duplicate"] != "Y"]
        for _, r in sc.iterrows():
            p = resolve_dsct(r)  # same DOI/title-slug resolver
            if p:
                jobs.append((r["DOI"] or r["Title"], r["Title"], p, "scoping"))

    # de-dup by resolved path (a DSCT paper may also be in the master)
    seen, uniq = set(), []
    for j in jobs:
        if j[2] in seen:
            continue
        seen.add(j[2])
        uniq.append(j)
    jobs = uniq
    print(f"adult full-text reports to re-screen: {len(jobs)}")

    llm.warm(rater)

    def screen(job):
        doi, title, path, origin = job
        text = open(path, encoding="utf-8").read()
        try:
            raw = llm.invoke_json(rater, system_prompt=SYS,
                                  user_prompt=f"Title: {title}\n\nTEXT:\n{excerpt(text)}",
                                  temperature=0, max_tokens=600)
        except Exception as e:
            return {"doi": doi, "title": title, "origin": origin, "status": "error",
                    "reason": str(e)[:80]}
        to = raw.get("target_outcome") or []
        to = [to] if isinstance(to, str) else to
        rec = {"population": raw.get("population"), "intervention": raw.get("intervention"),
               "target_outcome": [str(x).lower() for x in to], "design": raw.get("design"),
               "n_received": raw.get("n_received")}
        status, reason = verdict(rec)
        return {"doi": doi, "title": title[:70], "origin": origin, "status": status,
                "reason": reason, "population": rec["population"],
                "intervention": rec["intervention"],
                "target_outcome": "|".join(rec["target_outcome"]), "design": rec["design"],
                "n_received": rec["n_received"], "evidence": str(raw.get("evidence", ""))[:200],
                "reasoning": str(raw.get("reasoning", ""))[:250]}

    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(screen, j) for j in jobs]
        for f in as_completed(futs):
            rows.append(f.result())
            done += 1
            if done % 20 == 0:
                print(f"  ...{done}/{len(jobs)}")

    df = pd.DataFrame(rows).sort_values(["status", "reason"])
    df.to_csv(OUT, index=False)
    print(f"\n=== adult full-text re-screen (narrative rule): {len(df)} papers ===")
    print(df["status"].value_counts().to_string())
    print("\nexclusion reasons:")
    print(df[df["status"] == "exclude"]["reason"].value_counts().head(12).to_string())
    for st in ("include", "review"):
        sub = df[df["status"] == st]
        print(f"\n--- {st.upper()} ({len(sub)}) ---")
        for _, r in sub.iterrows():
            print(f"  [{r['origin']}] {r['design']:24} N={r['n_received']} "
                  f"[{r['target_outcome']}] {r['title']}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()

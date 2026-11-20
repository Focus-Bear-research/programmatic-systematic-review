"""Exploratory FULL-TEXT analysis of adult digital-intervention studies (autism and/or ADHD).

For every adult ND digital-intervention study with full text on disk, extract three things
the team wants to characterise the field on (single strong rater — Claude Sonnet — advisory,
over the full text, richer than the abstract-only intent pass in classify-intent.py):

  Q1. Lived-experience involvement — were autistic/ADHD peer researchers or co-design/
      participatory methods involved?
  Q2. Autism support level of participants — DSM-5 Level 1/2/3, mixed, or not disclosed.
  Q3. Intent (re-do of the normalisation vs affirming analysis) — does the intervention
      teach the person to MASK / become more neurotypical (normalisation), genuinely SUPPORT
      them on their own terms (skills_training / accommodation_support), or train COGNITIVE
      ability — plus whether the framing is neuro-affirming or deficit/normalising.

Usage: poetry run python analyze-adults-fulltext.py [workers]   (aws sso login --profile phd first)
"""
import os, sys, re, json
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv(override=True)
import pandas as pd
from steps.config import load_config, set_active
from steps import llm
from steps.io import normalize_doi

SRC = os.getenv("ADULT_SRC", "search-results-from-database/adults/nd_digital_adults_intent.csv")
OUT = os.getenv("ADULT_OUT", "search-results-from-database/adults/adults_fulltext_analysis.csv")
SNOW, DB = "full_text_snowball", "full_text"

HEAD = 9000
LIMIT = 17000
# sections where support level / lived-experience / co-design evidence lives
KEY = re.compile(r"level 1|level 2|level 3|level one|level two|level three|support need|"
                 r"requiring (very substantial|substantial) support|DSM|ADOS|diagnos|severity|"
                 r"co-?design|co-?produc|co-?creat|participatory|lived experience|peer research|"
                 r"autistic researcher|advisory (group|board|panel)|\bPPI\b|patient and public|"
                 r"stakeholder|community.{0,20}involv|nothing about us|end-?user.{0,10}involv|"
                 r"particip|recruit|inclusion crit", re.I)

def excerpt(text):
    head = text[:HEAD]
    wins, used, seen = [], 0, set()
    for mo in KEY.finditer(text[HEAD:]):
        s = HEAD + mo.start() - 250
        w = text[max(0, s):s + 500]
        k = w[:50]
        if k in seen: continue
        seen.add(k); wins.append(w); used += len(w)
        if used > LIMIT - HEAD: break
    tail = ("\n\n[SECTIONS: participants / diagnosis / co-design / lived-experience]\n"
            + "\n...\n".join(wins)) if wins else ""
    return (head + tail)[:LIMIT]

SYS = """You analyse the FULL TEXT of a digital-intervention study for neurodivergent (autistic and/or ADHD) people. Extract the following as strict JSON. Judge ONLY from the text; when the text does not say, use the "unclear"/"not_disclosed" option rather than guessing.

1) population_neurotype: which participants the intervention was evaluated in — one of "autism","adhd","audhd","mixed_nd","other_unclear".

1b) adults_direct_subjects: are ADULTS (18+) the DIRECT study subjects — the people themselves receiving/assessed on the intervention? "yes" if the intervention is delivered to and measured on adults with autism/ADHD. "no" if the direct subjects are children/adolescents, OR the only adults are parents/carers/teachers/clinicians of a child sample (parent-mediated or informants), OR it is a parent-training/provider-training study. "unclear" if ages/subjects genuinely not stated. Judge by the TARGET population, not by any adult merely mentioned.

2) lived_experience — involvement of neurodivergent lived experience in the RESEARCH:
   - peer_researcher: "yes" only if an autistic/ADHD/neurodivergent person is described as part of the research/author team or as a peer/co-researcher; else "no"; "unclear" if hinted but not stated.
   - co_design: "yes" if the intervention or study was co-designed / co-produced / developed with participatory methods involving autistic/ADHD people (or an advisory/community group of them); else "no"; "unclear" if hinted.
   - involvement_type: the STRONGEST level present — one of "peer_led","co_design_participatory","advisory_consultation","none_reported","unclear".
   - le_evidence: short verbatim quote (<=200 chars) or "" .

3) autism_support_level — DSM-5 support level of the AUTISTIC participants:
   one of "level_1","level_2","level_3","mixed_levels","not_disclosed","not_applicable_adhd_only".
   Use the explicit DSM-5 level if stated; infer "level_1" only if clearly high-functioning/no-ID/independent wording is explicit; "not_disclosed" if autism present but level/severity not reported; "not_applicable_adhd_only" if no autistic participants.
   - support_level_evidence: short quote or "".

4) intent — the intervention's PRIMARY aim (re the normalisation vs affirming question):
   - "normalisation": internal change toward a NEUROTYPICAL standard — teach masking/camouflaging, social-skills-to-appear-typical, emotion/face-recognition training, reduce/suppress ND traits or "inappropriate" behaviours, symptom reduction as the goal.
   - "skills_training": internal change that is NEURODIVERGENT-AFFIRMING — self-advocacy, self-understanding/psychoeducation about one's own autism/ADHD, self-regulation/planning strategies on the person's OWN terms, strengths-based.
   - "accommodation_support": EXTERNAL supports/tools/reminders/environmental adaptation/user-controlled scaffolds rather than changing the person.
   - "cognitive_training": trains a cognitive ability (attention, working memory, executive function, inhibition) via drills/games.
   - "unclear".
   Pick the DOMINANT aim (no "mixed").
   - neuroaffirming_framing: "affirming" (frames neurodivergence as difference to support; goals set with/by the person), "deficit_normalising" (frames traits as deficits to fix / aims to reduce visible difference / neurotypical standard of success), "mixed", or "unclear".
   - intent_reasoning: <=1 sentence.

Return ONLY: {"population_neurotype":"...","adults_direct_subjects":"...","peer_researcher":"...","co_design":"...","involvement_type":"...","le_evidence":"...","autism_support_level":"...","support_level_evidence":"...","intent":"...","neuroaffirming_framing":"...","intent_reasoning":"..."}"""

def fkey(d):
    d = normalize_doi(d) or ""
    return d.replace("/", "_").replace(":", "_")

def resolve(doi):
    k = fkey(doi)
    for p in ([f"{SNOW}/{k}.txt", f"{DB}/{k}.txt"] if k else []):
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p
    return None

def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    cfg = load_config("adults"); set_active(cfg)
    rater = cfg.rater_b
    print(f"rater: {rater.label}", flush=True)
    df = pd.read_csv(SRC, dtype=str).fillna("")
    if "is_duplicate" in df.columns:
        df = df[df.is_duplicate != "Y"]
    df = df.reset_index(drop=True)
    jobs = [(i, df.at[i, "DOI"], df.at[i, "Title"], resolve(df.at[i, "DOI"])) for i in df.index]
    jobs = [(i, d, t, p) for (i, d, t, p) in jobs if p]
    print(f"adult digital studies with full text to analyse: {len(jobs)}", flush=True)
    llm.warm(rater)

    FIELDS = ["population_neurotype","adults_direct_subjects","peer_researcher","co_design","involvement_type",
              "le_evidence","autism_support_level","support_level_evidence","intent","neuroaffirming_framing","intent_reasoning"]

    def do(job):
        i, doi, title, path = job
        text = open(path, encoding="utf-8").read()
        try:
            raw = llm.invoke_json(rater, system_prompt=SYS,
                                  user_prompt=f"Title: {title}\n\nFULL TEXT (excerpted):\n{excerpt(text)}",
                                  temperature=0, max_tokens=500)
        except Exception as e:
            return i, {"error": str(e)[:80]}
        return i, {k: str(raw.get(k, "")) for k in FIELDS}

    rows = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(do, j) for j in jobs]):
            i, rec = fut.result()
            rows[i] = rec
            done += 1
            if done % 25 == 0:
                print(f"  ...{done}/{len(jobs)}", flush=True)

    out = df.loc[list(rows.keys()), ["DOI", "Title", "Year", "Journal"]].copy()
    for k in FIELDS + ["error"]:
        out[k] = [rows[i].get(k, "") for i in out.index]
    out.to_csv(OUT, index=False)

    def report(sub, label):
        n = len(sub)
        print(f"\n===== {label} (n={n}) =====")
        print("Q1 involvement_type:", sub["involvement_type"].value_counts().to_dict())
        print(f"   peer_researcher=yes: {(sub.peer_researcher=='yes').sum()} | co_design=yes: {(sub.co_design=='yes').sum()}")
        aut = sub[sub.autism_support_level != 'not_applicable_adhd_only']
        print(f"Q2 autism_support_level (of {len(aut)} with autistic participants):",
              aut["autism_support_level"].value_counts().to_dict())
        print("Q3 intent:", sub["intent"].value_counts().to_dict())
        print("   neuroaffirming_framing:", sub["neuroaffirming_framing"].value_counts().to_dict())

    print(f"\n=== analysed {len(out)} adult digital-intervention full texts ===")
    print("direct-adult-subjects breakdown:", out["adults_direct_subjects"].value_counts().to_dict())
    report(out, "ALL analysed (unfiltered — as before)")
    genuine = out[out.adults_direct_subjects == 'yes']
    report(genuine, "GENUINE adult-direct-subject studies only (corrected)")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()

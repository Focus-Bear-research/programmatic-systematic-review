"""Build a Bedrock batch to classify the child-review DETAIL gap: papers that pass the
child screen gate but were NEVER detail-classified (both raters' intervention_type empty)
— mostly pre-existing snowball/original-search child-only papers the ADULT gate had dropped.
Rows where the raters merely DISAGREED already carry usable labels, so they're excluded.

recordId encodes the all_papers.csv row index so merge-children-expanded.py (run with the
'child_gap' prefix) writes labels back by index. Usage: poetry run python build-children-gap-batch.py
"""
import os, re, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import pandas as pd
from steps.config import load_config
from steps.schema import CLASSIFICATION_PROMPT
from steps.io import normalize_doi

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
ALL = "search-results-from-database/all_papers.csv"
ENRICHED = "search-results-from-database/children/enriched.csv"
MAXTOK = 1024
cfg = load_config("adults")
sa, sb = cfg.rater("a").prompt_suffix, cfg.rater("b").prompt_suffix


def nd(d):
    return normalize_doi(d) or ""


def nt(t):
    return re.sub(r"[^a-z0-9 ]", " ", str(t).lower()).strip()


def main():
    allp = pd.read_csv(ALL, dtype=str, keep_default_na=False)
    idx_by_doi = {nd(d): i for i, d in zip(allp.index, allp["DOI"]) if nd(d)}
    idx_by_title = {}
    for i, t in zip(allp.index, allp["Title"]):
        idx_by_title.setdefault(nt(t), i)

    en = pd.read_csv(ENRICHED, dtype=str, keep_default_na=False)
    tgt = en[(en["Screen_Pass"].str.upper() == "Y")
             & (en["RaterA_intervention_type"].str.strip() == "")
             & (en["RaterB_intervention_type"].str.strip() == "")
             & (en["Abstract"].str.len() >= 20)]
    print(f"truly-unclassified child-gate survivors with abstract: {len(tgt)}")

    seen, nova, sonnet = set(), [], []
    for _, r in tgt.iterrows():
        i = idx_by_doi.get(nd(r["DOI"]))
        if i is None:
            i = idx_by_title.get(nt(r["Title"]))
        if i is None or i in seen:
            continue
        seen.add(i)
        up = f"Title: {allp.at[i, 'Title']}\n\nAbstract: {allp.at[i, 'Abstract']}"
        rid = f"rec{int(i):07d}"
        sys_a = CLASSIFICATION_PROMPT + (("\n\n" + sa) if sa else "")
        sys_b = CLASSIFICATION_PROMPT + (("\n\n" + sb) if sb else "")
        sonnet.append({"recordId": rid, "modelInput": {
            "anthropic_version": "bedrock-2023-05-31", "max_tokens": MAXTOK,
            "system": sys_b, "messages": [{"role": "user", "content": up}]}})
        nova.append({"recordId": rid, "modelInput": {
            "system": [{"text": sys_a}], "messages": [{"role": "user", "content": [{"text": up}]}],
            "inferenceConfig": {"maxTokens": MAXTOK, "temperature": 0}}})

    os.makedirs("/tmp/batch_in", exist_ok=True)
    s3 = boto3.Session(region_name="us-east-1").client("s3")
    for name, recs in [("child_gap_sonnet", sonnet), ("child_gap_nova", nova)]:
        p = f"/tmp/batch_in/{name}.jsonl"
        with open(p, "w") as f:
            for rec in recs:
                f.write(json.dumps(rec) + "\n")
        s3.upload_file(p, BUCKET, f"input/{name}.jsonl")
        print(f"  uploaded {len(recs)} -> s3://{BUCKET}/input/{name}.jsonl")


if __name__ == "__main__":
    main()

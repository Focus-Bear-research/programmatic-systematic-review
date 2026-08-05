"""Build the Bedrock batch-inference input (Nova + Sonnet) to classify ONLY the newly-added
expanded-children-search rows (index range in expanded/new_index_range.json), using the same
CLASSIFICATION_PROMPT + rater suffixes as bigscreen so labels are consistent with the corpus.
recordId encodes the all_papers.csv row index (so bigscreen-merge writes back by index).
"""
import os, json, boto3
os.environ.setdefault("AWS_PROFILE", "phd")
import pandas as pd
from steps.config import load_config
from steps.schema import CLASSIFICATION_PROMPT

ACCT = "369598751361"; BUCKET = f"audhd-bedrock-batch-{ACCT}"
ALL = "search-results-from-database/all_papers.csv"
RANGE = "search-results-from-database/children/expanded/new_index_range.json"
MAXTOK = 1024
cfg = load_config("adults")  # same suffixes bigscreen used
sa, sb = cfg.rater("a").prompt_suffix, cfg.rater("b").prompt_suffix

rng = json.load(open(RANGE))
allp = pd.read_csv(ALL, dtype=str, keep_default_na=False)
sub = allp.iloc[rng["lo"]:rng["hi"] + 1]
tgt = sub[sub["Abstract"].str.len() >= 20]
print(f"new rows {rng['lo']}..{rng['hi']}  | screenable (abstract>=20): {len(tgt)}")

nova, sonnet = [], []
for idx, r in tgt.iterrows():
    rid = f"rec{int(idx):07d}"
    up = f"Title: {r['Title']}\n\nAbstract: {r['Abstract']}"
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
for name, recs in [("child_exp_sonnet", sonnet), ("child_exp_nova", nova)]:
    p = f"/tmp/batch_in/{name}.jsonl"
    with open(p, "w") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")
    s3.upload_file(p, BUCKET, f"input/{name}.jsonl")
    print(f"  uploaded {len(recs)} -> s3://{BUCKET}/input/{name}.jsonl")
print("done")

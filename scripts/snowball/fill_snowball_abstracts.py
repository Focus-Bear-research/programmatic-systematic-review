"""Fetch abstracts (by DOI) for the no-abstract snowball papers, isolated in the
snowball/ review subdir so the database review's abstracts_filled.csv is untouched.
"""

import dataclasses
import os

import pandas as pd

from steps import fill_abstracts
from steps.config import load_config, set_active
from steps.io import is_missing_abstract
from steps.paths import DEDUPED_WITH_SNOWBALL_CSV

cfg = load_config("adults")
cfg = dataclasses.replace(cfg, review_subdir="snowball")
set_active(cfg)
os.makedirs(cfg.review_dir, exist_ok=True)

df = pd.read_csv(DEDUPED_WITH_SNOWBALL_CSV, dtype=str).fillna("")
new = df[df["origin"] == "snowball"].copy()
missing = new[new["Abstract"].apply(is_missing_abstract)].copy()
print(f"{len(missing)} no-abstract snowball papers -> fetching by DOI", flush=True)
fill_abstracts.run(missing)

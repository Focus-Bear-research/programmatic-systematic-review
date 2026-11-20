"""Phase-2 detailed classification on snowball papers that passed the screen.
Isolated in the snowball/ subdir so the database review's enriched.csv is untouched.
Resumable (checkpoints to snowball/enriched.csv every 25 rows).
"""

import dataclasses
import os

import pandas as pd

from steps import classify
from steps.config import load_config, set_active
from steps.paths import SNOWBALL_SCREENED_CSV

cfg = dataclasses.replace(load_config("adults"), review_subdir="snowball")
set_active(cfg)
os.makedirs(cfg.review_dir, exist_ok=True)
df = pd.read_csv(SNOWBALL_SCREENED_CSV, dtype=str).fillna("")
print(f"Phase 2: {(df['Screen_Pass']=='Y').sum()} survivors to classify", flush=True)
classify.run(df)

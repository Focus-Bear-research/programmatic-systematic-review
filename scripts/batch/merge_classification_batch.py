"""Merge a finished classification batch back into the CSV it re-rated.

Usage::

    poetry run python scripts/batch/merge_classification_batch.py <batch>

``<batch>`` is reclassify, bigscreen, children_expanded or children_gap (see
``steps/batches.py``). Downloads both raters' output from S3, coerces each
reply to the classification enums, applies the deterministic rule overrides,
and writes RaterA_ / RaterB_ / Consensus_ columns for every row both raters
returned. Final_ / Human_ / Adjudicated columns are left untouched. The target
CSV is backed up first. Stop the adjudication UI before running: both write
the file.
"""

from __future__ import annotations

import shutil
import sys

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, RESCREEN
from steps.config import load_config
from steps.schema import coerce_classification

CLASSIFICATION_BATCHES = [name for name in BATCHES if name != RESCREEN]


def main(batch_name: str) -> None:
    batch = BATCHES[batch_name]
    results_a, results_b = bedrock_batch.load_rater_results(batch.job_prefix, coerce_classification)

    papers = pd.read_csv(batch.target_csv, dtype=str).fillna("")
    shutil.copy(batch.target_csv, batch.backup_csv)
    updated = bedrock_batch.merge_classifications(papers, results_a, results_b, load_config("adults"))
    papers.to_csv(batch.target_csv, index=False)
    print(f"merged {updated} rows -> {batch.target_csv} (backup: {batch.backup_csv})")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CLASSIFICATION_BATCHES:
        sys.exit(f"usage: merge_classification_batch.py <{'|'.join(CLASSIFICATION_BATCHES)}>")
    main(sys.argv[1])

"""Build the batch input that re-rates the adult screen survivors with the updated taxonomy.

Usage::

    poetry run python scripts/batch/build_reclassify_batch.py

Targets every row of the combined adult dataset that passed the Phase-1 screen
and has an abstract. Follow with ``submit_batch.py reclassify`` and
``merge_classification_batch.py reclassify``.
"""

from __future__ import annotations

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, RECLASSIFY
from steps.constants import COL_ABSTRACT, SCREEN_PASS_COL, YES
from steps.paths import ADULTS_COMBINED_ADJUDICATED_CSV
from steps.schema import CLASSIFICATION_PROMPT


def main() -> None:
    papers = pd.read_csv(ADULTS_COMBINED_ADJUDICATED_CSV, dtype=str).fillna("")
    passed_screen = papers[SCREEN_PASS_COL].astype(str).str.upper() == YES
    survivors = papers[passed_screen & bedrock_batch.has_usable_abstract(papers[COL_ABSTRACT])]
    print(f"survivors to re-rate: {len(survivors)}")

    records_a, records_b = bedrock_batch.build_records(
        survivors, CLASSIFICATION_PROMPT, CLASSIFICATION_PROMPT, bedrock_batch.CLASSIFICATION_MAX_TOKENS
    )
    bedrock_batch.upload_inputs(BATCHES[RECLASSIFY].job_prefix, records_a, records_b)


if __name__ == "__main__":
    main()

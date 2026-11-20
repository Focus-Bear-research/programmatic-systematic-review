"""Build the batch input that re-screens adult survivors under the redefined has_adults criterion.

Usage::

    poetry run python scripts/batch/build_rescreen_batch.py

Targets Phase-1 survivors whose current has_adults label is "yes" (the human
value where a row was adjudicated, otherwise the two-rater consensus). Follow
with ``submit_batch.py rescreen`` and ``merge_rescreen_batch.py``.
"""

from __future__ import annotations

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, RESCREEN
from steps.constants import COL_ABSTRACT, SCREEN_PASS_COL, YES
from steps.paths import ADULTS_COMBINED_ADJUDICATED_CSV
from steps.schema import SCREEN_PROMPT

AGE_FIELD = "has_adults"
AGE_PRESENT = "yes"
ADJUDICATED_COL = "Adjudicated"
ADJUDICATED_BY_HUMAN = "human"


def _normalised(value: object) -> str:
    return str(value).strip().lower()


def current_label(paper: pd.Series, field: str) -> str:
    """Human-adjudicated value where present, otherwise the two-rater consensus."""
    final_value = _normalised(paper.get(f"Final_{field}"))
    if _normalised(paper.get(ADJUDICATED_COL)) == ADJUDICATED_BY_HUMAN and final_value:
        return final_value
    return _normalised(paper.get(f"Consensus_{field}"))


def main() -> None:
    papers = pd.read_csv(ADULTS_COMBINED_ADJUDICATED_CSV, dtype=str).fillna("")
    passed_screen = papers[SCREEN_PASS_COL].astype(str).str.upper() == YES
    survivors = papers[passed_screen & bedrock_batch.has_usable_abstract(papers[COL_ABSTRACT])]
    is_adult_study = [current_label(paper, AGE_FIELD) == AGE_PRESENT for _, paper in survivors.iterrows()]
    targets = survivors[is_adult_study]
    print(f"re-screen targets (has_adults=yes survivors): {len(targets)}")

    records_a, records_b = bedrock_batch.build_records(
        targets, SCREEN_PROMPT, SCREEN_PROMPT, bedrock_batch.SCREEN_MAX_TOKENS
    )
    bedrock_batch.upload_inputs(BATCHES[RESCREEN].job_prefix, records_a, records_b)


if __name__ == "__main__":
    main()

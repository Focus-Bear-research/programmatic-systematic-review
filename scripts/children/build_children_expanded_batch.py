"""Build the batch input that classifies the rows added by the expanded children's search.

Usage::

    poetry run python scripts/children/build_children_expanded_batch.py

Targets only the new rows of ``all_papers.csv`` (the index range recorded by
``build_children_expanded_corpus.py``), with the same prompt and rater suffixes
as the bigscreen batch so labels are consistent across the corpus. Follow with
``submit_batch.py children_expanded`` and
``merge_classification_batch.py children_expanded``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, CHILDREN_EXPANDED
from steps.config import load_config
from steps.constants import COL_ABSTRACT
from steps.paths import ALL_PAPERS_CSV, DATA_DIR
from steps.schema import CLASSIFICATION_PROMPT

NEW_INDEX_RANGE_JSON = f"{DATA_DIR}/children/expanded/new_index_range.json"


def main() -> None:
    index_range = json.loads(Path(NEW_INDEX_RANGE_JSON).read_text())
    all_papers = pd.read_csv(ALL_PAPERS_CSV, dtype=str, keep_default_na=False)
    new_rows = all_papers.iloc[index_range["lo"] : index_range["hi"] + 1]
    targets = new_rows[bedrock_batch.has_usable_abstract(new_rows[COL_ABSTRACT])]
    print(f"new rows {index_range['lo']}..{index_range['hi']}  | screenable: {len(targets)}")

    # The adult config's rater suffixes, because that is what the bigscreen batch used.
    cfg = load_config("adults")
    records_a, records_b = bedrock_batch.build_records(
        targets,
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_a.prompt_suffix),
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_b.prompt_suffix),
        bedrock_batch.CLASSIFICATION_MAX_TOKENS,
    )
    bedrock_batch.upload_inputs(BATCHES[CHILDREN_EXPANDED].job_prefix, records_a, records_b)


if __name__ == "__main__":
    main()

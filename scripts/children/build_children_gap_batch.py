"""Build the batch input for child-screen survivors that never got a detail classification.

Usage::

    poetry run python scripts/children/build_children_gap_batch.py

Targets papers that pass the children's screen gate but have no
intervention_type from either rater. These are mostly snowball and
original-search child-only papers that the adult gate had dropped before the
detail phase. Rows where the raters merely disagreed already carry usable
labels and are excluded. Records are keyed by ``all_papers.csv`` row index, so
follow with ``submit_batch.py children_gap`` and
``merge_classification_batch.py children_gap``.
"""

from __future__ import annotations

import re

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, CHILDREN_GAP
from steps.config import load_config
from steps.constants import COL_ABSTRACT, COL_DOI, COL_TITLE, SCREEN_PASS_COL, YES
from steps.io import normalize_doi
from steps.paths import ALL_PAPERS_CSV, DATA_DIR
from steps.schema import CLASSIFICATION_PROMPT

CHILDREN_ENRICHED_CSV = f"{DATA_DIR}/children/enriched.csv"
DETAIL_FIELD = "intervention_type"


def doi_key(doi: object) -> str:
    return normalize_doi(doi) or ""


def title_key(title: object) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(title).lower()).strip()


def unclassified_survivors(enriched: pd.DataFrame) -> pd.DataFrame:
    return enriched[
        (enriched[SCREEN_PASS_COL].str.upper() == YES)
        & (enriched[f"RaterA_{DETAIL_FIELD}"].str.strip() == "")
        & (enriched[f"RaterB_{DETAIL_FIELD}"].str.strip() == "")
        & bedrock_batch.has_usable_abstract(enriched[COL_ABSTRACT])
    ]


def corpus_row_indices(papers: pd.DataFrame, all_papers: pd.DataFrame) -> list[int]:
    """Match each paper to its all_papers.csv row by DOI, then title; unmatched papers are skipped."""
    index_by_doi = {doi_key(doi): i for i, doi in zip(all_papers.index, all_papers[COL_DOI]) if doi_key(doi)}
    index_by_title: dict[str, int] = {}
    for i, title in zip(all_papers.index, all_papers[COL_TITLE]):
        index_by_title.setdefault(title_key(title), i)

    indices: list[int] = []
    for _, paper in papers.iterrows():
        index = index_by_doi.get(doi_key(paper[COL_DOI]))
        if index is None:
            index = index_by_title.get(title_key(paper[COL_TITLE]))
        if index is None or index in indices:
            continue
        indices.append(index)
    return indices


def main() -> None:
    all_papers = pd.read_csv(ALL_PAPERS_CSV, dtype=str, keep_default_na=False)
    enriched = pd.read_csv(CHILDREN_ENRICHED_CSV, dtype=str, keep_default_na=False)
    survivors = unclassified_survivors(enriched)
    print(f"truly-unclassified child-gate survivors with abstract: {len(survivors)}")

    targets = all_papers.loc[corpus_row_indices(survivors, all_papers)]
    cfg = load_config("adults")
    records_a, records_b = bedrock_batch.build_records(
        targets,
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_a.prompt_suffix),
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_b.prompt_suffix),
        bedrock_batch.CLASSIFICATION_MAX_TOKENS,
    )
    bedrock_batch.upload_inputs(BATCHES[CHILDREN_GAP].job_prefix, records_a, records_b)


if __name__ == "__main__":
    main()

"""Build the unified corpus and the batch input that re-classifies every paper in it.

Usage::

    poetry run python scripts/batch/build_bigscreen_batch.py

Step 1 writes ``all_papers.csv``: the combined adult dataset (database search +
citation snowball) plus the DSCT-review snowball records not already in it.
Step 2 builds a batch record for every row with an abstract, using the tuned
classification prompt and each rater's prompt suffix. Follow with
``submit_batch.py bigscreen`` and ``merge_classification_batch.py bigscreen``.
"""

from __future__ import annotations

import re

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, BIGSCREEN
from steps.config import load_config
from steps.constants import COL_ABSTRACT, COL_DOI, COL_TITLE
from steps.io import normalize_doi
from steps.paths import ADULTS_COMBINED_ADJUDICATED_CSV, ALL_PAPERS_CSV, CITATION_DIR
from steps.schema import CLASSIFICATION_PROMPT

DSCT_RECALLSAFE_CSV = f"{CITATION_DIR}/dsct_recallsafe.csv"
ORIGIN_COL = "origin"
ORIGIN_DATABASE_SEARCH = "database_search"
ORIGIN_DSCT_SNOWBALL = "dsct_snowball"
BIBLIOGRAPHIC_COLUMNS = ["Title", "Abstract", "Authors", "Year", "DOI", "URL", "PMID", "Journal"]


def doi_key(doi: object) -> str:
    return normalize_doi(doi) or ""


def title_key(title: object) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(title).lower()).strip()


def new_dsct_papers(corpus: pd.DataFrame) -> pd.DataFrame:
    """DSCT snowball records whose DOI and title are both absent from the corpus."""
    known_dois = {doi_key(doi) for doi in corpus[COL_DOI] if doi_key(doi)}
    known_titles = {title_key(title) for title in corpus[COL_TITLE] if str(title).strip()}
    dsct = pd.read_csv(DSCT_RECALLSAFE_CSV, dtype=str).fillna("")
    new_rows = []
    for _, paper in dsct.iterrows():
        is_known_doi = doi_key(paper[COL_DOI]) and doi_key(paper[COL_DOI]) in known_dois
        if is_known_doi or title_key(paper[COL_TITLE]) in known_titles:
            continue
        new_rows.append(
            {**{col: paper[col] for col in BIBLIOGRAPHIC_COLUMNS}, ORIGIN_COL: ORIGIN_DSCT_SNOWBALL}
        )
    return pd.DataFrame(new_rows)


def build_unified_corpus() -> pd.DataFrame:
    corpus = pd.read_csv(ADULTS_COMBINED_ADJUDICATED_CSV, dtype=str).fillna("")
    corpus.loc[corpus[ORIGIN_COL].str.strip() == "", ORIGIN_COL] = ORIGIN_DATABASE_SEARCH
    dsct_additions = new_dsct_papers(corpus)
    all_papers = pd.concat([corpus, dsct_additions], ignore_index=True).fillna("")
    all_papers.to_csv(ALL_PAPERS_CSV, index=False)
    print(f"all_papers.csv: {len(all_papers)} rows (+{len(dsct_additions)} new DSCT)")
    return all_papers


def main() -> None:
    all_papers = build_unified_corpus()
    targets = all_papers[bedrock_batch.has_usable_abstract(all_papers[COL_ABSTRACT])]
    print(
        f"to classify (abstract>={bedrock_batch.MIN_ABSTRACT_CHARS} chars): {len(targets)}"
        f"  | skipped no-abstract: {len(all_papers) - len(targets)}"
    )

    cfg = load_config("adults")
    records_a, records_b = bedrock_batch.build_records(
        targets,
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_a.prompt_suffix),
        bedrock_batch.with_suffix(CLASSIFICATION_PROMPT, cfg.rater_b.prompt_suffix),
        bedrock_batch.CLASSIFICATION_MAX_TOKENS,
    )
    bedrock_batch.upload_inputs(BATCHES[BIGSCREEN].job_prefix, records_a, records_b)


if __name__ == "__main__":
    main()

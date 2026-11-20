"""Run the adult review's database search against Semantic Scholar.

Usage::

    poetry run python scripts/search/search_semantic_scholar.py

Writes ``semantic_scholar.csv`` into the adult review's database-export folder,
where the pipeline's combine step picks it up as one more source.
"""

from __future__ import annotations

import os

import pandas as pd

from steps.config import load_config
from steps.semantic_scholar import BulkSearchClient, api_key_from_env

# Mirrors the other databases' searches (see search_queries.txt in the adult
# database-export folder), translated to Semantic Scholar bulk-search operators:
# `|` = OR, `+` = AND, `*` = prefix wildcard, `"..."` = phrase, `()` = grouping.
SEARCH_QUERY = (
    "(ADHD | autis* | ASD | Asperger* | AuDHD) "
    '+ (app | "mobile application" | mHealth | eHealth | "digital tool" '
    '| "web-based" | software | "digital therapeutics") '
    "+ adult"
)
MAX_RESULTS = 5000
OUTPUT_FILENAME = "semantic_scholar.csv"


def to_rows(papers: list[dict]) -> list[dict]:
    """Map Semantic Scholar records to the pipeline's standard columns, de-duplicated within the run."""
    rows = []
    seen_keys = set()
    for paper in papers:
        external_ids = paper.get("externalIds") or {}
        doi = (external_ids.get("DOI") or "").strip()
        key = doi.lower() if doi else paper.get("paperId", "")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(
            {
                "Title": paper.get("title") or "",
                "Abstract": paper.get("abstract") or "",
                "Authors": ", ".join(author.get("name", "") for author in (paper.get("authors") or [])),
                "Year": paper.get("year") or "",
                "DOI": doi,
                "PMID": external_ids.get("PubMed") or "",
                "URL": paper.get("url") or "",
                "Journal": paper.get("venue") or "",
            }
        )
    return rows


def main() -> None:
    client = BulkSearchClient(api_key=api_key_from_env())
    papers = list(client.search(SEARCH_QUERY, max_results=MAX_RESULTS))
    print(f"Semantic Scholar reports {client.total_matches} total matches; retrieved {len(papers)}.")

    output_dir = load_config("adults").database_csvs_dir
    os.makedirs(output_dir, exist_ok=True)
    output_csv = os.path.join(output_dir, OUTPUT_FILENAME)
    rows = to_rows(papers)
    pd.DataFrame(rows).to_csv(output_csv, index=False)
    print(f"Saved {len(rows)} unique papers to {output_csv}")


if __name__ == "__main__":
    main()

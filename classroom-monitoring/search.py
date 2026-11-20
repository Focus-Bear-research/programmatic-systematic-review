"""Search Semantic Scholar for studies of classroom monitoring / blocking software.

Usage (from the repo root)::

    poetry run python classroom-monitoring/search.py

Runs every query in ``queries.py`` against the bulk-search endpoint, merges the
results, and writes ``results/semantic_scholar.csv`` (one row per paper, with the
queries that retrieved it) plus ``results/search_log.json`` (hit counts per
query, for reporting).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from queries import QUERIES
from steps.semantic_scholar import BulkSearchClient, api_key_from_env

RESULTS_DIR = Path(__file__).parent / "results"
OUTPUT_CSV = RESULTS_DIR / "semantic_scholar.csv"
SEARCH_LOG_JSON = RESULTS_DIR / "search_log.json"

FIELDS = (
    "title,abstract,authors,year,url,venue,externalIds,"
    "publicationTypes,citationCount,openAccessPdf"
)
MAX_RESULTS_PER_QUERY = 5000
QUERY_SEPARATOR = ";"


def paper_key(paper: dict) -> str:
    doi = ((paper.get("externalIds") or {}).get("DOI") or "").strip().lower()
    return doi or paper.get("paperId", "")


def to_row(paper: dict, matched_queries: list[str]) -> dict:
    external_ids = paper.get("externalIds") or {}
    return {
        "Title": paper.get("title") or "",
        "Abstract": paper.get("abstract") or "",
        "Authors": ", ".join(a.get("name", "") for a in (paper.get("authors") or [])),
        "Year": paper.get("year") or "",
        "Journal": paper.get("venue") or "",
        "DOI": (external_ids.get("DOI") or "").strip(),
        "PMID": external_ids.get("PubMed") or "",
        "URL": paper.get("url") or "",
        "PublicationTypes": QUERY_SEPARATOR.join(paper.get("publicationTypes") or []),
        "CitationCount": paper.get("citationCount") or 0,
        "OpenAccessPdf": (paper.get("openAccessPdf") or {}).get("url") or "",
        "MatchedQueries": QUERY_SEPARATOR.join(matched_queries),
    }


def run_queries(client: BulkSearchClient) -> tuple[dict[str, dict], dict[str, list[str]], dict]:
    """Run every query; return papers by key, query names by key, and a log."""
    papers: dict[str, dict] = {}
    matched: dict[str, list[str]] = {}
    log: dict[str, dict] = {}
    for name, query in QUERIES.items():
        retrieved = 0
        for paper in client.search(query, fields=FIELDS, max_results=MAX_RESULTS_PER_QUERY):
            key = paper_key(paper)
            papers.setdefault(key, paper)
            matched.setdefault(key, []).append(name)
            retrieved += 1
        log[name] = {
            "query": query,
            "total_matches": client.total_matches,
            "retrieved": retrieved,
        }
        print(f"{name}: {client.total_matches} matches, {retrieved} retrieved")
    return papers, matched, log


def main() -> None:
    client = BulkSearchClient(api_key=api_key_from_env())
    papers, matched, log = run_queries(client)

    rows = [to_row(paper, matched[key]) for key, paper in papers.items()]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    SEARCH_LOG_JSON.write_text(json.dumps(
        {"search_date": date.today().isoformat(), "unique_papers": len(rows), "queries": log},
        indent=2,
    ))
    print(f"Saved {len(rows)} unique papers to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()

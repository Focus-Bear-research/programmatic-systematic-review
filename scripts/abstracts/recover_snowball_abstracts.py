"""Recover abstracts for snowball papers the main backfill left without one.

Usage::

    poetry run python scripts/abstracts/recover_snowball_abstracts.py <source>

``<source>`` is one of:

  cascade    publisher landing page, then the Elsevier API for Elsevier DOIs,
             then Semantic Scholar
  s2         Semantic Scholar only
  europepmc  Europe PMC, by DOI or PMID (free, no key, no throttle)
  unpaywall  Unpaywall (needs UNPAYWALL_EMAIL or CONTACT_EMAIL)
  elsevier   Elsevier Abstract Retrieval API, Elsevier DOIs only
  springer   Springer Nature Meta API, Springer-family DOIs only

Elsevier gates the abstract view by institution: with only the free
ELSEVIER_API_KEY every call returns HTTP 401. Run on the institution's network
or VPN, or set ELSEVIER_INSTTOKEN. Springer needs SPRINGER_META_API_KEY or
SPRINGER_OA_API_KEY.

Updates the snowball ``screened.csv`` in place: a recovered row gets its
Abstract and has Screen_Pass / Screen_Reason cleared, so the next screen run
re-evaluates it. Resumable, with a checkpoint every 50 rows. Do not run while
the screen step is running: both write ``screened.csv``.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from scripts.abstracts.fill_missing_abstracts_by_doi import fetch_abstract_unpaywall
from steps.abstract_fetcher import (
    fetch_elsevier,
    fetch_europepmc,
    fetch_landing_page,
    fetch_semantic_scholar,
    fetch_springer,
    resolve_doi_url,
)
from steps.config import semantic_scholar_key, unpaywall_email
from steps.constants import COL_ABSTRACT, COL_DOI, COL_PMID, SCREEN_PASS_COL, SCREEN_REASON_COL
from steps.io import normalize_doi
from steps.paths import SNOWBALL_SCREENED_CSV

NO_ABSTRACT_REASON = "no_abstract"
# Shorter strings are teasers or error text rather than an abstract.
MIN_ABSTRACT_CHARS = 60
CHECKPOINT_EVERY_ROWS = 50
ENTITLEMENT_CHECK_AFTER_ROWS = 10

ELSEVIER_DOI_PREFIXES = ("10.1016", "10.1006", "10.1053", "10.1067", "10.1078")
# 10.1007 = Springer journals and books; the rest are Nature, BMC, Palgrave, Adis and others.
SPRINGER_DOI_PREFIXES = (
    "10.1007",
    "10.1023",
    "10.1038",
    "10.1057",
    "10.1065",
    "10.1140",
    "10.1186",
    "10.1245",
    "10.1361",
    "10.1365",
    "10.3758",
    "10.1617",
)

# (doi, pmid) -> (abstract or None, name of the source that supplied it)
Fetcher = Callable[[str, str], tuple[str | None, str]]


@dataclass(frozen=True)
class Source:
    fetch: Fetcher
    doi_prefixes: tuple[str, ...] | None = None
    accepts_pmid_only: bool = False


def fetch_cascade(doi: str, pmid: str) -> tuple[str | None, str]:
    landing_url = resolve_doi_url(doi)
    if landing_url:
        abstract = fetch_landing_page(landing_url)
        if abstract:
            return abstract, "landing"
    if doi.startswith(ELSEVIER_DOI_PREFIXES):
        abstract = fetch_elsevier(doi)
        if abstract:
            return abstract, "elsevier"
    return fetch_semantic_scholar(doi, semantic_scholar_key()), "s2"


def fetch_europepmc_by_doi_or_pmid(doi: str, pmid: str) -> tuple[str | None, str]:
    return fetch_europepmc(doi=doi, pmid=pmid), "doi" if doi else "pmid"


SOURCES: dict[str, Source] = {
    "cascade": Source(fetch_cascade),
    "s2": Source(lambda doi, pmid: (fetch_semantic_scholar(doi, semantic_scholar_key()), "s2")),
    "europepmc": Source(fetch_europepmc_by_doi_or_pmid, accepts_pmid_only=True),
    "unpaywall": Source(lambda doi, pmid: (fetch_abstract_unpaywall(doi, unpaywall_email()), "unpaywall")),
    "elsevier": Source(lambda doi, pmid: (fetch_elsevier(doi), "elsevier"), ELSEVIER_DOI_PREFIXES),
    "springer": Source(lambda doi, pmid: (fetch_springer(doi), "springer"), SPRINGER_DOI_PREFIXES),
}


def is_eligible(source: Source, doi: str, pmid: str) -> bool:
    if not doi:
        return source.accepts_pmid_only and bool(pmid)
    return source.doi_prefixes is None or doi.startswith(source.doi_prefixes)


def rows_missing_abstract(screened: pd.DataFrame, source: Source) -> list[tuple[int, str, str]]:
    todo = []
    for index in screened.index:
        if screened.at[index, SCREEN_REASON_COL] != NO_ABSTRACT_REASON:
            continue
        doi = normalize_doi(screened.at[index, COL_DOI]) or ""
        pmid = str(screened.at[index, COL_PMID]).strip()
        if is_eligible(source, doi, pmid):
            todo.append((index, doi, pmid))
    return todo


def try_fetch(source: Source, doi: str, pmid: str) -> tuple[str | None, str]:
    # One paper's network or parsing failure must not stop a run of hundreds.
    try:
        return source.fetch(doi, pmid)
    except Exception:  # noqa: BLE001
        return None, ""


def check_prerequisites(source_name: str) -> None:
    if source_name == "elsevier" and not os.getenv("ELSEVIER_API_KEY"):
        sys.exit("ELSEVIER_API_KEY is not set in .env")
    if source_name == "unpaywall" and not unpaywall_email():
        sys.exit("UNPAYWALL_EMAIL (or CONTACT_EMAIL) is not set in .env")


def main(source_name: str) -> None:
    check_prerequisites(source_name)
    source = SOURCES[source_name]
    screened = pd.read_csv(SNOWBALL_SCREENED_CSV, dtype=str).fillna("")
    todo = rows_missing_abstract(screened, source)
    print(f"{len(todo)} papers still missing an abstract; trying {source_name}", flush=True)

    recovered_by: Counter[str] = Counter()
    for count, (index, doi, pmid) in enumerate(todo, 1):
        abstract, supplied_by = try_fetch(source, doi, pmid)
        if abstract and len(abstract) > MIN_ABSTRACT_CHARS:
            screened.at[index, COL_ABSTRACT] = abstract
            screened.at[index, SCREEN_PASS_COL] = ""
            screened.at[index, SCREEN_REASON_COL] = ""
            recovered_by[supplied_by] += 1
        if count % CHECKPOINT_EVERY_ROWS == 0:
            screened.to_csv(SNOWBALL_SCREENED_CSV, index=False)
            print(
                f"  [{count}/{len(todo)}] recovered {recovered_by.total()} {dict(recovered_by)}", flush=True
            )
        if source_name == "elsevier" and count == ENTITLEMENT_CHECK_AFTER_ROWS and not recovered_by:
            print(
                "  (none recovered so far: if these are HTTP 401s you are not on an entitled "
                "network. Stop, connect to the institution's VPN, and re-run.)",
                flush=True,
            )

    screened.to_csv(SNOWBALL_SCREENED_CSV, index=False)
    print(
        f"{source_name} done: recovered {recovered_by.total()}/{len(todo)} {dict(recovered_by)}", flush=True
    )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SOURCES:
        sys.exit(f"usage: recover_snowball_abstracts.py <{'|'.join(SOURCES)}>")
    main(sys.argv[1])

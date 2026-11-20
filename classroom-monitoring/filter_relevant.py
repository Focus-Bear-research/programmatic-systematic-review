"""Keep only search results that actually mention the software of interest.

Usage (from the repo root)::

    poetry run python classroom-monitoring/filter_relevant.py

Semantic Scholar's bulk search stems query terms (``securly`` also retrieves
"secure", ``"family zone"`` retrieves zoning law), so most raw hits are noise.
This deterministic pass keeps a record only when its title or abstract has an
education term AND one of: a product name, a software-category phrase, or an
off-task term. Reads ``results/semantic_scholar.csv`` and writes
``results/candidates.csv`` with the reason each record was kept.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"
SEARCH_RESULTS_CSV = RESULTS_DIR / "semantic_scholar.csv"
CANDIDATES_CSV = RESULTS_DIR / "candidates.csv"

COL_TITLE = "Title"
COL_ABSTRACT = "Abstract"
COL_KEEP_REASON = "KeepReason"

EDUCATION_PATTERN = re.compile(
    r"school|classroom|student|pupil|teacher|lecture|lesson|universit|college|learner|education"
)

# Checked in order; the first pattern that matches is recorded as the reason.
KEEP_PATTERNS: dict[str, re.Pattern[str]] = {
    "product_name": re.compile(
        r"goguardian|linewize|classwize|securly|lanschool|dyknow|blocksi|hapara|veyon"
        r"|\bitalc\b|mythware|netsupport|lightspeed (classroom|systems)|apple classroom\b"
        r"|netop|faronics|smart sync|family zone|qustodio|senso\.cloud|smoothwall"
        r"|bark for schools|impero|gaggle|radix|classroom\.cloud"
    ),
    "software_category": re.compile(
        r"(classroom|screen|student|computer|device|remote|lab) "
        r"(management|monitoring|activity monitoring) (software|system|tool|app)"
        r"|monitoring software|surveillance software|screen monitoring"
        r"|(student|school|classroom) surveillance|dataveillance"
        r"|(website|site|internet|app|distraction) block|(web|internet|content) filter"
    ),
    "off_task": re.compile(r"off[- ]task|distract|multitask|cyberslack|cyberloaf|non-academic"),
}


def keep_reason(text: str) -> str:
    """Return why a record is relevant, or '' if it should be dropped."""
    if not EDUCATION_PATTERN.search(text):
        return ""
    for reason, pattern in KEEP_PATTERNS.items():
        if pattern.search(text):
            return reason
    return ""


def main() -> None:
    papers = pd.read_csv(SEARCH_RESULTS_CSV, dtype=str).fillna("")
    searchable_text = (papers[COL_TITLE] + " " + papers[COL_ABSTRACT]).str.lower()
    papers[COL_KEEP_REASON] = searchable_text.map(keep_reason)

    candidates = papers[papers[COL_KEEP_REASON] != ""]
    candidates.to_csv(CANDIDATES_CSV, index=False)
    print(f"Kept {len(candidates)} of {len(papers)} records -> {CANDIDATES_CSV}")
    print(candidates[COL_KEEP_REASON].value_counts().to_string())


if __name__ == "__main__":
    main()

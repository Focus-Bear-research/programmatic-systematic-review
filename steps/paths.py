"""Data locations shared by more than one script.

Per-review pipeline outputs (combined.csv, screened.csv, ...) come from
:class:`steps.config.Config`. This module holds the files that sit outside that
layout: the unified corpus both reviews read, the full-text stores, and the
masters the full-text scripts pass between each other. All paths are relative
to the repository root, which is where every script is run from.
"""

DATA_DIR = "search-results-from-database"
CITATION_DIR = "citation-scraping"

# Unified corpus that both reviews merge and deduplicate into.
ALL_PAPERS_CSV = f"{DATA_DIR}/all_papers.csv"

ADULTS_COMBINED_ADJUDICATED_CSV = f"{DATA_DIR}/adults/combined/adjudicated.csv"
ADULTS_FULLTEXT_MASTER_CSV = f"{DATA_DIR}/adults/fulltext_review_master.csv"
ADULTS_FULLTEXT_TO_RETRIEVE_CSV = f"{DATA_DIR}/adults/fulltext_to_retrieve.csv"
ADULTS_INTENT_CSV = f"{DATA_DIR}/adults/nd_digital_adults_intent.csv"
CHILDREN_FULLTEXT_MASTER_CSV = f"{DATA_DIR}/children/fulltext_review_master.csv"
CHILDREN_MANUAL_MATCHES_CSV = f"{DATA_DIR}/children/manual_matches_confirmed.csv"

DEDUPED_WITH_SNOWBALL_CSV = f"{DATA_DIR}/deduped-with-snowball.csv"
SNOWBALL_SCREENED_CSV = f"{DATA_DIR}/screened.csv"
SNOWBALL_FULLTEXT_CANDIDATES_CSV = f"{DATA_DIR}/adults/snowball/fulltext_candidates.csv"
SNOWBALL_ADULT_CITATIONS_CSV = f"{CITATION_DIR}/openalex_scraped_citations_adults.csv"

# Extracted publisher full text is copyrighted, so these directories are never committed.
FULL_TEXT_SNOWBALL_DIR = "full_text_snowball"
MANUAL_FULLTEXT_DIR = "manual_fulltext"

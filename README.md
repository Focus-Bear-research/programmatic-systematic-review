# Living systematic review pipeline

Code for two companion systematic reviews of digital interventions for people
with co-occurring ADHD and autism (AuDHD): one in adults, one in under-18s.

The pipeline merges database exports, removes duplicates, recovers missing
abstracts, and screens every record with two independent LLM raters. Records
are excluded only when both raters agree; disagreements go to a human through a
local adjudication UI. Citation snowballing, full-text retrieval and full-text
screening run as separate stages on the survivors.

The manuscript is in [`manuscript/`](manuscript/).

## Layout

```
pipeline.py            Core pipeline: combine -> dedupe -> fill abstracts -> screen -> classify -> adjudicate
adjudicate_ui.py       Local web app for human adjudication of rater disagreements
configs/               One JSON file per review: data paths, rater models, tuned prompt suffixes
steps/                 Library used by the pipeline and every script
scripts/               Stage-specific scripts (see below)
tests/                 Unit tests for the deterministic parts
docs/WORKFLOW.md       End-to-end run instructions
manuscript/            Review manuscript and PRISMA flow
classroom-monitoring/  Separate scoping scan (classroom monitoring software); see its README
search-results-from-database/   Search strategies and PRISMA counts (record-level data is not committed)
```

### `steps/`

| Module | Purpose |
|---|---|
| `config.py` | Loads `configs/<review>.json`; environment-derived settings |
| `schema.py` | Classification fields, allowed values, and the screening and classification prompts |
| `combine.py`, `dedupe.py` | Merge database exports; mark duplicates by DOI, then normalised title |
| `fill_abstracts.py`, `abstract_fetcher.py` | Recover missing abstracts (Semantic Scholar, Crossref, PubMed, Europe PMC, publisher APIs) |
| `screen.py` | Phase 1: two raters code age group and empirical status; exclusion needs agreement |
| `classify.py` | Phase 2: two raters code study type, intervention, neurotypes and outcomes |
| `rules.py` | Deterministic overrides applied on top of rater output |
| `adjudicate.py` | Resolves disagreements (human by default; an LLM third rater if configured) |
| `llm.py` | AWS Bedrock client |
| `bedrock_batch.py`, `batches.py` | Bedrock batch inference for large re-rating runs |
| `full_text.py` | Open-access full-text retrieval and text extraction |
| `semantic_scholar.py` | Semantic Scholar bulk-search client |
| `prisma.py` | Records stage counts for the PRISMA flow diagram |
| `paths.py`, `constants.py`, `io.py` | Shared file locations, column names and CSV helpers |

### `scripts/`

| Folder | Stage |
|---|---|
| `search/` | Database search run through an API (Semantic Scholar) |
| `snowball/` | Backward and forward citation searching from seed reviews, and screening of what it finds |
| `abstracts/` | Abstract recovery beyond the pipeline step, including institutional access |
| `batch/` | Build, submit and merge Bedrock batch re-rating jobs |
| `fulltext/` | Full-text retrieval and ingestion of manually downloaded PDFs |
| `adults/` | Adult review: candidate master, design / outcome / intent coding, full-text screen |
| `children/` | Children's review: dataset assembly, triage, PDF matching, full-text screen |
| `validation/` | Prompt tuning, screening accuracy against blind human labels, model reachability check |

Each script's docstring states what it reads and writes.

## Setup

Requires Python 3.13 and [Poetry](https://python-poetry.org/).

```bash
poetry install
cp .env.example .env    # then fill in the values you need
poetry run pytest
```

LLM steps call models through AWS Bedrock, so they need AWS credentials with
Bedrock access. Rater models are set per review in `configs/`. Everything else
(combine, dedupe, abstract recovery, the adjudication UI) runs without AWS.

## Running

Run every command from the repository root; data paths are relative to it.

```bash
poetry run python scripts/validation/verify_bedrock.py adults   # check the configured models are reachable
poetry run python pipeline.py adults                            # or: children
poetry run python adjudicate_ui.py adults                       # then open http://localhost:8000
```

Put each database export in the folder named by the review's
`paths.database_csvs_subdir` (the filename stem becomes the source name, for
example `pubmed.csv`). Each pipeline step caches its output CSV; delete the file
to re-run that step. [`docs/WORKFLOW.md`](docs/WORKFLOW.md) covers prompt tuning
and adjudication in more detail.

## Data

Record-level data (titles, abstracts, labels) and extracted full text are not
in this repository: abstracts and full text are publisher copyright. What is
committed:

- the database search strategies (`search-results-from-database/adults/database-csvs/*.txt`)
- PRISMA stage counts (`search-results-from-database/adults/prisma_counts.json`)
- the review protocol notes (`search-results-from-database/adults/supervisor_meeting_summary.md`)

## Reproducibility notes

- Raters run at temperature 0, but hosted models are not bit-for-bit
  deterministic and model versions are retired over time. Re-running the LLM
  steps will not reproduce every label exactly.
- Scripts outside `pipeline.py` were run once, in sequence, as the reviews
  progressed. They record what was done; several read intermediate files that a
  later stage has since moved or replaced.
- Screening accuracy against blind human labels is reported in the manuscript.

## Licence

MIT. See [`LICENSE`](LICENSE).

# Classroom monitoring and blocking software: evidence scan

A rapid search for studies of classroom device-monitoring and website-blocking
software (GoGuardian, Linewize/Classwize, Securly, NetSupport School, LanSchool,
Apple Classroom and similar), run to check whether any randomised trials exist.
It is separate from the two AuDHD systematic reviews in this repository and is a
scoping scan, not a systematic review: one database, one screener.

## How to run

From the repository root, after `poetry install`:

```bash
poetry run python classroom-monitoring/search.py           # query Semantic Scholar
poetry run python classroom-monitoring/filter_relevant.py  # drop off-topic hits
```

| File | What it is |
|---|---|
| `queries.py` | The seven search strings (Semantic Scholar bulk-search syntax) |
| `search.py` | Runs the queries, merges results, records which query found each paper |
| `filter_relevant.py` | Deterministic keyword filter that removes off-topic hits |
| `results/search_log.json` | Search date and hit counts per query |
| `results/semantic_scholar.csv` | All retrieved records |
| `results/candidates.csv` | Records that pass the keyword filter |
| `results/shortlist.csv` | Hand-screened relevant studies, coded by design and relevance |

## Search (21 November 2026)

| Query | Hits |
|---|---|
| Product names | 1,429 |
| Ambiguous product names + school term | 173 |
| Software category + school term | 619 |
| Surveillance + school + device | 90 |
| Device + classroom + off-task + restriction | 323 |
| Blocking / filtering + school term | 329 |
| Device + classroom + off-task + trial design | 276 |
| **Unique records** | **3,114** |

Most raw hits are noise. Semantic Scholar stems query terms, so `securly`
retrieves "secure" and `"family zone"` retrieves zoning law. The keyword filter
keeps 773 records. One screener read all 773 titles, then the abstracts of 76,
and coded 33 as relevant (`results/shortlist.csv`).

## Findings

**No randomised trial of commercial classroom monitoring software was found.**
Nothing in the search tests whether GoGuardian, Linewize, Securly, LanSchool or
Apple Classroom reduces off-task use or improves learning with a randomised or
well-controlled design.

What does exist falls into four groups:

1. **Randomised trials of neighbouring interventions, all in higher education.**
   Patterson (2018) randomised online-course students to a commitment device, an
   alert tool or a distraction blocker. The commitment device raised course time,
   grades and completion; the blocker had no significant effect. Aksoy, Lusher
   and Carrell (2025) ran a field experiment with an app that rewards students
   for staying off their phones in class: focus and attendance improved, grades
   did not change significantly, and study time fell.
2. **Qualitative and critical studies of monitoring software in schools.**
   Selwyn and Cumbo (2024), Sarin and Hill-Bonnet (2025), Crooks (2019), and two
   small interview studies of GoGuardian Teacher (Pungong, 2023). These describe
   uneven teacher use, student workarounds and privacy concerns. None measures
   off-task behaviour.
3. **Small quasi-experiments of lab-management software as a teaching medium.**
   About 40 records, mostly from Indonesia, Peru and China, on NetSupport School,
   NetOp School, iTALC and Mythware. The outcome is test scores after teaching
   through the software (screen broadcast, file distribution), not distraction.
   Designs are classroom action research or non-equivalent groups with small
   samples.
4. **Digital self-control tools chosen by students.** Lyngs et al. (2024, two
   papers) and Hariadi et al. (2026, neurodivergent students). Pre-post or
   qualitative.

A large share of the remaining candidates are engineering papers describing
camera-based attention detection or attendance systems, which are out of scope.

## Limitations

- Semantic Scholar matches title and abstract only, and only 968 of the 3,114
  records came with an abstract. A study that names the product only in its
  methods section is missed.
- No education database (ERIC), no dissertations index, no forward or backward
  citation search, and no grey literature. Vendor-commissioned evaluations are
  not indexed here.
- One screener, no second rater.

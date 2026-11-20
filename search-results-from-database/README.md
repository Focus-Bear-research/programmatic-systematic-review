# search-results-from-database — layout

Two companion systematic reviews, cleanly separated. Shared corpora stay in this root.

```
search-results-from-database/
├── all_papers.csv                 # SHARED unified corpus (both reviews merge + dedup into this)
├── all_papers_pre_*_backup.csv    # SHARED snapshots
├── adults/                        # ADULT review — digital interventions for adults with co-occurring AuDHD
│   ├── database-csvs/             #   adult database search exports (PubMed/Scopus/PsycINFO/WoS/…)
│   ├── combined/ , snowball/      #   adult pipeline intermediates (citation + DSCT snowball)
│   ├── fulltext_review_master.csv #   adult full-text candidate master
│   ├── nd_digital_adults_intent.csv, nd_digital_empirical.csv   # scoping corpus + intent coding
│   ├── adults_fulltext_analysis.csv          # exploratory full-text analysis (co-design, support level, intent)
│   ├── adults_fulltext_screen_narrative.csv  # narrative-rule full-text re-screen
│   ├── adults_fulltext_to_retrieve_*.{csv,xlsx}  # outstanding full-text retrieval list
│   ├── validation_sample.csv      #   blind IRR validation sample
│   └── supervisor_meeting_summary.md         # adult protocol / scope decisions
└── children/                      # CHILDREN companion review (<18)
    ├── database-csvs/             #   children-specific database search exports
    ├── fulltext_review_master.csv, enriched.csv, adjudicated.csv …
    ├── FINAL_includes_narrative_2026-08-23.csv   # the confirmed include set
    ├── IRR_sebrina_vs_llm.csv, maybe_triage_*.csv  # human IRR + maybe adjudication
    └── review20_adjudication_*.csv, …
```

Paths are driven by `configs/{adults,children}.json` (`review_subdir` = `adults` / `children`). Adult/children-specific scripts hardcode their review's subdir; `all_papers.csv` is the only shared data file both pipelines read.

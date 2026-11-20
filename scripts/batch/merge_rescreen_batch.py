"""Merge the Phase-1 re-screen batch into the combined adult dataset.

Usage::

    poetry run python scripts/batch/merge_rescreen_batch.py

Updates has_adults / has_under_18 / is_empirical for both raters, then re-runs
the screen gate. Rows where both raters now say has_adults=no fail the gate
(Screen_Pass=N) and drop out. Reports how many rows flipped. The CSV is backed
up first. Stop the adjudication UI before running: both write the file.
"""

from __future__ import annotations

import shutil

import pandas as pd

from steps import bedrock_batch, rules, screen
from steps.batches import BATCHES, RESCREEN
from steps.config import load_config, set_active
from steps.constants import COL_ABSTRACT, COL_TITLE, NO, SCREEN_PASS_COL, SCREEN_REASON_COL, YES
from steps.schema import SCREEN_FIELDS, coerce_screen

BATCH = BATCHES[RESCREEN]
AGE_FIELD = "has_adults"
AGE_ABSENT = "no"


def _normalised(value: object) -> str:
    return str(value).strip().lower()


def screen_rule_overrides(title: str, abstract: str) -> dict:
    overrides = rules.apply_rules(title, abstract)
    return {field: value for field, value in overrides.items() if field in SCREEN_FIELDS}


def main() -> None:
    cfg = load_config("adults")
    set_active(cfg)
    require_age = (cfg.raw.get("screening") or {}).get("require_age")
    results_a, results_b = bedrock_batch.load_rater_results(BATCH.job_prefix, coerce_screen)

    papers = pd.read_csv(BATCH.target_csv, dtype=str).fillna("")
    shutil.copy(BATCH.target_csv, BATCH.backup_csv)
    rated_by_both = set(results_a) & set(results_b)
    both_say_no_adults = 0
    newly_dropped = 0
    for index in rated_by_both:
        if index not in papers.index:
            continue
        overrides = screen_rule_overrides(
            str(papers.at[index, COL_TITLE] or ""), str(papers.at[index, COL_ABSTRACT] or "")
        )
        labels_a = {**results_a[index], **overrides}
        labels_b = {**results_b[index], **overrides}
        for field in SCREEN_FIELDS:
            papers.at[index, f"RaterA_{field}"] = labels_a.get(field, "")
            papers.at[index, f"RaterB_{field}"] = labels_b.get(field, "")
            agreed = _normalised(labels_a.get(field)) == _normalised(labels_b.get(field))
            papers.at[index, f"Consensus_{field}"] = labels_a.get(field) if agreed else ""
        screen_pass, reason = screen._gate(labels_a, labels_b, require_age)
        if (
            _normalised(labels_a.get(AGE_FIELD)) == AGE_ABSENT
            and _normalised(labels_b.get(AGE_FIELD)) == AGE_ABSENT
        ):
            both_say_no_adults += 1
        was_passing = _normalised(papers.at[index, SCREEN_PASS_COL]) == YES.lower()
        if was_passing and _normalised(screen_pass) == NO.lower():
            newly_dropped += 1
        papers.at[index, SCREEN_PASS_COL] = screen_pass
        papers.at[index, SCREEN_REASON_COL] = reason
    papers.to_csv(BATCH.target_csv, index=False)
    print(
        f"merged {len(rated_by_both)} | both-raters has_adults=no: {both_say_no_adults} | "
        f"newly dropped (Y->N): {newly_dropped}"
    )


if __name__ == "__main__":
    main()

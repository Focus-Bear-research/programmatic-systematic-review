"""Registry of the Bedrock classification batches run for the two reviews.

One entry per batch, shared by the build, submit and merge scripts so the S3
job names and the CSV each batch writes back to stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

from .paths import ADULTS_COMBINED_ADJUDICATED_CSV, ALL_PAPERS_CSV


@dataclass(frozen=True)
class Batch:
    """One Bedrock batch run: its S3 job prefix and the CSV it re-rates."""

    job_prefix: str
    target_csv: str
    backup_suffix: str

    @property
    def backup_csv(self) -> str:
        return self.target_csv.replace(".csv", f"{self.backup_suffix}.csv")


RECLASSIFY = "reclassify"
RESCREEN = "rescreen"
BIGSCREEN = "bigscreen"
CHILDREN_EXPANDED = "children_expanded"
CHILDREN_GAP = "children_gap"

BATCHES: dict[str, Batch] = {
    # Adult screen survivors re-rated after the taxonomy split data_collection_only from no_intervention.
    RECLASSIFY: Batch("", ADULTS_COMBINED_ADJUDICATED_CSV, "_pre_batch_backup"),
    # Phase-1 re-screen of has_adults=yes survivors under the redefined has_adults criterion.
    RESCREEN: Batch("screen", ADULTS_COMBINED_ADJUDICATED_CSV, "_pre_rescreen_age_backup"),
    # Every paper with an abstract in the unified corpus.
    BIGSCREEN: Batch("big", ALL_PAPERS_CSV, "_pre_bigscreen_backup"),
    # Rows added by the expanded children's database search.
    CHILDREN_EXPANDED: Batch("child_exp", ALL_PAPERS_CSV, "_pre_childexp_backup"),
    # Child-screen survivors that never received a detail classification.
    CHILDREN_GAP: Batch("child_gap", ALL_PAPERS_CSV, "_pre_childgap_backup"),
}

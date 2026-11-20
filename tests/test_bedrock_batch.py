"""Batch record construction and the two-rater merge, with no AWS calls."""

from __future__ import annotations

import pandas as pd

from steps import bedrock_batch
from steps.batches import BATCHES, RECLASSIFY
from steps.config import load_config
from steps.schema import CONSENSUS_FIELDS

AGREED_LABELS = {field: "unspecified" for field in CONSENSUS_FIELDS}


def test_record_id_round_trips_row_index():
    assert bedrock_batch.record_id(42) == "rec0000042"
    assert bedrock_batch.row_index(bedrock_batch.record_id(42)) == 42


def test_job_names_use_prefix_when_present():
    assert bedrock_batch.job_names("big") == ("big_nova", "big_sonnet")
    assert bedrock_batch.job_names("") == ("nova", "sonnet")


def test_with_suffix_leaves_prompt_alone_without_suffix():
    assert bedrock_batch.with_suffix("PROMPT", "") == "PROMPT"
    assert bedrock_batch.with_suffix("PROMPT", "NOTE") == "PROMPT\n\nNOTE"


def test_build_records_keys_both_raters_by_frame_index():
    papers = pd.DataFrame({"Title": ["T"], "Abstract": ["A"]}, index=[7])
    records_a, records_b = bedrock_batch.build_records(papers, "SYS_A", "SYS_B", 100)

    assert records_a[0]["recordId"] == records_b[0]["recordId"] == "rec0000007"
    assert records_a[0]["modelInput"]["system"] == [{"text": "SYS_A"}]
    assert records_b[0]["modelInput"]["system"] == "SYS_B"
    assert records_b[0]["modelInput"]["messages"][0]["content"] == "Title: T\n\nAbstract: A"


def test_has_usable_abstract_rejects_placeholders():
    abstracts = pd.Series(["N/A", "x" * bedrock_batch.MIN_ABSTRACT_CHARS])
    assert bedrock_batch.has_usable_abstract(abstracts).tolist() == [False, True]


def test_merge_writes_consensus_only_where_raters_agree():
    papers = pd.DataFrame({"Title": ["An app trial", "Another trial"], "Abstract": ["", ""]})
    results_a = {0: dict(AGREED_LABELS), 1: {**AGREED_LABELS, "study_type": "rct"}}
    results_b = {0: dict(AGREED_LABELS), 1: {**AGREED_LABELS, "study_type": "qualitative"}}

    updated = bedrock_batch.merge_classifications(papers, results_a, results_b, load_config("adults"))

    assert updated == 2
    assert papers.at[0, "Consensus_Reached"] == "Y"
    assert papers.at[1, "Consensus_Reached"] == "N"
    assert papers.at[1, "Consensus_study_type"] == ""
    assert papers.at[1, "RaterA_study_type"] == "rct"
    assert papers.at[1, "RaterB_study_type"] == "qualitative"


def test_merge_skips_rows_only_one_rater_returned():
    papers = pd.DataFrame({"Title": ["T"], "Abstract": [""]})
    updated = bedrock_batch.merge_classifications(papers, {0: dict(AGREED_LABELS)}, {}, load_config("adults"))
    assert updated == 0


def test_backup_path_sits_beside_target():
    batch = BATCHES[RECLASSIFY]
    assert batch.backup_csv.endswith("adjudicated_pre_batch_backup.csv")

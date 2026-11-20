"""Bedrock batch inference for the two raters: build inputs, submit jobs, merge outputs.

Batch inference re-rates thousands of records at about half the on-demand price.
The flow is three scripts sharing a ``job_prefix``:

  1. build  — write one JSONL per rater and upload to ``s3://<bucket>/input/``
  2. submit — start one model-invocation job per rater
  3. merge  — download ``s3://<bucket>/output/<job>/`` and write rater columns

Each record's ``recordId`` encodes the row index of the CSV being re-rated, so
the merge step can write results back by position. Rater A must be an Amazon
Nova model and rater B an Anthropic model: the two families use different
request and response schemas.

Needs ``BEDROCK_BATCH_BUCKET`` and (for submit) ``BEDROCK_BATCH_ROLE_ARN``.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Callable

import boto3
import pandas as pd

from . import rules
from .config import Config, require_env
from .constants import COL_ABSTRACT, COL_TITLE, CONSENSUS_REACHED_COL, NO, YES
from .schema import CONSENSUS_FIELDS

BATCH_REGION = "us-east-1"
ANTHROPIC_VERSION = "bedrock-2023-05-31"
RATER_A_JOB_SUFFIX = "nova"
RATER_B_JOB_SUFFIX = "sonnet"

RECORD_ID_PREFIX = "rec"
RECORD_ID_DIGITS = 7
# Abstracts shorter than this are placeholders ("N/A", "No abstract"), not text to rate.
MIN_ABSTRACT_CHARS = 20

INPUT_PREFIX = "input"
OUTPUT_PREFIX = "output"
OUTPUT_FILE_SUFFIX = ".jsonl.out"

CLASSIFICATION_MAX_TOKENS = 1024
SCREEN_MAX_TOKENS = 400

# Free-text field written per rater but never compared for consensus.
INTERVENTION_DETAILS_FIELD = "intervention_details"

Coercer = Callable[[dict], dict]


def bucket() -> str:
    return require_env("BEDROCK_BATCH_BUCKET", "S3 bucket for Bedrock batch input and output")


def role_arn() -> str:
    return require_env(
        "BEDROCK_BATCH_ROLE_ARN", "IAM role Bedrock assumes to read and write the batch bucket"
    )


def job_names(job_prefix: str) -> tuple[str, str]:
    """Return the (rater A, rater B) job names for a batch, e.g. ``big_nova``, ``big_sonnet``."""
    if not job_prefix:
        return RATER_A_JOB_SUFFIX, RATER_B_JOB_SUFFIX
    return f"{job_prefix}_{RATER_A_JOB_SUFFIX}", f"{job_prefix}_{RATER_B_JOB_SUFFIX}"


def record_id(row_index: int) -> str:
    return f"{RECORD_ID_PREFIX}{int(row_index):0{RECORD_ID_DIGITS}d}"


def row_index(record_id_value: str) -> int:
    return int(record_id_value[len(RECORD_ID_PREFIX) :])


def has_usable_abstract(abstracts: pd.Series) -> pd.Series:
    return abstracts.str.len() >= MIN_ABSTRACT_CHARS


def with_suffix(system_prompt: str, rater_suffix: str) -> str:
    """Append a rater's tuned prompt suffix, if it has one."""
    if not rater_suffix:
        return system_prompt
    return f"{system_prompt}\n\n{rater_suffix}"


def user_prompt(title: str, abstract: str) -> str:
    return f"Title: {title}\n\nAbstract: {abstract}"


def nova_record(index: int, system_prompt: str, prompt: str, max_tokens: int) -> dict:
    return {
        "recordId": record_id(index),
        "modelInput": {
            "system": [{"text": system_prompt}],
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
        },
    }


def anthropic_record(index: int, system_prompt: str, prompt: str, max_tokens: int) -> dict:
    return {
        "recordId": record_id(index),
        "modelInput": {
            "anthropic_version": ANTHROPIC_VERSION,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        },
    }


def build_records(
    papers: pd.DataFrame, system_a: str, system_b: str, max_tokens: int
) -> tuple[list[dict], list[dict]]:
    """Build (rater A, rater B) batch records for every row, keyed by the frame's index."""
    records_a, records_b = [], []
    for index, paper in papers.iterrows():
        prompt = user_prompt(paper.get(COL_TITLE, ""), paper.get(COL_ABSTRACT, ""))
        records_a.append(nova_record(index, system_a, prompt, max_tokens))
        records_b.append(anthropic_record(index, system_b, prompt, max_tokens))
    return records_a, records_b


def _s3():
    return boto3.Session(region_name=BATCH_REGION).client("s3")


def upload_inputs(job_prefix: str, records_a: list[dict], records_b: list[dict]) -> None:
    """Write one JSONL per rater and upload both to the batch bucket's input folder."""
    s3 = _s3()
    name_a, name_b = job_names(job_prefix)
    with tempfile.TemporaryDirectory() as work_dir:
        for name, records in ((name_b, records_b), (name_a, records_a)):
            local_path = Path(work_dir) / f"{name}.jsonl"
            local_path.write_text("".join(json.dumps(record) + "\n" for record in records))
            key = f"{INPUT_PREFIX}/{name}.jsonl"
            s3.upload_file(str(local_path), bucket(), key)
            print(f"  uploaded {len(records)} -> s3://{bucket()}/{key}")


def submit_jobs(job_prefix: str, cfg: Config) -> dict[str, str]:
    """Start one batch job per rater; return job ARNs by job name."""
    bedrock = boto3.Session(region_name=BATCH_REGION).client("bedrock")
    name_a, name_b = job_names(job_prefix)
    model_ids = {name_a: cfg.rater_a.model_id, name_b: cfg.rater_b.model_id}
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    job_arns = {}
    for name, model_id in model_ids.items():
        response = bedrock.create_model_invocation_job(
            jobName=f"litreview-{name.replace('_', '-')}-{timestamp}",
            roleArn=role_arn(),
            modelId=model_id,
            inputDataConfig={"s3InputDataConfig": {"s3Uri": f"s3://{bucket()}/{INPUT_PREFIX}/{name}.jsonl"}},
            outputDataConfig={"s3OutputDataConfig": {"s3Uri": f"s3://{bucket()}/{OUTPUT_PREFIX}/{name}/"}},
        )
        job_arns[name] = response["jobArn"]
        print(f"submitted {name}: {response['jobArn']}")
    return job_arns


def _response_text(job_name: str, model_output: dict) -> str:
    if RATER_B_JOB_SUFFIX in job_name:
        blocks = model_output.get("content", [])
        return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    blocks = model_output.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks)


def _parse_json_object(text: str) -> dict | None:
    """Extract the outermost JSON object from a model reply; None if there isn't one."""
    try:
        return json.loads(text[text.index("{") : text.rindex("}") + 1])
    except ValueError:
        return None


def load_results(job_name: str, coerce: Coercer) -> dict[int, dict]:
    """Download a job's output and return coerced labels by CSV row index.

    Records the model failed on, or whose reply is not JSON, are skipped; the
    merge only writes rows that both raters returned.
    """
    s3 = _s3()
    prefix = f"{OUTPUT_PREFIX}/{job_name}/"
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefix)
    keys = [
        entry["Key"]
        for page in pages
        for entry in page.get("Contents", [])
        if entry["Key"].endswith(OUTPUT_FILE_SUFFIX)
    ]
    results: dict[int, dict] = {}
    for key in keys:
        body = s3.get_object(Bucket=bucket(), Key=key)["Body"].read().decode()
        for line in body.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            model_output = record.get("modelOutput")
            if not model_output:
                continue
            labels = _parse_json_object(_response_text(job_name, model_output))
            if labels is None:
                continue
            results[row_index(record["recordId"])] = coerce(labels)
    return results


def load_rater_results(job_prefix: str, coerce: Coercer) -> tuple[dict[int, dict], dict[int, dict]]:
    name_a, name_b = job_names(job_prefix)
    results_a, results_b = load_results(name_a, coerce), load_results(name_b, coerce)
    print(f"parsed {name_a}={len(results_a)} {name_b}={len(results_b)}")
    return results_a, results_b


def _normalised(value: object) -> str:
    return str(value).strip().lower()


def with_rule_overrides(labels: dict, overrides: dict) -> dict:
    """Apply deterministic rule overrides to the fields a rater actually returned."""
    return {**labels, **{field: value for field, value in overrides.items() if field in labels}}


def merge_classifications(
    papers: pd.DataFrame, results_a: dict[int, dict], results_b: dict[int, dict], cfg: Config
) -> int:
    """Write RaterA_/RaterB_/Consensus_ columns for rows both raters classified.

    Leaves Final_/Human_/Adjudicated untouched. Returns the number of rows updated.
    """
    rated_fields = CONSENSUS_FIELDS + [INTERVENTION_DETAILS_FIELD]
    updated = 0
    for index in set(results_a) & set(results_b):
        if index not in papers.index:
            continue
        overrides = rules.apply_rules(
            str(papers.at[index, COL_TITLE] or ""), str(papers.at[index, COL_ABSTRACT] or "")
        )
        labels_a = with_rule_overrides(results_a[index], overrides)
        labels_b = with_rule_overrides(results_b[index], overrides)
        for field in rated_fields:
            value_a, value_b = labels_a.get(field, ""), labels_b.get(field, "")
            papers.at[index, f"RaterA_{field}"] = value_a
            papers.at[index, f"RaterB_{field}"] = value_b
            if field in CONSENSUS_FIELDS:
                agreed = _normalised(value_a) == _normalised(value_b)
                papers.at[index, f"Consensus_{field}"] = value_a if agreed else ""
        papers.at[index, "RaterA_model"] = cfg.rater_a.label
        papers.at[index, "RaterB_model"] = cfg.rater_b.label
        all_agreed = all(
            _normalised(labels_a.get(field)) == _normalised(labels_b.get(field)) for field in CONSENSUS_FIELDS
        )
        papers.at[index, CONSENSUS_REACHED_COL] = YES if all_agreed else NO
        updated += 1
    return updated

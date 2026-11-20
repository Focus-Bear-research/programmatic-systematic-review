"""Submit the two Bedrock batch-inference jobs (one per rater) for a built batch.

Usage::

    poetry run python scripts/batch/submit_batch.py <batch>

``<batch>`` is a key of ``steps.batches.BATCHES`` (reclassify, rescreen,
bigscreen, children_expanded, children_gap). Job ARNs are printed and saved so
progress can be polled with ``aws bedrock get-model-invocation-job``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from steps import bedrock_batch
from steps.batches import BATCHES
from steps.config import load_config


def main(batch_name: str) -> None:
    job_arns = bedrock_batch.submit_jobs(BATCHES[batch_name].job_prefix, load_config("adults"))
    arns_path = Path(tempfile.gettempdir()) / f"batch_jobs_{batch_name}.json"
    arns_path.write_text(json.dumps(job_arns))
    print(f"saved {arns_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in BATCHES:
        sys.exit(f"usage: submit_batch.py <{'|'.join(BATCHES)}>")
    main(sys.argv[1])

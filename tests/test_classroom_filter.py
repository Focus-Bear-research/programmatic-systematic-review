from __future__ import annotations

import importlib.util
from pathlib import Path

# classroom-monitoring/ is a folder of standalone scripts, not an importable package.
_SCRIPT = Path(__file__).resolve().parent.parent / "classroom-monitoring" / "filter_relevant.py"
_spec = importlib.util.spec_from_file_location("filter_relevant", _SCRIPT)
filter_relevant = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_relevant)


def test_product_name_in_school_context_is_kept():
    assert filter_relevant.keep_reason("goguardian teacher in high school classrooms") == "product_name"


def test_stemming_noise_is_dropped():
    assert filter_relevant.keep_reason("tvt-secur sling after 5 years of follow-up") == ""


def test_off_task_term_needs_an_education_term():
    assert filter_relevant.keep_reason("driver distraction detection cameras") == ""
    assert filter_relevant.keep_reason("laptop distraction in university lectures") == "off_task"

from __future__ import annotations

from steps.io import normalize_doi


def test_normalize_doi_strips_resolver_prefix():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/ABC"


def test_normalize_doi_returns_none_for_missing_values():
    assert normalize_doi("") is None
    assert normalize_doi(None) is None

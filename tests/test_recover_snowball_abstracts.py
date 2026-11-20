from __future__ import annotations

from scripts.abstracts.recover_snowball_abstracts import SOURCES, is_eligible

ELSEVIER_DOI = "10.1016/j.example.2020.01.001"
SPRINGER_DOI = "10.1007/s00000-020-00000-0"
PMID = "12345678"


def test_publisher_sources_only_take_their_own_dois():
    assert is_eligible(SOURCES["elsevier"], ELSEVIER_DOI, "")
    assert not is_eligible(SOURCES["elsevier"], SPRINGER_DOI, "")
    assert is_eligible(SOURCES["springer"], SPRINGER_DOI, "")


def test_only_europepmc_accepts_a_paper_with_no_doi():
    assert is_eligible(SOURCES["europepmc"], "", PMID)
    assert not is_eligible(SOURCES["s2"], "", PMID)
    assert not is_eligible(SOURCES["europepmc"], "", "")

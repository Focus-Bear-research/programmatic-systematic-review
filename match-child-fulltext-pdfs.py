#!/usr/bin/env python3
"""Match manually-retrieved child-review full-text PDFs against the candidate master.

Sebrina supplied numbered PDFs (1.pdf ... N.pdf) in OneDrive folders. Filenames carry
no bibliographic info, so we open each PDF, derive its DOI and title, and match against
children/fulltext_review_master.csv:

  1. DOI match  — DOI found on PAGE 1 only (title zone), exact on normalised DOI.
     Restricting to page 1 avoids matching reference-list DOIs (a paper citing another
     candidate would otherwise be mis-identified as that candidate).
  2. Title match — the PDF's OWN title (embedded metadata title, else the first
     substantive lines of page 1) vs each candidate title, scored with a symmetric
     token_sort_ratio. Title-to-title (not short-title-into-fulltext) is what stops a
     4-word candidate like "SIDES"/"TOBY"/"PECS" from spuriously matching any PDF that
     merely contains that word.

Writes children/manual_fulltext_matches.csv (one row per PDF) and prints a summary.

Usage: poetry run python match-child-fulltext-pdfs.py "<pdf_root_folder>"
"""
import re
import sys
import subprocess
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

MASTER = "search-results-from-database/children/fulltext_review_master.csv"
OUT = "search-results-from-database/children/manual_fulltext_matches.csv"
CONFIRMED = "search-results-from-database/children/manual_matches_confirmed.csv"
NEEDS_REVIEW = "search-results-from-database/children/manual_matches_needs_review.csv"

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
TITLE_MATCH_THRESHOLD = 92   # partial_ratio; at/above -> trusted match
TITLE_REVIEW_FLOOR = 80      # between floor and threshold -> flag for human review
MIN_CAND_CHARS = 20          # candidate titles shorter than this only match by DOI or
                             # anchored token-prefix (avoids "SIDES"-in-"besides" hits)
FRAGMENT_GUARD = 55          # a partial_ratio title match whose token_sort_ratio is
                             # below this is the candidate being a mere fragment of a
                             # longer, likely-different PDF title -> send to review
MIN_FULLTEXT_CAND_CHARS = 40 # only titles this long may match against raw page-1 text
                             # (last-resort recovery when the title blob is junk)
FULLTEXT_MATCH_THRESHOLD = 93
FULLTEXT_REVIEW_FLOOR = 85

# metadata titles that are boilerplate/junk rather than the real article title
JUNK_TITLE_RE = re.compile(r"^\s*(https?:|www\.|untitled|microsoft word|ieee xplore|"
                           r"doi:|\d+\s*$|.{0,6}$)", re.I)


def norm_doi(d):
    if not isinstance(d, str):
        return ""
    d = d.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.rstrip(".").rstrip(")")


def norm_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def tokens(s):
    return re.findall(r"\w+", (s or "").lower())


def pdf_page1_text(path):
    """Text of page 1 only, via poppler's pdftotext."""
    try:
        out = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "1", str(path), "-"],
            capture_output=True, timeout=60,
        )
        return out.stdout.decode("utf-8", "ignore")
    except Exception:
        return ""


def pdf_meta_title(path):
    """Embedded metadata title via pdfinfo (often the cleanest title source)."""
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=30)
        for line in out.stdout.decode("utf-8", "ignore").splitlines():
            if line.startswith("Title:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


# lines on page 1 that are chrome, not the article title
_CRUFT_RE = re.compile(
    r"(^\s*$|research-article|^\s*session:|proceedings|^\s*\d+\s*$|@|http|www\.|"
    r"downloaded|copyright|©|all rights reserved|^\s*(article|original article|"
    r"abstract|introduction)\s*$|journal of|vol\.|issn|doi:|^page\s|conference on|"
    r"university|department|springer|elsevier|wiley|sage|taylor)", re.I)


def title_from_page1(text):
    """Best-effort article title from the top of page 1 when metadata is missing/junk.

    Takes the first run of substantive, non-chrome lines and joins them (titles often
    wrap across 2-3 lines)."""
    lines = [ln.strip() for ln in text.splitlines()]
    picked = []
    for ln in lines:
        if not ln:
            if picked:
                break
            continue
        if _CRUFT_RE.search(ln) or len(ln) < 4 or sum(c.isalpha() for c in ln) < 3:
            if picked:
                break
            continue
        picked.append(ln)
        if len(" ".join(picked)) > 200:
            break
    return " ".join(picked)


def pdf_title(meta, page1_text):
    if meta and not JUNK_TITLE_RE.match(meta) and sum(c.isalpha() for c in meta) >= 6:
        return meta
    return title_from_page1(page1_text)


def extract_doi(text):
    for raw in DOI_RE.findall(text):
        # strip trailing junk that regularly clings to DOIs in extracted text
        cand = raw.rstrip(".,;)").strip()
        return norm_doi(cand)
    return ""


def main():
    roots = [Path(a) for a in sys.argv[1:]]
    if not roots or not all(r.is_dir() for r in roots):
        sys.exit(f"pdf root folder(s) not found: {[str(r) for r in roots] or None}")

    m = pd.read_csv(MASTER)
    m["_doi"] = m["DOI"].map(norm_doi)
    m["_title_n"] = m["Title"].map(norm_text)
    doi_to_idx = {d: i for i, d in zip(m.index, m["_doi"]) if d}

    # Long candidate titles -> fuzzy partial_ratio against the PDF's title blob.
    long_titles, long_idx = [], []
    # Short candidate titles (e.g. "MOSOCO", "TOBY") -> anchored token-prefix only.
    short_tokens, short_idx = [], []
    # Very long titles are also matched against the raw page-1 text as a fallback.
    ft_titles, ft_idx = [], []
    for i, t in zip(m.index, m["_title_n"]):
        if len(t) >= MIN_CAND_CHARS:
            long_titles.append(t)
            long_idx.append(i)
        elif t:
            short_tokens.append(tokens(t))
            short_idx.append(i)
        if len(t) >= MIN_FULLTEXT_CAND_CHARS:
            ft_titles.append(t)
            ft_idx.append(i)

    pdfs = sorted((p for r in roots for p in r.rglob("*.pdf")), key=lambda p: str(p))
    print(f"{len(pdfs)} PDFs under {len(roots)} folder(s)\n")

    rows = []
    for i, pdf in enumerate(pdfs, 1):
        text = pdf_page1_text(pdf)
        meta = pdf_meta_title(pdf)
        ptitle = pdf_title(meta, text)
        ptitle_n = norm_text(ptitle)
        text_n = norm_text(text)
        rec = {
            "pdf": pdf.name,
            "folder": pdf.parent.name,
            "chars": len(text),
            "pdf_title": ptitle,
            "method": "none",
            "score": 0,
            "match_doi": "",
            "match_title": "",
            "ft_status": "",
        }

        # 1. DOI match — page 1 only (avoids reference-list DOIs)
        pdoi = extract_doi(text)
        rec["pdf_doi"] = pdoi
        if pdoi and pdoi in doi_to_idx:
            j = doi_to_idx[pdoi]
            rec.update(method="doi", score=100, match_doi=m.at[j, "DOI"],
                       match_title=m.at[j, "Title"], ft_status=m.at[j, "ft_status"])
        elif ptitle_n:
            # 2a. Short candidate titles: anchored token-prefix (PDF title STARTS WITH
            #     the candidate title, e.g. "MOSOCO: a mobile assistive tool ...").
            ptoks = tokens(ptitle)
            for ctoks, j in zip(short_tokens, short_idx):
                if ctoks and ptoks[:len(ctoks)] == ctoks:
                    rec.update(method="title_short", score=100, match_doi=m.at[j, "DOI"],
                               match_title=m.at[j, "Title"], ft_status=m.at[j, "ft_status"])
                    break

            # 2b. Long candidate titles: is the candidate title present within the PDF's
            #     title blob? partial_ratio tolerates author/journal padding in the blob.
            if rec["method"] == "none":
                best = process.extractOne(
                    ptitle_n, long_titles, scorer=fuzz.partial_ratio,
                    score_cutoff=TITLE_REVIEW_FLOOR,
                )
                if best:
                    cand_n, sc, pos = best
                    j = long_idx[pos]
                    # Fragment guard: candidate is only a slice of a longer PDF title
                    # (e.g. generic "The Picture Exchange Communication System") -> review.
                    frag = fuzz.token_sort_ratio(cand_n, ptitle_n) < FRAGMENT_GUARD
                    rec.update(method="title_fragment" if frag else "title",
                               score=round(sc, 1), match_doi=m.at[j, "DOI"],
                               match_title=m.at[j, "Title"], ft_status=m.at[j, "ft_status"])

            # 2c. Last resort: match long (>=40 char) candidate titles against the raw
            #     page-1 text, for PDFs whose title blob is a banner/author junk line.
            if rec["method"] == "none" and text_n:
                best = process.extractOne(
                    text_n, ft_titles, scorer=fuzz.partial_ratio,
                    score_cutoff=FULLTEXT_REVIEW_FLOOR,
                )
                if best:
                    _, sc, pos = best
                    j = ft_idx[pos]
                    rec.update(method="fulltext", score=round(sc, 1), match_doi=m.at[j, "DOI"],
                               match_title=m.at[j, "Title"], ft_status=m.at[j, "ft_status"])

        rows.append(rec)
        if i % 25 == 0:
            print(f"  ...{i}/{len(pdfs)}")

    df = pd.DataFrame(rows)

    def verdict(r):
        if r["method"] in ("doi", "title_short"):
            return "matched"
        if r["method"] == "title" and r["score"] >= TITLE_MATCH_THRESHOLD:
            return "matched"
        if r["method"] == "fulltext" and r["score"] >= FULLTEXT_MATCH_THRESHOLD:
            return "matched"
        if r["method"] in ("title", "fulltext", "title_fragment"):
            return "review"
        return "no_match"

    df["verdict"] = df.apply(verdict, axis=1)
    df = df[["pdf", "folder", "verdict", "method", "score", "ft_status",
             "match_doi", "match_title", "pdf_title", "pdf_doi", "chars"]]
    df.to_csv(OUT, index=False)

    # Split files the downstream steps consume: confirmed (verdict==matched) feeds
    # ingest-children-pdfs.py; needs_review is for manual eyeballing.
    split_cols = ["pdf", "folder", "method", "score", "match_doi", "match_title", "ft_status"]
    matched = df[df["verdict"] == "matched"]
    matched[split_cols].to_csv(CONFIRMED, index=False)
    df[df["verdict"] == "review"][split_cols].to_csv(NEEDS_REVIEW, index=False)

    print(f"\n=== {len(df)} PDFs ===")
    print(df["verdict"].value_counts().to_string())
    print(f"\nMatched to a candidate: {len(matched)}")
    print("  of which ft_status:")
    print("   " + matched["ft_status"].value_counts().to_string().replace("\n", "\n   "))
    print(f"\nUnique candidates covered: {matched['match_doi'].replace('', pd.NA).nunique()}")
    print(f"Wrote {OUT}, {CONFIRMED}, {NEEDS_REVIEW}")


if __name__ == "__main__":
    main()

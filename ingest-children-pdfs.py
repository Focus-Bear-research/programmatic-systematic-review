"""Ingest the manually-retrieved child-review PDFs that match-child-fulltext-pdfs.py
has already identified (children/manual_matches_confirmed.csv: pdf -> candidate DOI).

For each confirmed match: copy the PDF to manual_fulltext/<fkey>.pdf and extract its
full text to full_text_snowball/<fkey>.txt (the key the review pipeline reads, per
build-children-triage.have_fulltext). Idempotent: a paper whose .txt already exists
(>=1500 chars) is skipped, so re-running after more PDFs sync only processes the new ones.

PDFs whose text layer is too thin (scanned) are reported as needs-OCR rather than
written, so they don't masquerade as full text.

Usage: poetry run python ingest-children-pdfs.py "<pdf_root_folder>"
"""
import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

sys.path.insert(0, os.getcwd())
import pandas as pd

from steps.io import normalize_doi
from steps.full_text import MIN_FULL_TEXT_CHARS

CONFIRMED = "search-results-from-database/children/manual_matches_confirmed.csv"
MASTER = "search-results-from-database/children/fulltext_review_master.csv"
DEST_PDF = "manual_fulltext"
DEST_TXT = "full_text_snowball"
DEST_PMID = "full_text"  # pipeline keys DOI-less candidates as full_text/<pmid>.txt


def fkey(doi):
    d = normalize_doi(doi) or ""
    return d.replace("/", "_").replace(":", "_")


def clean_pmid(pmid):
    s = str(pmid).strip()
    m = re.match(r"^(\d+)", s)  # CSV load can render PMIDs as "28050182.0"
    return m.group(1) if m else ""


def title_slug(title):
    return re.sub(r"[^a-z0-9]+", "_", str(title).strip().lower()).strip("_")[:80]


def pdf_text(path):
    """Full-document text via poppler pdftotext (more reliable than pypdf here)."""
    try:
        out = subprocess.run(["pdftotext", str(path), "-"],
                             capture_output=True, timeout=180)
        return out.stdout.decode("utf-8", "ignore")
    except Exception:
        return ""


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not root or not root.is_dir():
        sys.exit(f"pdf root folder not found: {root}")

    os.makedirs(DEST_PDF, exist_ok=True)
    os.makedirs(DEST_TXT, exist_ok=True)
    os.makedirs(DEST_PMID, exist_ok=True)

    conf = pd.read_csv(CONFIRMED, keep_default_na=False)
    m = pd.read_csv(MASTER, keep_default_na=False)
    pmid_by_doi = {normalize_doi(d): clean_pmid(p)
                   for d, p in zip(m["DOI"], m["PMID"]) if normalize_doi(d)}
    pmid_by_title = {str(t).strip().lower(): clean_pmid(p)
                     for t, p in zip(m["Title"], m["PMID"])}

    # filename -> full path (folder disambiguates same-numbered files if any)
    by_name = {}
    for p in root.rglob("*.pdf"):
        by_name.setdefault(p.name, []).append(p)

    def resolve_target(r):
        """(txt_path, pdf_path, kind) for a confirmed match, by DOI else PMID else slug."""
        key = fkey(r["match_doi"])
        if key:
            return (os.path.join(DEST_TXT, f"{key}.txt"),
                    os.path.join(DEST_PDF, f"{key}.pdf"), "doi")
        pmid = pmid_by_doi.get(normalize_doi(r["match_doi"])) or \
            pmid_by_title.get(str(r["match_title"]).strip().lower(), "")
        if pmid:
            return (os.path.join(DEST_PMID, f"{pmid}.txt"),
                    os.path.join(DEST_PDF, f"PMID{pmid}.pdf"), "pmid")
        slug = title_slug(r["match_title"])
        return (os.path.join(DEST_TXT, f"{slug}.txt"),
                os.path.join(DEST_PDF, f"{slug}.pdf"), "slug")

    ingested = skipped = 0
    by_kind = {"doi": 0, "pmid": 0, "slug": 0}
    needs_ocr, missing_file, unkeyed = [], [], []
    for _, r in conf.iterrows():
        txt_path, pdf_path, kind = resolve_target(r)
        if os.path.exists(txt_path) and os.path.getsize(txt_path) >= MIN_FULL_TEXT_CHARS:
            skipped += 1
            continue

        cands = by_name.get(r["pdf"], [])
        src = next((c for c in cands if c.parent.name == r["folder"]), None) or \
            (cands[0] if cands else None)
        if src is None:
            missing_file.append(r["pdf"])
            continue

        text = pdf_text(src)
        if len(text) < MIN_FULL_TEXT_CHARS:
            needs_ocr.append((r["pdf"], os.path.basename(txt_path), len(text)))
            continue

        shutil.copy(src, pdf_path)
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        ingested += 1
        by_kind[kind] += 1
        if kind == "slug":
            unkeyed.append((r["pdf"], r["match_title"]))

    print(f"confirmed matches ....... {len(conf)}")
    print(f"  newly ingested ........ {ingested}  (by DOI {by_kind['doi']}, "
          f"by PMID {by_kind['pmid']}, by title-slug {by_kind['slug']})")
    print(f"  skipped (already had) . {skipped}")
    print(f"  needs OCR (scanned) ... {len(needs_ocr)}")
    print(f"  source file missing ... {len(missing_file)}")
    if needs_ocr:
        pd.DataFrame(needs_ocr, columns=["pdf", "target", "chars"]).to_csv(
            "search-results-from-database/children/needs_ocr.csv", index=False)
        print("  -> wrote children/needs_ocr.csv")
    if unkeyed:
        print("  DOI/PMID-less (text saved by title-slug, needs an ID backfilled):")
        for pdf, t in unkeyed:
            print(f"     {pdf}: {str(t)[:60]}")
    if missing_file:
        print("  MISSING:", missing_file)


if __name__ == "__main__":
    main()

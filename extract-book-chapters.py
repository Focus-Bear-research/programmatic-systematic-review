"""Extract the target candidate chapter(s) from the whole-book/proceedings PDFs that
Sebrina saved in full, and ingest each chapter's text like a normal single paper.

Per book: find every candidate title present in the front matter (ToC) -> those are the
candidate chapters in this volume. For each, locate the chapter-opening page in the body
(title near the top of the page), then take pages up to the next chapter (Springer/LNCS
chapters open with an "Abstract" block near the top -> the next such page is the boundary),
capped at MAX_CHAPTER_PAGES. Write text to full_text_snowball/<doi>.txt (idempotent skip),
copy the page-range PDF to manual_fulltext/<doi>.pdf.

Usage: poetry run python extract-book-chapters.py "<pdf_root_folder>"
"""
import os
import re
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, os.getcwd())
import pandas as pd
from rapidfuzz import fuzz, process

from steps.io import normalize_doi
from steps.full_text import MIN_FULL_TEXT_CHARS

MASTER = "search-results-from-database/children/fulltext_review_master.csv"
MATCHES = "search-results-from-database/children/manual_fulltext_matches.csv"
DEST_TXT = "full_text_snowball"
DEST_PDF = "manual_fulltext"
REPORT = "search-results-from-database/children/book_chapter_extractions.csv"

TOC_PAGES = 40           # front matter where the ToC lives
TOC_SCORE = 95           # candidate title counts as "a chapter in this book" at/above
START_SCORE = 90         # title vs top-of-page to call it the chapter opening
TOP_CHARS = 600          # "near the top of the page" window
MAX_CHAPTER_PAGES = 18   # hard cap so a missed boundary can't swallow the next chapter
ABSTRACT_RE = re.compile(r"\babstract\b", re.I)


def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def fkey(doi):
    d = normalize_doi(doi) or ""
    return d.replace("/", "_").replace(":", "_")


def pages_of(path, first=None, last=None):
    cmd = ["pdftotext"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(path), "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=300).stdout.decode("utf-8", "ignore")
    return out.split("\f")


def find_start(pages, title_n):
    """0-based index of the chapter-opening page: title near the top, past front matter."""
    best_i, best_sc = None, START_SCORE
    for i in range(TOC_PAGES, len(pages)):
        top = norm(pages[i])[:TOP_CHARS]
        if not top:
            continue
        sc = fuzz.partial_ratio(title_n, top)
        if sc >= best_sc:
            best_i, best_sc = i, sc
            if sc == 100:
                break
    return best_i


def find_end(pages, start):
    """Next chapter boundary: first later page with 'Abstract' near the top, capped."""
    cap = min(start + MAX_CHAPTER_PAGES, len(pages))
    for i in range(start + 2, cap):
        if ABSTRACT_RE.search(norm(pages[i])[:TOP_CHARS]):
            return i, "abstract-boundary"
    return cap, "page-cap"


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not root or not root.is_dir():
        sys.exit(f"pdf root folder not found: {root}")

    m = pd.read_csv(MASTER, keep_default_na=False)
    long_titles = [(norm(t), i) for i, t in zip(m.index, m["Title"]) if len(norm(t)) >= 40]
    tlist = [t for t, _ in long_titles]
    tidx = [i for _, i in long_titles]

    matches = pd.read_csv(MATCHES, keep_default_na=False)
    books = matches[(matches["verdict"] == "no_match") & (matches["chars"].astype(int) < 1500)]
    by_name = {}
    for p in root.rglob("*.pdf"):
        by_name.setdefault(p.name, []).append(p)

    rows = []
    for _, b in books.iterrows():
        cands = by_name.get(b["pdf"], [])
        src = next((c for c in cands if c.parent.name == b["folder"]), None) or (cands[0] if cands else None)
        if src is None:
            continue
        pages = int(subprocess.run(["pdfinfo", str(src)], capture_output=True).stdout
                    .decode("utf-8", "ignore").split("Pages:")[1].split()[0]) if src else 0
        if pages < 60:  # not a book -> leave for manual (e.g. 374.pdf single paper)
            rows.append({"pdf": b["pdf"], "pages": pages, "chapter": "", "doi": "",
                         "start_page": "", "end_page": "", "boundary": "", "chars": "",
                         "status": "not-a-book (single paper) -> manual"})
            continue

        toc = norm(" ".join(pages_of(src, 1, TOC_PAGES)))
        chapters = [(tlist[pos], tidx[pos]) for _, sc, pos in
                    process.extract(toc, tlist, scorer=fuzz.partial_ratio, limit=6, score_cutoff=TOC_SCORE)]
        if not chapters:
            rows.append({"pdf": b["pdf"], "pages": pages, "chapter": "", "doi": "",
                         "start_page": "", "end_page": "", "boundary": "", "chars": "",
                         "status": "no candidate chapter in ToC -> manual"})
            continue

        allpages = pages_of(src)  # full document, once per book
        for title_n, j in chapters:
            doi = m.at[j, "DOI"]
            key = fkey(doi)
            txt_path = os.path.join(DEST_TXT, f"{key}.txt") if key else None
            status = ""
            if m.at[j, "ft_status"] == "have" or (txt_path and os.path.exists(txt_path)
                                                  and os.path.getsize(txt_path) >= MIN_FULL_TEXT_CHARS):
                status = "already have"
            start = find_start(allpages, title_n)
            if start is None:
                status = status or "chapter-opening page not found -> manual"
                rows.append({"pdf": b["pdf"], "pages": pages, "chapter": m.at[j, "Title"][:55],
                             "doi": doi, "start_page": "", "end_page": "", "boundary": "",
                             "chars": "", "status": status})
                continue
            end, boundary = find_end(allpages, start)
            text = "\f".join(allpages[start:end])
            ok = len(text) >= MIN_FULL_TEXT_CHARS and fuzz.partial_ratio(title_n, norm(text)[:TOP_CHARS]) >= START_SCORE
            if not status and ok and key:
                with open(txt_path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                try:  # best-effort PDF slice; text is what the pipeline actually reads
                    subprocess.run(["qpdf", "--empty", "--pages", str(src),
                                    f"{start+1}-{end}", "--", os.path.join(DEST_PDF, f"{key}.pdf")],
                                   capture_output=True, timeout=120)
                except Exception:
                    pass
                status = "EXTRACTED"
            elif not status:
                status = "low-confidence -> manual"
            rows.append({"pdf": b["pdf"], "pages": pages, "chapter": m.at[j, "Title"][:55],
                         "doi": doi, "start_page": start + 1, "end_page": end,
                         "boundary": boundary, "chars": len(text), "status": status})

    rep = pd.DataFrame(rows)
    rep.to_csv(REPORT, index=False)
    print(rep.to_string(index=False))
    print(f"\nEXTRACTED: {(rep['status']=='EXTRACTED').sum()}  |  "
          f"already have: {(rep['status']=='already have').sum()}  |  "
          f"manual/low-conf: {rep['status'].str.contains('manual|low').sum()}")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()

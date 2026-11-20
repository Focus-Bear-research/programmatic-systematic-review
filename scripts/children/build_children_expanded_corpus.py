"""Normalise the expanded children-search exports (PubMed/Scopus/WoS/PsycINFO) into the
all_papers.csv schema, dedupe against the existing corpus AND within the expanded set, and
stage the genuinely-new rows for screening.

The children review had been reusing an ADULT-scoped search (see search_queries.txt: every
DB query hard-required `AND (adult)` and omitted serious-game/VR/robot/neurofeedback terms).
This ingests the corrected, children-scoped expanded search a second reviewer ran.

Usage: poetry run python scripts/children/build_children_expanded_corpus.py "<expanded-search root folder>"
Writes children/expanded/new_papers.csv (new, normalised) + prints coverage.
"""

import glob
import os
import re
import sys
import warnings

from steps.paths import ALL_PAPERS_CSV

warnings.filterwarnings("ignore")
import pandas as pd

from steps.io import normalize_doi

ALL = ALL_PAPERS_CSV
OUTDIR = "search-results-from-database/children/expanded"
OUT = os.path.join(OUTDIR, "new_papers.csv")

STD = ["Title", "Abstract", "Authors", "Year", "DOI", "URL", "PMID", "Journal", "origin", "source_databases"]


def nd(d):
    return normalize_doi(d) or ""


def nt(t):
    return re.sub(r"[^a-z0-9 ]", " ", str(t).lower()).strip()


def pick(cols, *cands):
    """First column whose lowercased name matches any candidate (exact, then substring)."""
    low = {c.lower().strip(): c for c in cols}
    for cand in cands:
        if cand in low:
            return low[cand]
    for cand in cands:
        for lc, orig in low.items():
            if cand in lc:
                return orig
    return None


def load_source(path):
    eng = "openpyxl" if path.lower().endswith("xlsx") else None
    df = pd.read_excel(path, engine=eng).fillna("")
    c = df.columns
    db = os.path.basename(os.path.dirname(path))  # PubMed / Scopus / Web of Science / PsycInfo
    m = pd.DataFrame()
    m["Title"] = df[pick(c, "article title", "title")] if pick(c, "article title", "title") else ""
    ac = pick(c, "abstract")
    m["Abstract"] = df[ac] if ac else ""
    au = pick(c, "authors", "author full names", "author full name")
    m["Authors"] = df[au] if au else ""
    yc = pick(c, "year", "publication year", "pubyear")
    m["Year"] = df[yc] if yc else ""
    dc = pick(c, "doi", "digitalobjectidentifier")
    m["DOI"] = df[dc] if dc else ""
    uc = pick(c, "url", "link")
    m["URL"] = df[uc] if uc else ""
    pc = pick(c, "pmid")
    m["PMID"] = df[pc] if pc else ""
    jc = pick(c, "journal", "source title", "journal/book", "publication title")
    m["Journal"] = df[jc] if jc else ""
    m["origin"] = "database_search_expanded"
    m["source_databases"] = db
    return m


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else None
    if not root or not os.path.isdir(root):
        sys.exit(f"expanded-search root folder not found: {root}")
    os.makedirs(OUTDIR, exist_ok=True)

    files = [
        p
        for p in glob.glob(os.path.join(root, "**", "*"), recursive=True)
        if p.lower().endswith((".xls", ".xlsx"))
    ]
    frames = []
    for p in sorted(files):
        m = load_source(p)
        print(f"  {len(m):5} rows  {os.path.relpath(p, root)}")
        frames.append(m)
    exp = pd.concat(frames, ignore_index=True).fillna("")
    exp["_nd"] = exp["DOI"].map(nd)
    exp["_nt"] = exp["Title"].map(nt)
    print(f"\nexpanded raw records: {len(exp)}")

    # existing corpus keys
    corpus = pd.read_csv(ALL, dtype=str, keep_default_na=False)
    seen_doi = {nd(d) for d in corpus["DOI"] if nd(d)}
    seen_t = {nt(t) for t in corpus["Title"] if str(t).strip()}

    # dedupe within expanded (prefer a row that has an abstract) + against corpus
    exp["_hasabs"] = exp["Abstract"].str.len() >= 20
    exp = exp.sort_values("_hasabs", ascending=False)
    new, kept_doi, kept_t = [], set(), set()
    for _, r in exp.iterrows():
        d, t = r["_nd"], r["_nt"]
        if d and d in seen_doi:
            continue
        if not d and t and t in seen_t:
            continue
        if d and d in kept_doi:
            continue
        if not d and t in kept_t:
            continue
        if d:
            kept_doi.add(d)
        if t:
            kept_t.add(t)
        new.append(r)
    newdf = pd.DataFrame(new)[STD].reset_index(drop=True)
    newdf.to_csv(OUT, index=False)

    print(f"\nunique-in-expanded, NEW to corpus: {len(newdf)}")
    print(f"  with abstract (screenable now): {(newdf['Abstract'].str.len() >= 20).sum()}")
    print(f"  NO abstract (need fetch):       {(newdf['Abstract'].str.len() < 20).sum()}")
    print("  by source database:")
    print("   " + newdf["source_databases"].value_counts().to_string().replace("\n", "\n   "))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()

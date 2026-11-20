"""Ingest manually-retrieved PDFs/HTML: match each file to its candidate (by DOI
filename variants, or author/title fallback), copy into manual_fulltext/ under the
canonical name, and extract text to full_text_snowball/<sanitised-doi>.txt.
"""

import os
import re
import shutil

import pandas as pd

from steps.config import require_env
from steps.full_text import _html_to_text, _pdf_to_text
from steps.io import normalize_doi
from steps.paths import ADULTS_FULLTEXT_TO_RETRIEVE_CSV, FULL_TEXT_SNOWBALL_DIR, MANUAL_FULLTEXT_DIR

SRC = require_env("MANUAL_PDF_DIR", "folder holding the manually downloaded PDFs / HTML files to ingest")
DEST = MANUAL_FULLTEXT_DIR
TEXT = FULL_TEXT_SNOWBALL_DIR
os.makedirs(DEST, exist_ok=True)
os.makedirs(TEXT, exist_ok=True)


def nd(d):
    return normalize_doi(d) or ""


def fid(doi):
    return nd(doi).replace("/", "_").replace(":", "_")


df = pd.read_csv(ADULTS_FULLTEXT_TO_RETRIEVE_CSV, dtype=str).fillna("")
# variant -> row index
vmap = {}
for i, r in df.iterrows():
    doi = nd(r["DOI"])
    for k in {r["save_as"][:-4], doi, doi.replace("/", "_"), doi.replace("/", ":")}:
        if k:
            vmap[k.lower()] = i

files = [f for f in os.listdir(SRC) if f.lower().endswith((".pdf", ".html", ".htm"))]
matched, unmatched, extracted, failed = 0, [], 0, []
for fn in files:
    stem = os.path.splitext(fn)[0].lower()
    idx = vmap.get(stem)
    if idx is None:  # author/title fallback (e.g. thesis named by author)
        tok = re.findall(r"[a-z]{4,}", stem)
        for i, r in df.iterrows():
            blob = (r["Authors"] + " " + r["Title"]).lower()
            if any(t in blob for t in tok):
                idx = i
                break
    if idx is None:
        unmatched.append(fn)
        continue
    matched += 1
    doi = nd(df.at[idx, "DOI"])
    fkey = fid(doi) if doi else df.at[idx, "save_as"][:-4]
    shutil.copy(os.path.join(SRC, fn), os.path.join(DEST, f"{fkey}{os.path.splitext(fn)[1]}"))
    data = open(os.path.join(SRC, fn), "rb").read()
    text = (
        _pdf_to_text(data) if fn.lower().endswith(".pdf") else _html_to_text(data.decode("utf-8", "ignore"))
    )
    if text:
        open(os.path.join(TEXT, f"{fkey}.txt"), "w", encoding="utf-8").write(text)
        extracted += 1
    else:
        failed.append(fn)

print(f"files: {len(files)} | matched: {matched} | unmatched: {len(unmatched)}")
print(f"text extracted: {extracted} | extraction failed (scanned/no text?): {len(failed)}")
if unmatched:
    print("UNMATCHED:", unmatched)
if failed:
    print("NO TEXT:", failed)

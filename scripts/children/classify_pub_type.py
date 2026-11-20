"""Classify each children candidate's PUBLICATION TYPE (journal article vs conference
proceedings vs book chapter) so non-peer-reviewed grey literature can be excluded.

Authoritative source: Crossref `message.type` per DOI (journal-article / proceedings-article
/ book-chapter / book / posted-content ...). For DOI-less candidates, fall back to a venue
heuristic on the Journal/Source string. Writes pub_type + pub_peer_reviewed into the master.

Usage: poetry run python scripts/children/classify_pub_type.py [workers]
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from steps.config import contact_email
from steps.io import normalize_doi
from steps.paths import CHILDREN_FULLTEXT_MASTER_CSV

MASTER = CHILDREN_FULLTEXT_MASTER_CSV
CACHE = "search-results-from-database/children/expanded/crossref_type.json"
MAILTO = contact_email()

# Crossref types that are NOT peer-reviewed journal articles for our purposes.
EXCLUDE_TYPES = {
    "proceedings-article",
    "proceedings",
    "book-chapter",
    "book",
    "book-part",
    "book-section",
    "monograph",
    "edited-book",
    "reference-entry",
    "report",
    "dataset",
    "posted-content",
    "dissertation",
}
KEEP_TYPES = {"journal-article", "journal-issue", "review-article"}

CONF_RE = re.compile(
    r"conference|proceedings|symposium|workshop|\bLNCS\b|lecture notes|"
    r"communications in computer|advances in intelligent|CCIS|\bIEEE\b.*(conf|symp)",
    re.I,
)
BOOK_RE = re.compile(r"\bbook\b|book series|handbook|\bchapter\b|springer series|studies in", re.I)


def nd(d):
    return normalize_doi(d) or ""


def crossref_type(doi, sess):
    try:
        r = sess.get(f"https://api.crossref.org/works/{doi}", params={"mailto": MAILTO}, timeout=20)
        if r.status_code == 200:
            return (r.json().get("message", {}) or {}).get("type", "") or ""
    except Exception:
        pass
    return ""


def venue_guess(journal):
    if CONF_RE.search(journal):
        return "proceedings-article"
    if BOOK_RE.search(journal):
        return "book-chapter"
    return ""


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    m = pd.read_csv(MASTER, keep_default_na=False)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    dois = [nd(d) for d in m["DOI"] if nd(d) and nd(d) not in cache]
    dois = sorted(set(dois))
    print(f"candidates={len(m)} | Crossref lookups needed={len(dois)} (cached={len(cache)})")
    sess = requests.Session()
    sess.headers.update({"User-Agent": f"childreview/1.0 (mailto:{MAILTO})"})
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(crossref_type, d, sess): d for d in dois}
        for f in as_completed(futs):
            cache[futs[f]] = f.result()
            done += 1
            if done % 200 == 0:
                print(f"  ...{done}/{len(dois)}")
                json.dump(cache, open(CACHE, "w"))
    json.dump(cache, open(CACHE, "w"))

    types, peer = [], []
    for _, r in m.iterrows():
        d = nd(r["DOI"])
        t = cache.get(d, "") if d else ""
        if not t:
            t = venue_guess(str(r.get("Journal", "")))
        types.append(t)
        pr = "yes" if t in KEEP_TYPES else ("no" if t in EXCLUDE_TYPES else "unknown")
        peer.append(pr)
    m["pub_type"] = types
    m["pub_peer_reviewed"] = peer
    m.to_csv(MASTER, index=False)

    from collections import Counter

    print("\npub_type distribution:")
    for k, v in Counter(types).most_common():
        print(f"  {v:5}  {k or '(blank)'}")
    print("\npub_peer_reviewed:", dict(Counter(peer)))
    excl = int((pd.Series(peer) == "no").sum())
    print(
        f"\nwould EXCLUDE (conference/book/grey): {excl}  | keep(journal): "
        f"{int((pd.Series(peer)=='yes').sum())}  | unknown: {int((pd.Series(peer)=='unknown').sum())}"
    )


if __name__ == "__main__":
    main()

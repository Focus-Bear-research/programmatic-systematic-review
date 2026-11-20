"""Semantic Scholar bulk-search client shared by the database-search scripts.

The bulk endpoint supports boolean query syntax (the relevance ``/paper/search``
endpoint does not) and paginates with a continuation token, returning up to
1000 records per page. Matching is against title and abstract only.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import requests

BULK_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
API_KEY_ENV_VARS = ("SEMANTIC_SCHOLAR_API_KEY", "S2_API_KEY")

DEFAULT_FIELDS = "title,abstract,authors,year,url,venue,externalIds"

HTTP_OK = 200
HTTP_UNAUTHORISED = (401, 403)
HTTP_RATE_LIMITED = 429
MAX_ATTEMPTS_PER_PAGE = 8
MAX_BACKOFF_SEC = 60
REQUEST_TIMEOUT_SEC = 60
# Unauthenticated requests share one global rate-limit pool, so pause longer.
PAUSE_WITH_KEY_SEC = 1
PAUSE_WITHOUT_KEY_SEC = 2


class SemanticScholarError(RuntimeError):
    """The API returned an error that retrying will not fix."""


def api_key_from_env() -> str | None:
    for name in API_KEY_ENV_VARS:
        value = os.getenv(name)
        if value:
            return value
    return None


class BulkSearchClient:
    """Pages through bulk-search results, backing off when rate limited.

    If the API key is rejected (401/403) the client drops it and continues
    unauthenticated for the rest of the run rather than failing.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        self.total_matches: int | None = None

    def search(
        self, query: str, fields: str = DEFAULT_FIELDS, max_results: int | None = None
    ) -> Iterator[dict]:
        """Yield paper records for ``query`` until exhausted or ``max_results``."""
        self.total_matches = None
        yielded = 0
        token: str | None = None
        while True:
            page = self._fetch_page(query, fields, token)
            if self.total_matches is None:
                self.total_matches = page.get("total")
            papers = page.get("data") or []
            for paper in papers:
                if max_results is not None and yielded >= max_results:
                    return
                yield paper
                yielded += 1
            token = page.get("token")
            if not token or not papers:
                return
            time.sleep(self._pause_seconds())

    def _pause_seconds(self) -> int:
        return PAUSE_WITH_KEY_SEC if self._api_key else PAUSE_WITHOUT_KEY_SEC

    def _fetch_page(self, query: str, fields: str, token: str | None) -> dict:
        params = {"query": query, "fields": fields}
        if token:
            params["token"] = token

        for attempt in range(MAX_ATTEMPTS_PER_PAGE):
            headers = {"x-api-key": self._api_key} if self._api_key else {}
            response = self._session.get(
                BULK_SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT_SEC
            )
            if response.status_code == HTTP_OK:
                return response.json()
            if response.status_code in HTTP_UNAUTHORISED and self._api_key:
                print(
                    f"Semantic Scholar API key rejected (HTTP {response.status_code}); "
                    "continuing unauthenticated."
                )
                self._api_key = None
                continue
            if response.status_code == HTTP_RATE_LIMITED or response.status_code >= 500:
                wait = min(2**attempt, MAX_BACKOFF_SEC)
                print(f"Semantic Scholar HTTP {response.status_code}; retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise SemanticScholarError(f"HTTP {response.status_code}: {response.text[:200]}")

        raise SemanticScholarError(f"Gave up after {MAX_ATTEMPTS_PER_PAGE} attempts for query: {query[:80]}")

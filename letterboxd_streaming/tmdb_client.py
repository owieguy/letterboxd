"""Thin wrapper around the subset of the TMDB v3 API this project needs:
searching for a movie by title/year (fallback matching only), fetching a
movie's basic details (for its poster), and fetching its watch/providers
data (the actual streaming-availability info, sourced from JustWatch).

Docs: https://developer.themoviedb.org/reference/intro/getting-started
"""
from __future__ import annotations

import requests

from .util import retry_request

API_BASE = "https://api.themoviedb.org/3"
REQUEST_TIMEOUT = 20
POSTER_BASE = "https://image.tmdb.org/t/p/w200"


class TMDBClient:
    def __init__(self, api_key: str, session: requests.Session | None = None):
        self.api_key = api_key
        self.session = session or requests.Session()

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["api_key"] = self.api_key

        def do() -> dict:
            resp = self.session.get(f"{API_BASE}{path}", params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()

        return retry_request(do)

    def search_movie(self, title: str, year: int | None = None) -> dict | None:
        """Fallback lookup used only when a film's Letterboxd page has no
        linked TMDB id. Best-effort title match, optionally narrowed by
        year; returns the top result or None."""
        params = {"query": title}
        if year:
            params["year"] = year
        data = self._get("/search/movie", params)
        results = data.get("results") or []
        if not results and year:
            # retry without the year filter in case it was slightly off
            data = self._get("/search/movie", {"query": title})
            results = data.get("results") or []
        return results[0] if results else None

    def get_movie(self, tmdb_id: int) -> dict:
        return self._get(f"/movie/{tmdb_id}")

    def get_watch_providers(self, tmdb_id: int) -> dict:
        """Returns the raw `results` mapping of country code -> provider
        categories (flatrate/free/ads/rent/buy), as documented at
        https://developer.themoviedb.org/reference/movie-watch-providers
        """
        data = self._get(f"/movie/{tmdb_id}/watch/providers")
        return data.get("results", {})


def poster_url(poster_path: str | None) -> str | None:
    return f"{POSTER_BASE}{poster_path}" if poster_path else None

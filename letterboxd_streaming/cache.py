"""A small on-disk JSON cache so re-running the script doesn't re-scrape
every film's Letterboxd page or re-hit TMDB unnecessarily.

Two sections:
  - film_ids:  slug -> {tmdb_id, poster_path}      (cached indefinitely --
    a film's identity/poster doesn't meaningfully change)
  - providers: tmdb_id -> {checked_at, country, results}   (cached with a
    time-to-live, since streaming availability changes over time)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {"film_ids": {}, "providers": {}, "lists": {}}
    try:
        data = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"film_ids": {}, "providers": {}, "lists": {}}
    data.setdefault("film_ids", {})
    data.setdefault("providers", {})
    data.setdefault("lists", {})
    return data


def save(cache_path: Path, data: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2, sort_keys=True))


def get_film_id_entry(cache: dict, slug: str) -> dict | None:
    return cache["film_ids"].get(slug)


def set_film_id_entry(cache: dict, slug: str, tmdb_id: int, poster_path: str | None) -> None:
    cache["film_ids"][slug] = {"tmdb_id": tmdb_id, "poster_path": poster_path}


def get_provider_entry(cache: dict, tmdb_id: int, country: str, max_age_hours: float) -> dict | None:
    entry = cache["providers"].get(str(tmdb_id))
    if not entry or entry.get("country") != country:
        return None
    checked_at = datetime.fromisoformat(entry["checked_at"])
    age_hours = (datetime.now(timezone.utc) - checked_at).total_seconds() / 3600
    if age_hours > max_age_hours:
        return None
    return entry["results"]


def set_provider_entry(cache: dict, tmdb_id: int, country: str, results: dict) -> None:
    cache["providers"][str(tmdb_id)] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "country": country,
        "results": results,
    }


def get_lists(cache: dict) -> dict[str, dict]:
    """The registry of every list this script has ever generated a page
    for -- keyed by slug -- so the landing page can link to lists that
    weren't part of *this* run (e.g. `--list-url` was used for just one)."""
    return cache["lists"]


def set_list_entry(cache: dict, slug: str, **fields: Any) -> None:
    cache["lists"][slug] = fields

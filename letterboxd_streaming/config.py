"""Configuration loading for the letterboxd-streaming-checker script.

Reads settings from a `.env` file (via python-dotenv) with environment
variables and CLI arguments able to override them.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The lists checked by default when .env doesn't set LIST_URLS.
DEFAULT_LIST_URLS = [
    "https://boxd.it/il1fQ",  # Watch with Ash
    "https://boxd.it/Skwgs",  # Watch On My Own
    "https://boxd.it/8HjM",  # Letterboxd's Top 500 Films
]
DEFAULT_COUNTRY = "US"
# GitHub Actions' own "Run workflow" page for the update workflow -- linked
# from a "Refresh data" button on generated pages so a viewer can trigger an
# on-demand re-check without waiting for the weekly schedule. There's no
# backend to wire up an in-page one-click refresh without exposing a
# write-capable GitHub token in this public page's client-side source, which
# isn't safe to do -- this deep-links to GitHub's own dispatch UI instead,
# where the signed-in repo owner clicks "Run workflow" themselves.
DEFAULT_REFRESH_WORKFLOW_URL = "https://github.com/owieguy/letterboxd/actions/workflows/update.yml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_CACHE_PATH = PROJECT_ROOT / "cache" / "data.json"
DEFAULT_PROVIDER_MAX_AGE_HOURS = 24


@dataclass
class Config:
    tmdb_api_key: str
    list_urls: list[str]
    # Set only when --list-url and --output were both passed explicitly --
    # write that one list straight to this path instead of an auto-named
    # file under output_dir, and skip regenerating the landing page.
    single_output_path: Path | None
    country: str
    output_dir: Path
    cache_path: Path
    provider_max_age_hours: float
    force_refresh: bool
    refresh_workflow_url: str | None


def _parse_list_urls(raw: str) -> list[str]:
    parts = [p.strip() for chunk in raw.splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]


def load_config(
    *,
    list_url: str | None = None,
    country: str | None = None,
    output_path: str | None = None,
    output_dir: str | None = None,
    cache_path: str | None = None,
    provider_max_age_hours: float | None = None,
    force_refresh: bool = False,
) -> Config:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "Missing TMDB_API_KEY.\n"
            "  1. Get a free key at https://www.themoviedb.org/settings/api\n"
            "  2. Copy .env.example to .env in this project folder\n"
            "  3. Set TMDB_API_KEY=<your key> in .env and re-run.\n"
        )

    if list_url:
        list_urls = [list_url]
    else:
        raw = os.environ.get("LIST_URLS") or os.environ.get("LIST_URL")
        list_urls = _parse_list_urls(raw) if raw else list(DEFAULT_LIST_URLS)

    return Config(
        tmdb_api_key=api_key,
        list_urls=list_urls,
        single_output_path=Path(output_path) if (output_path and list_url) else None,
        country=(country or os.environ.get("COUNTRY", DEFAULT_COUNTRY)).upper(),
        output_dir=Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR,
        cache_path=Path(cache_path) if cache_path else DEFAULT_CACHE_PATH,
        provider_max_age_hours=(
            provider_max_age_hours
            if provider_max_age_hours is not None
            else float(os.environ.get("PROVIDER_MAX_AGE_HOURS", DEFAULT_PROVIDER_MAX_AGE_HOURS))
        ),
        force_refresh=force_refresh,
        # Empty string (REFRESH_WORKFLOW_URL=) explicitly opts out and hides
        # the button -- e.g. for a fork pointed at a repo with no such
        # workflow.
        refresh_workflow_url=(
            os.environ["REFRESH_WORKFLOW_URL"].strip() or None
            if "REFRESH_WORKFLOW_URL" in os.environ
            else DEFAULT_REFRESH_WORKFLOW_URL
        ),
    )

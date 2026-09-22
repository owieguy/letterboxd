#!/usr/bin/env python3
"""Pulls one or more public Letterboxd lists, checks which of a fixed set of
streaming services carry each film at no extra cost (subscription-included,
free, or ad-supported -- rent/buy is ignored), and renders the result as a
static HTML page per list, plus a landing page linking to all of them.

Usage:
    python main.py                     # process every list configured in .env
    python main.py --refresh           # force re-checking streaming availability
    python main.py --list-url <url>    # process just this one list
    python main.py --list-url <url> --output out.html   # ...to this exact file
    python main.py --country GB        # check a different region

Re-run this any time to pick up the current state of each list and refresh
availability. See README.md for one-time setup (TMDB API key) and how to add
or remove lists.
"""
from __future__ import annotations

import argparse
import sys
import time

import certifi
import requests

from letterboxd_streaming import cache as cache_mod
from letterboxd_streaming import letterboxd_client, render
from letterboxd_streaming.config import load_config
from letterboxd_streaming.providers import SERVICE_DEFINITIONS, classify, search_url
from letterboxd_streaming.tmdb_client import TMDBClient, poster_url
from letterboxd_streaming.util import slugify

# Be polite to both Letterboxd and TMDB -- these are unauthenticated page
# scrapes / low-volume API calls, not bulk traffic.
REQUEST_DELAY_SECONDS = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-url", help="Process just this one Letterboxd list (overrides .env LIST_URLS)")
    parser.add_argument("--country", help="ISO country code for streaming availability, e.g. US, GB (overrides .env COUNTRY)")
    parser.add_argument("--output", help="Exact path to write the HTML page to (only with --list-url)")
    parser.add_argument("--output-dir", help="Directory for auto-named per-list pages + the landing page (default: output/)")
    parser.add_argument("--refresh", action="store_true", help="Bypass the streaming-availability cache and re-check every film")
    parser.add_argument("--max-age-hours", type=float, help="How long cached availability is considered fresh (default: 24)")
    return parser.parse_args()


def process_list(list_url: str, config, session: requests.Session, tmdb: TMDBClient, cache: dict) -> dict:
    """Runs the full fetch/match/classify pipeline for one list. Returns a
    summary dict; also mutates `cache` in place (saved by the caller)."""
    print(f"Fetching list: {list_url}")
    list_title, films = letterboxd_client.fetch_list_films(list_url, session=session)
    print(f"  -> '{list_title}': {len(films)} films")

    rendered_films = []
    unresolved = 0

    try:
        for i, film in enumerate(films, start=1):
            print(f"[{i}/{len(films)}] {film.title} ({film.year or '?'})", end=" ", flush=True)

            entry = cache_mod.get_film_id_entry(cache, film.slug)
            if entry is None:
                tmdb_id = letterboxd_client.resolve_tmdb_id(film.slug, session=session)
                time.sleep(REQUEST_DELAY_SECONDS)
                poster_path = None
                if tmdb_id is not None:
                    try:
                        details = tmdb.get_movie(tmdb_id)
                        poster_path = details.get("poster_path")
                    except requests.HTTPError:
                        pass
                if tmdb_id is not None:
                    cache_mod.set_film_id_entry(cache, film.slug, tmdb_id, poster_path)
                    entry = cache_mod.get_film_id_entry(cache, film.slug)

            if entry is None:
                print("-- no TMDB match, skipping availability check")
                unresolved += 1
                services = {key: {"label": label, "available": False, "matched": []} for key, label, _ in SERVICE_DEFINITIONS}
                rendered_films.append(
                    {
                        "title": film.title,
                        "year": film.year,
                        "letterboxd_url": film.letterboxd_url,
                        "poster_url": None,
                        "services": services,
                        "any_free": False,
                    }
                )
                continue

            tmdb_id = entry["tmdb_id"]
            results = None if config.force_refresh else cache_mod.get_provider_entry(
                cache, tmdb_id, config.country, config.provider_max_age_hours
            )
            if results is None:
                try:
                    results = tmdb.get_watch_providers(tmdb_id)
                except requests.HTTPError as e:
                    if e.response is not None and e.response.status_code == 401:
                        sys.exit(
                            "\nTMDB rejected the API key (401 Unauthorized). Double-check "
                            "TMDB_API_KEY in .env -- see README.md for how to get one."
                        )
                    raise
                cache_mod.set_provider_entry(cache, tmdb_id, config.country, results)
                time.sleep(REQUEST_DELAY_SECONDS)

            services, _link = classify(results, config.country)
            for key, svc in services.items():
                if svc["available"]:
                    svc["url"] = search_url(key, svc["label"], svc["matched"], film.title)
            any_free = any(s["available"] for s in services.values())
            print("-> " + (", ".join(k for k, s in services.items() if s["available"]) or "not free anywhere"))

            rendered_films.append(
                {
                    "title": film.title,
                    "year": film.year,
                    "letterboxd_url": film.letterboxd_url,
                    "poster_url": poster_url(entry.get("poster_path")),
                    "services": services,
                    "any_free": any_free,
                }
            )
    finally:
        # Persist whatever was resolved/checked even if a later film's
        # lookup fails partway through, so a re-run doesn't start from zero.
        cache_mod.save(config.cache_path, cache)

    return {
        "list_title": list_title,
        "list_url": list_url,
        "films": rendered_films,
        "unresolved_count": unresolved,
        "total_films": len(rendered_films),
        "free_count": sum(1 for f in rendered_films if f["any_free"]),
    }


def main() -> None:
    args = parse_args()
    config = load_config(
        list_url=args.list_url,
        country=args.country,
        output_path=args.output,
        output_dir=args.output_dir,
        provider_max_age_hours=args.max_age_hours,
        force_refresh=args.refresh,
    )

    session = requests.Session()
    # Some environments (notably python.org macOS builds without
    # "Install Certificates.command" run) don't wire up requests' default
    # CA bundle correctly -- pin it explicitly to certifi's for robustness.
    session.verify = certifi.where()
    tmdb = TMDBClient(config.tmdb_api_key, session=session)
    cache = cache_mod.load(config.cache_path)

    used_slugs: set[str] = set(cache_mod.get_lists(cache).keys())
    multi_mode = config.single_output_path is None

    for list_url in config.list_urls:
        summary = process_list(list_url, config, session, tmdb, cache)

        if config.single_output_path is not None:
            out_path = config.single_output_path
            slug = None
        else:
            base_slug = slugify(summary["list_title"])
            slug = base_slug
            n = 2
            # Two different lists whose titles slugify the same shouldn't
            # clobber each other's page.
            existing = cache_mod.get_lists(cache)
            while slug in used_slugs and existing.get(slug, {}).get("url") != list_url:
                slug = f"{base_slug}-{n}"
                n += 1
            used_slugs.add(slug)
            out_path = config.output_dir / f"{slug}.html"

        render.render_page(
            list_title=summary["list_title"],
            list_url=list_url,
            country=config.country,
            films=summary["films"],
            unresolved_count=summary["unresolved_count"],
            output_path=out_path,
            back_to_index="index.html" if multi_mode else None,
        )

        if slug is not None:
            cache_mod.set_list_entry(
                cache,
                slug,
                title=summary["list_title"],
                url=list_url,
                output_file=out_path.name,
                film_count=summary["total_films"],
                free_count=summary["free_count"],
                unresolved_count=summary["unresolved_count"],
                country=config.country,
            )
            cache_mod.save(config.cache_path, cache)

        print()
        print(f"Done: {summary['free_count']}/{summary['total_films']} films are free somewhere in {config.country}.")
        if summary["unresolved_count"]:
            print(f"({summary['unresolved_count']} film(s) could not be matched to a TMDB entry.)")
        print(f"Page written to: {out_path}")
        print()

    if multi_mode:
        index_path = config.output_dir / "index.html"
        render.render_landing(lists=cache_mod.get_lists(cache), country=config.country, output_path=index_path)
        print(f"Landing page written to: {index_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")

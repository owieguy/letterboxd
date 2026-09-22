"""Fetches film entries from a public Letterboxd list, and resolves each
film's TMDB id by scraping its Letterboxd film page (Letterboxd has no
public API, so this is done via straightforward HTML parsing of public
pages only -- no login, no private data).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .util import retry_request

USER_AGENT = (
    "Mozilla/5.0 (compatible; letterboxd-streaming-checker/1.0; "
    "+https://github.com/) personal-use script"
)
REQUEST_TIMEOUT = 20
MAX_LIST_PAGES = 50  # safety cap in case pagination detection ever misbehaves

_NAME_YEAR_RE = re.compile(r"^(?P<title>.*?)\s*\((?P<year>\d{4})\)\s*$")


@dataclass
class ListFilm:
    slug: str
    title: str
    year: int | None
    letterboxd_url: str


def _get(url: str, session: requests.Session) -> requests.Response:
    def do() -> requests.Response:
        resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp

    return retry_request(do)


def _normalize_list_url(list_url: str) -> str:
    # Following a boxd.it short link and any trailing redirects is handled
    # transparently by `requests`; we just need a clean base with no query
    # string and a trailing slash for page-number suffixing.
    url = list_url.split("?", 1)[0].rstrip("/")
    # "/detail" is just a Letterboxd view mode (bigger per-film metadata) and
    # 403s for non-browser requests; the plain list view has everything we
    # scrape, so drop the suffix if someone pastes a /detail/ link.
    if url.lower().endswith("/detail"):
        url = url[: -len("/detail")]
    return url + "/"


def fetch_list_films(list_url: str, session: requests.Session | None = None) -> tuple[str, list[ListFilm]]:
    """Returns (resolved_list_title, films) for every film on the list,
    following pagination until an empty page is hit."""
    session = session or requests.Session()
    requested_base = _normalize_list_url(list_url)
    resolved_base: str | None = None  # set from page 1's post-redirect URL

    films: list[ListFilm] = []
    seen_slugs: set[str] = set()
    list_title: str | None = None

    for page in range(1, MAX_LIST_PAGES + 1):
        if page == 1:
            page_url = requested_base
        else:
            # boxd.it and similar short links only redirect their exact
            # path, not /page/N/ suffixes -- so page 2+ must be built from
            # wherever page 1 actually landed, not the original input URL.
            page_url = f"{resolved_base}page/{page}/"
        resp = _get(page_url, session)
        if page == 1:
            resolved_base = _normalize_list_url(resp.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        if list_title is None:
            title_tag = soup.select_one("h1.title-1, meta[property='og:title']")
            if title_tag is not None:
                list_title = title_tag.get("content") if title_tag.name == "meta" else title_tag.get_text(strip=True)

        entries = soup.select("li.posteritem [data-item-slug]")
        if not entries:
            if page == 1:
                raise RuntimeError(
                    f"No films found at {page_url} -- is this a valid public Letterboxd list URL?"
                )
            break  # ran off the end of pagination

        for entry in entries:
            slug = entry.get("data-item-slug")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            name_year = entry.get("data-item-name", "")
            match = _NAME_YEAR_RE.match(name_year)
            title = match.group("title") if match else name_year
            year = int(match.group("year")) if match else None

            link = entry.get("data-item-link") or f"/film/{slug}/"
            films.append(
                ListFilm(
                    slug=slug,
                    title=title or slug,
                    year=year,
                    letterboxd_url=f"https://letterboxd.com{link}",
                )
            )

    return list_title or list_url, films


def resolve_tmdb_id(slug: str, session: requests.Session | None = None) -> int | None:
    """Scrapes a film's Letterboxd page for its linked TMDB id. Returns
    None if no TMDB link is present (rare, e.g. very obscure titles)."""
    session = session or requests.Session()
    url = f"https://letterboxd.com/film/{slug}/"
    resp = _get(url, session)
    soup = BeautifulSoup(resp.text, "html.parser")

    link = soup.select_one('a[data-track-action="TMDB"]')
    if link is None or not link.get("href"):
        return None

    match = re.search(r"themoviedb\.org/movie/(\d+)", link["href"])
    return int(match.group(1)) if match else None

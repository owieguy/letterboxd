"""Maps TMDB/JustWatch provider names onto the specific set of services the
user cares about, and decides whether a film is watchable on each at no
extra cost (subscription-included, free-with-ads, or fully free) versus
only available to rent/buy (which we ignore).
"""
from __future__ import annotations

from urllib.parse import quote_plus

# Order here is the display order in the generated page.
# (key, display label, substrings matched against TMDB's lowercased provider_name)
SERVICE_DEFINITIONS: list[tuple[str, str, list[str]]] = [
    ("netflix", "Netflix", ["netflix"]),
    ("prime", "Prime Video", ["amazon prime video", "prime video"]),
    ("disney", "Disney+", ["disney plus", "disney+"]),
    ("hulu", "Hulu", ["hulu"]),
    ("peacock", "Peacock", ["peacock"]),
    ("appletv", "Apple TV+", ["apple tv"]),
    ("hbo", "HBO / Max", ["hbo", "max"]),
    ("paramount", "Paramount+", ["paramount"]),
    (
        "free",
        "Free (ads)",
        ["pluto tv", "tubi", "freevee", "roku channel", "crackle", "plex"],
    ),
]

# Categories that mean "watchable without paying extra" (as opposed to
# `rent`/`buy`, which we deliberately ignore).
INCLUDED_CATEGORIES = ("flatrate", "free", "ads")


def classify(provider_results: dict, country: str) -> tuple[dict[str, dict], str | None]:
    """provider_results: the raw country->categories mapping from
    TMDBClient.get_watch_providers().

    Returns (services, justwatch_link) where `services` maps each service
    key from SERVICE_DEFINITIONS to {"label", "available", "matched"}.
    """
    region = provider_results.get(country, {})

    included_entries = []
    for category in INCLUDED_CATEGORIES:
        included_entries.extend(region.get(category) or [])

    provider_names = [entry.get("provider_name", "") for entry in included_entries]
    lowered = [(name, name.lower()) for name in provider_names if name]

    services: dict[str, dict] = {}
    for key, label, substrings in SERVICE_DEFINITIONS:
        matched = sorted({name for name, low in lowered if any(s in low for s in substrings)})
        services[key] = {"label": label, "available": bool(matched), "matched": matched}

    return services, region.get("link")


# ---------------------------------------------------------------------------
# Direct-to-service links.
#
# TMDB's free API only gives one aggregate "watch" link per film (a JustWatch
# page listing every provider); it doesn't expose a per-provider deep link.
# These are best-effort search-page URLs for each service's own site, so a
# badge click lands you on that service already searching for the title --
# usually the title is the first/only result, but it's a search page, not a
# guaranteed exact-match "play" link, and services can change these patterns
# without notice.
# ---------------------------------------------------------------------------

SERVICE_SEARCH_URL_TEMPLATES: dict[str, str] = {
    "netflix": "https://www.netflix.com/search?q={q}",
    "prime": "https://www.amazon.com/s?k={q}&i=instant-video",
    "disney": "https://www.disneyplus.com/search/{q}",
    "hulu": "https://www.hulu.com/search?q={q}",
    "peacock": "https://www.peacocktv.com/search?q={q}",
    "appletv": "https://tv.apple.com/search?term={q}",
    "hbo": "https://www.max.com/search?q={q}",
    "paramount": "https://www.paramountplus.com/search?query={q}",
}

# The "free" bucket is an umbrella over several distinct sites -- route by
# whichever specific platform actually matched (checked in this order).
FREE_PLATFORM_SEARCH_URL_TEMPLATES: list[tuple[str, str]] = [
    ("tubi", "https://tubitv.com/search/{q}"),
    ("pluto", "https://pluto.tv/search?q={q}"),
    ("roku", "https://therokuchannel.roku.com/search?q={q}"),
    ("plex", "https://watch.plex.tv/search?query={q}"),
    ("crackle", "https://www.crackle.com/search?q={q}"),
    ("freevee", "https://www.amazon.com/s?k={q}&i=instant-video"),
]


def search_url(service_key: str, service_label: str, matched_names: list[str], title: str) -> str:
    """Best-effort URL that takes the viewer straight to `title` searched on
    the given service's own site. Falls back to a plain web search phrased
    as "<title> watch on <service>" for anything not explicitly modeled
    (an unrecognized free-platform name, or a service whose search-page
    pattern isn't known)."""
    q = quote_plus(title)

    if service_key == "free":
        for name in matched_names:
            low = name.lower()
            for needle, template in FREE_PLATFORM_SEARCH_URL_TEMPLATES:
                if needle in low:
                    return template.format(q=q)
        return f"https://www.google.com/search?q={quote_plus(title + ' watch free streaming')}"

    template = SERVICE_SEARCH_URL_TEMPLATES.get(service_key)
    if template:
        return template.format(q=q)
    return f"https://www.google.com/search?q={quote_plus(title + ' watch on ' + service_label)}"

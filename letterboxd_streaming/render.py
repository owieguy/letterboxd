"""Renders the collected film + streaming-availability data to a single
static HTML file using the Jinja2 template in templates/index.html.jinja.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .providers import SERVICE_DEFINITIONS

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_page(
    *,
    list_title: str,
    list_url: str,
    country: str,
    films: list[dict[str, Any]],
    unresolved_count: int,
    output_path: Path,
    back_to_index: str | None = None,
    refresh_workflow_url: str | None = None,
) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html.jinja")

    service_labels = [(key, label) for key, label, _ in SERVICE_DEFINITIONS]

    total_films = len(films)
    free_count = sum(1 for f in films if f["any_free"])

    # Per-service counts, sorted descending, for the summary bar chart --
    # magnitude comparison across a fixed set of named categories. Some
    # "services" (namely the free/ad-supported catch-all) are really an
    # umbrella over several distinct real platforms (Tubi, Pluto TV, ...) --
    # tally which specific ones actually matched so the chart/tooltip can
    # name them rather than just the umbrella label.
    service_counts = []
    for key, label in service_labels:
        matched_platforms = Counter()
        count = 0
        for f in films:
            svc = f["services"][key]
            if svc["available"]:
                count += 1
                matched_platforms.update(svc["matched"])
        breakdown = [
            {"name": name, "count": n}
            for name, n in matched_platforms.most_common()
        ]
        service_counts.append(
            {
                "key": key,
                "label": label,
                "count": count,
                # only meaningful when the umbrella covers >1 distinct platform
                "breakdown": breakdown if len(breakdown) > 1 else [],
            }
        )
    service_counts.sort(key=lambda row: row["count"], reverse=True)

    max_service_count = max((row["count"] for row in service_counts), default=0)
    for row in service_counts:
        row["pct_of_max"] = round(100 * row["count"] / max_service_count) if max_service_count else 0
        row["pct_of_total"] = round(100 * row["count"] / total_films) if total_films else 0

    html = template.render(
        list_title=list_title,
        list_url=list_url,
        country=country,
        films=films,
        service_labels=service_labels,
        service_counts=service_counts,
        total_films=total_films,
        free_count=free_count,
        unresolved_count=unresolved_count,
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        back_to_index=back_to_index,
        refresh_workflow_url=refresh_workflow_url,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)


def render_landing(*, lists: dict[str, dict], country: str, output_path: Path,
                    refresh_workflow_url: str | None = None) -> None:
    """Renders the hub page linking out to every list's own generated page."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("landing.html.jinja")

    rows = sorted(lists.values(), key=lambda row: row["title"].lower())

    html = template.render(
        lists=rows,
        country=country,
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        refresh_workflow_url=refresh_workflow_url,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)

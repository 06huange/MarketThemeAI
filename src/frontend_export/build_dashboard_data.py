from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


THEMES_DIR = Path("data/themes")
WEEKLY_INDEX_PATH = THEMES_DIR / "weekly_index.json"
THEME_LINKS_PATH = THEMES_DIR / "theme_links.json"
WEEKLY_DIR = THEMES_DIR / "weekly"

OUT_DIR = Path("public/data")
OUT_WEEKS_DIR = OUT_DIR / "weeks"
DASHBOARD_OUT_PATH = OUT_DIR / "dashboard.json"

EMERGING_GROWTH_THRESHOLD = 0.25
MIN_SIMILARITY_FOR_CONTINUATION = 0.60


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def compute_growth_rate(prev_size: int, curr_size: int) -> float | None:
    if prev_size <= 0:
        return None
    return (curr_size - prev_size) / prev_size


def compute_emerging_score(
    *,
    size: int,
    is_new: bool,
    growth_rate: float | None,
    similarity: float | None,
) -> float:
    size_score = min(size / 20.0, 1.0)

    if is_new:
        # New themes get a decent baseline if they are non-trivial in size.
        score = 0.55 + 0.45 * size_score
        return round(min(score, 1.0), 4)

    growth_component = 0.0 if growth_rate is None else max(min(growth_rate, 1.0), -1.0)
    similarity_component = 0.0 if similarity is None else max(min(similarity, 1.0), 0.0)

    # Favor growing themes with strong continuity.
    score = (
        0.45 * size_score
        + 0.35 * max(growth_component, 0.0)
        + 0.20 * similarity_component
    )
    return round(min(max(score, 0.0), 1.0), 4)


def build_trajectory_maps(links: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    best_incoming: dict[str, dict] = {}
    outgoing: dict[str, list[dict]] = defaultdict(list)

    for link in links:
        to_theme_id = link.get("to_theme_id")
        from_theme_id = link.get("from_theme_id")
        if not to_theme_id or not from_theme_id:
            continue

        outgoing[from_theme_id].append(link)

        current_best = best_incoming.get(to_theme_id)
        if current_best is None:
            best_incoming[to_theme_id] = link
            continue

        new_sim = safe_float(link.get("similarity"))
        cur_sim = safe_float(current_best.get("similarity"))

        # Prefer higher similarity; tie-break by larger destination size.
        if (
            new_sim > cur_sim
            or (
                new_sim == cur_sim
                and int(link.get("to_size", 0)) > int(current_best.get("to_size", 0))
            )
        ):
            best_incoming[to_theme_id] = link

    return best_incoming, dict(outgoing)


def build_theme_records(
    weeks: list[str],
    weekly_themes_by_week: dict[str, list[dict]],
    best_incoming: dict[str, dict],
    outgoing: dict[str, list[dict]],
) -> tuple[list[dict], dict[str, list[dict]]]:
    all_theme_records: list[dict] = []
    themes_by_week_out: dict[str, list[dict]] = {}

    for week in weeks:
        week_themes = weekly_themes_by_week.get(week, [])
        enriched_week_themes: list[dict] = []

        for theme in week_themes:
            theme_id = theme.get("theme_id")
            size = int(theme.get("size", 0))
            incoming = best_incoming.get(theme_id)
            outgoing_links = outgoing.get(theme_id, [])

            previous_theme_id = None
            previous_week = None
            previous_label = None
            previous_size = None
            similarity = None
            growth_rate = None

            if incoming is not None:
                similarity = safe_float(incoming.get("similarity"))
                previous_theme_id = incoming.get("from_theme_id")
                previous_week = incoming.get("from_week")
                previous_label = incoming.get("from_label")
                previous_size = int(incoming.get("from_size", 0))
                growth_rate = compute_growth_rate(previous_size, size)

            is_new = (
                incoming is None
                or similarity is None
                or similarity < MIN_SIMILARITY_FOR_CONTINUATION
            )

            is_emerging = is_new or (
                growth_rate is not None and growth_rate >= EMERGING_GROWTH_THRESHOLD
            )

            next_theme_ids = [x.get("to_theme_id") for x in outgoing_links if x.get("to_theme_id")]

            enriched = {
                "theme_id": theme_id,
                "week": theme.get("week"),
                "cluster_id": theme.get("cluster_id"),
                "label": theme.get("label"),
                "size": size,
                "top_companies": theme.get("top_companies", []),
                "top_keywords": theme.get("top_keywords", []),
                "example_titles": theme.get("example_titles", []),
                "article_ids": theme.get("article_ids", []),
                "centroid": theme.get("centroid", []),
                "previous_theme_id": previous_theme_id,
                "previous_week": previous_week,
                "previous_label": previous_label,
                "previous_size": previous_size,
                "similarity_to_previous": similarity,
                "growth_rate": None if growth_rate is None else round(growth_rate, 4),
                "is_new_theme": is_new,
                "is_emerging": is_emerging,
                "next_theme_ids": next_theme_ids,
                "out_degree": len(next_theme_ids),
                "emerging_score": compute_emerging_score(
                    size=size,
                    is_new=is_new,
                    growth_rate=growth_rate,
                    similarity=similarity,
                ),
            }

            enriched_week_themes.append(enriched)
            all_theme_records.append(enriched)

        enriched_week_themes.sort(
            key=lambda x: (
                x["emerging_score"],
                x["size"],
            ),
            reverse=True,
        )
        themes_by_week_out[week] = enriched_week_themes

    return all_theme_records, themes_by_week_out


def build_stats(themes: list[dict], weeks: list[str]) -> dict:
    total_themes = len(themes)
    emerging_count = sum(1 for t in themes if t.get("is_emerging"))
    new_count = sum(1 for t in themes if t.get("is_new_theme"))
    avg_size = round(
        sum(int(t.get("size", 0)) for t in themes) / total_themes, 2
    ) if total_themes else 0.0

    hottest = None
    if themes:
        hottest = max(themes, key=lambda x: (x.get("emerging_score", 0), x.get("size", 0)))

    return {
        "num_weeks": len(weeks),
        "total_themes": total_themes,
        "emerging_themes": emerging_count,
        "new_themes": new_count,
        "average_theme_size": avg_size,
        "hottest_theme": None if hottest is None else {
            "theme_id": hottest.get("theme_id"),
            "week": hottest.get("week"),
            "label": hottest.get("label"),
            "size": hottest.get("size"),
            "emerging_score": hottest.get("emerging_score"),
        },
    }


def main() -> None:
    weekly_index = load_json(WEEKLY_INDEX_PATH)
    links = load_json(THEME_LINKS_PATH)

    weeks = weekly_index.get("weeks", [])
    if not isinstance(weeks, list):
        raise ValueError(f"Expected 'weeks' list in {WEEKLY_INDEX_PATH}")

    weekly_themes_by_week: dict[str, list[dict]] = {}
    for week in weeks:
        week_path = WEEKLY_DIR / f"{week}.json"
        if not week_path.exists():
            print(f"Warning: missing weekly file for {week}: {week_path}")
            weekly_themes_by_week[week] = []
            continue
        weekly_themes_by_week[week] = load_json(week_path)

    best_incoming, outgoing = build_trajectory_maps(links)
    all_themes, themes_by_week_out = build_theme_records(
        weeks=weeks,
        weekly_themes_by_week=weekly_themes_by_week,
        best_incoming=best_incoming,
        outgoing=outgoing,
    )

    stats = build_stats(all_themes, weeks)

    emerging = sorted(
        [t for t in all_themes if t.get("is_emerging")],
        key=lambda x: (x.get("emerging_score", 0), x.get("size", 0)),
        reverse=True,
    )

    # Write per-week frontend files
    for week in weeks:
        payload = {
            "week": week,
            "themes": themes_by_week_out.get(week, []),
        }
        save_json(OUT_WEEKS_DIR / f"{week}.json", payload)

    dashboard_payload = {
        "weeks": weeks,
        "stats": stats,
        "themes": all_themes,
        "emerging": emerging,
        "links": links,
    }
    save_json(DASHBOARD_OUT_PATH, dashboard_payload)

    print(f"Saved dashboard data to {DASHBOARD_OUT_PATH}")
    print(f"Saved {len(weeks)} week files to {OUT_WEEKS_DIR}")
    print(f"Total themes: {len(all_themes)}")
    print(f"Emerging themes: {len(emerging)}")


if __name__ == "__main__":
    main()
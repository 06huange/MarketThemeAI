from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


WEEKLY_DIR = Path("data/themes/weekly")
OUT_PATH = Path("data/themes/theme_links.json")

# Every theme in this corpus is about AI and chips, so raw centroids all point the
# same way and unrelated themes still score ~0.85. Similarity is measured after
# subtracting the average theme, which leaves what distinguishes each one.
SIMILARITY_THRESHOLD = 0.55

# A story often skips a week of coverage, and the archive has gaps, so a theme is
# compared with themes from the last few weeks that have data, not just the last one.
LOOKBACK_WEEKS = 4


def load_week_files() -> list[Path]:
    return sorted(WEEKLY_DIR.glob("*.json"))


def load_json(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    if norm == 0:
        return v
    return v / norm


def parse_theme(theme: dict[str, Any], week: str) -> dict[str, Any] | None:
    centroid = theme.get("centroid")
    if centroid is None:
        return None

    centroid_arr = np.asarray(centroid, dtype=float)
    if centroid_arr.ndim != 1 or centroid_arr.size == 0:
        return None

    return {
        "theme_id": theme.get("theme_id", ""),
        "label": theme.get("label", ""),
        "week": week,
        "size": int(theme.get("size", 0)),
        "cluster_id": theme.get("cluster_id"),
        "centroid": l2_normalize(centroid_arr),
        "raw": theme,
    }


def load_weekly_themes() -> list[tuple[str, list[dict[str, Any]]]]:
    weekly = []

    for path in load_week_files():
        week = path.stem
        data = load_json(path)

        if not isinstance(data, list):
            print(f"Skipping {path} because top-level JSON is not a list")
            continue

        themes = []
        skipped = 0
        for item in data:
            if not isinstance(item, dict):
                skipped += 1
                continue
            parsed = parse_theme(item, week)
            if parsed is None:
                skipped += 1
                continue
            themes.append(parsed)

        print(f"{week}: loaded {len(themes)} themes, skipped {skipped}")
        weekly.append((week, themes))

    return weekly


def center_centroids(weekly: list[tuple[str, list[dict[str, Any]]]]) -> None:
    """Subtract the mean theme centroid in place, then renormalize."""
    themes = [t for _, week_themes in weekly for t in week_themes]
    if len(themes) < 2:
        return
    mean = np.mean([t["centroid"] for t in themes], axis=0)
    for t in themes:
        t["centroid"] = l2_normalize(t["centroid"] - mean)


def build_links(
    weekly: list[tuple[str, list[dict[str, Any]]]],
    threshold: float = SIMILARITY_THRESHOLD,
    lookback: int = LOOKBACK_WEEKS,
) -> list[dict[str, Any]]:
    """Link each theme to its most similar theme in the preceding `lookback` weeks.

    A theme has at most one predecessor, but a predecessor can continue into
    several themes (a story that splits), so linked themes form storylines.
    """
    links = []
    for k, (week, themes) in enumerate(weekly):
        earlier = [t for _, week_themes in weekly[max(0, k - lookback):k] for t in week_themes]
        if not earlier:
            continue
        earlier_matrix = np.stack([t["centroid"] for t in earlier])

        for theme in themes:
            sims = earlier_matrix @ theme["centroid"]
            # Highest similarity; on a tie, the more recent week.
            best = max(range(len(earlier)), key=lambda i: (sims[i], earlier[i]["week"]))
            if sims[best] < threshold:
                continue
            prev = earlier[best]
            links.append(
                {
                    "from_week": prev["week"],
                    "to_week": week,
                    "from_theme_id": prev["theme_id"],
                    "to_theme_id": theme["theme_id"],
                    "from_label": prev["label"],
                    "to_label": theme["label"],
                    "from_size": prev["size"],
                    "to_size": theme["size"],
                    "similarity": round(float(sims[best]), 4),
                }
            )
    return links


def main() -> None:
    weekly = load_weekly_themes()
    center_centroids(weekly)
    all_links = build_links(weekly)

    by_week: dict[str, list[dict[str, Any]]] = {}
    for link in all_links:
        by_week.setdefault(link["to_week"], []).append(link)
    for week, themes in weekly:
        links = by_week.get(week, [])
        print(f"{week}: {len(links)} of {len(themes)} themes continue an earlier one")
        for link in links[:5]:
            print(f"  {link['from_week']} {link['from_label'][:60]}  -->  {link['to_label'][:60]}  (sim={link['similarity']})")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_links, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_links)} links to {OUT_PATH}")


if __name__ == "__main__":
    main()

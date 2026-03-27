from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


WEEKLY_DIR = Path("data/themes/weekly")
OUT_PATH = Path("data/themes/theme_links.json")

SIMILARITY_THRESHOLD = 0.72
MAX_LINKS_PER_THEME = 1


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


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


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


def build_links_between_weeks(
    prev_week: str,
    prev_themes: list[dict[str, Any]],
    curr_week: str,
    curr_themes: list[dict[str, Any]],
    threshold: float,
    max_links_per_theme: int,
) -> list[dict[str, Any]]:
    if not prev_themes or not curr_themes:
        return []

    candidates = []
    for i, prev_theme in enumerate(prev_themes):
        for j, curr_theme in enumerate(curr_themes):
            sim = cosine_similarity(prev_theme["centroid"], curr_theme["centroid"])
            if sim >= threshold:
                candidates.append(
                    {
                        "prev_idx": i,
                        "curr_idx": j,
                        "similarity": sim,
                    }
                )

    candidates.sort(key=lambda x: x["similarity"], reverse=True)

    used_prev = set()
    used_curr = set()
    links = []

    for c in candidates:
        prev_idx = c["prev_idx"]
        curr_idx = c["curr_idx"]

        if max_links_per_theme == 1:
            if prev_idx in used_prev or curr_idx in used_curr:
                continue

        prev_theme = prev_themes[prev_idx]
        curr_theme = curr_themes[curr_idx]

        links.append(
            {
                "from_week": prev_week,
                "to_week": curr_week,
                "from_theme_id": prev_theme["theme_id"],
                "to_theme_id": curr_theme["theme_id"],
                "from_label": prev_theme["label"],
                "to_label": curr_theme["label"],
                "from_size": prev_theme["size"],
                "to_size": curr_theme["size"],
                "similarity": round(c["similarity"], 4),
            }
        )

        used_prev.add(prev_idx)
        used_curr.add(curr_idx)

    return links


def main() -> None:
    weekly = load_weekly_themes()

    all_links = []

    for k in range(len(weekly) - 1):
        prev_week, prev_themes = weekly[k]
        curr_week, curr_themes = weekly[k + 1]

        links = build_links_between_weeks(
            prev_week=prev_week,
            prev_themes=prev_themes,
            curr_week=curr_week,
            curr_themes=curr_themes,
            threshold=SIMILARITY_THRESHOLD,
            max_links_per_theme=MAX_LINKS_PER_THEME,
        )

        print(f"{prev_week} -> {curr_week}: {len(links)} links")
        for link in links[:10]:
            print(
                f"  {link['from_label']}  -->  {link['to_label']}  "
                f"(sim={link['similarity']})"
            )

        all_links.extend(links)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_links, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_links)} links to {OUT_PATH}")


if __name__ == "__main__":
    main()
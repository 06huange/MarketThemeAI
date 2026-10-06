"""The dashboard reads dashboard.json directly, so its shape is a contract with
frontend/app/theme_dashboard.tsx. These tests pin that contract."""

from src.frontend_export.build_dashboard_data import (
    build_stats,
    build_theme_records,
    build_trajectory_maps,
    strip_backend_fields,
)

WEEKS = ["W1", "W2"]


def theme(theme_id: str, week: str, size: int) -> dict:
    return {
        "theme_id": theme_id,
        "week": week,
        "cluster_id": 0,
        "label": theme_id,
        "size": size,
        "top_companies": [],
        "top_keywords": [],
        "example_titles": [],
        "article_ids": ["a"],
        "centroid": [0.1, 0.2],
    }


def link(src: dict, dst: dict, similarity: float) -> dict:
    return {
        "from_week": src["week"],
        "to_week": dst["week"],
        "from_theme_id": src["theme_id"],
        "to_theme_id": dst["theme_id"],
        "from_label": src["label"],
        "to_label": dst["label"],
        "from_size": src["size"],
        "to_size": dst["size"],
        "similarity": similarity,
    }


def records():
    baseline = theme("w1_a", "W1", 10)
    grown = theme("w2_a", "W2", 20)
    fresh = theme("w2_b", "W2", 6)
    best_incoming, outgoing = build_trajectory_maps([link(baseline, grown, 0.8)])
    themes, _ = build_theme_records(WEEKS, {"W1": [baseline], "W2": [grown, fresh]}, best_incoming, outgoing)
    return {t["theme_id"]: t for t in themes}


def test_first_week_is_a_baseline_not_new():
    t = records()["w1_a"]

    assert not t["is_new_theme"]
    assert not t["is_emerging"]


def test_unlinked_theme_after_first_week_is_new():
    t = records()["w2_b"]

    assert t["is_new_theme"]
    assert t["is_emerging"]


def test_linked_theme_reports_growth():
    t = records()["w2_a"]

    assert not t["is_new_theme"]
    assert t["previous_theme_id"] == "w1_a"
    assert t["growth_rate"] == 1.0
    assert t["is_emerging"]


def test_exported_theme_matches_frontend_type():
    exported = strip_backend_fields(records()["w2_a"])

    assert "centroid" not in exported
    assert "article_ids" not in exported
    required = {"theme_id", "week", "label", "size", "top_companies", "top_keywords", "example_titles"}
    assert required <= exported.keys()


def test_stats_shape():
    stats = build_stats(list(records().values()), WEEKS)

    assert stats["num_weeks"] == 2
    assert stats["total_themes"] == 3
    assert stats["new_themes"] == 1
    assert set(stats["hottest_theme"]) == {"theme_id", "week", "label", "size", "emerging_score"}

import numpy as np
import pytest

from src.themes.build_weekly_themes import (
    build_theme_objects,
    embed_articles,
    get_week,
    group_by_week,
    load_embedding_cache,
    save_embedding_cache,
)


@pytest.mark.parametrize(
    "date_str, week",
    [
        ("20260105120000", "2026-W02"),
        ("20251231T235959Z", "2026-W01"),  # ISO weeks can cross the calendar year
        ("20251228", "2025-W52"),
    ],
)
def test_get_week_uses_iso_weeks(date_str, week):
    assert get_week(date_str) == week


def test_get_week_rejects_unknown_formats():
    with pytest.raises(ValueError):
        get_week("Jan 5 2026")


def test_group_by_week():
    articles = [{"date": "20260105000000"}, {"date": "20260106000000"}, {"date": "20260112000000"}]

    grouped = group_by_week(articles)

    assert {week: len(items) for week, items in grouped.items()} == {"2026-W02": 2, "2026-W03": 1}


class FakeModel:
    def __init__(self):
        self.encoded = []

    def encode(self, texts, **kwargs):
        self.encoded.extend(texts)
        return np.ones((len(texts), 3), dtype=np.float32)


def test_embed_articles_only_embeds_uncached_articles():
    cache = {"a": np.zeros(3, dtype=np.float32)}
    model = FakeModel()
    articles = [{"article_id": "a", "title": "old"}, {"article_id": "b", "title": "new"}]

    vectors = embed_articles(articles, model, cache)

    assert model.encoded == ["new"]
    assert vectors.shape == (2, 3)
    assert set(cache) == {"a", "b"}


def test_embedding_cache_round_trip(tmp_path):
    path = tmp_path / "cache.npz"
    cache = {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 1.0])}

    save_embedding_cache(path, cache)
    loaded = load_embedding_cache(path)

    assert set(loaded) == {"a", "b"}
    np.testing.assert_array_equal(loaded["b"], cache["b"])


def test_theme_objects_skip_noise_and_aggregate_companies():
    week = "2026-W02"
    articles = [
        {"article_id": str(i), "title": f"Nvidia HBM supply story {i}", "matched_companies": ["NVIDIA"], "matched_keywords": ["hbm"]}
        for i in range(3)
    ] + [{"article_id": "noise", "title": "Unrelated", "matched_companies": [], "matched_keywords": []}]
    embeddings = np.eye(4)
    labels = np.array([0, 0, 0, -1])

    themes = build_theme_objects(week, articles, embeddings, labels)

    assert len(themes) == 1
    theme = themes[0]
    assert theme["theme_id"] == "2026-W02_theme_0"
    assert theme["size"] == 3
    assert theme["top_companies"] == ["NVIDIA"]
    assert "noise" not in theme["article_ids"]
    assert len(theme["centroid"]) == 4

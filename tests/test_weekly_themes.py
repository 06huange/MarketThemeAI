import numpy as np
import pytest

from src.themes.build_weekly_themes import (
    build_theme_objects,
    embed_articles,
    get_week,
    headline,
    keyphrases_by_cluster,
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


def make_articles(n, source_prefix="site", title="Nvidia HBM supply story"):
    return [
        {
            "article_id": f"{source_prefix}{i}",
            "title": f"{title} {i} | Site {i}",
            "source": f"{source_prefix}{i}.com",
            "matched_companies": ["NVIDIA"],
        }
        for i in range(n)
    ]


def test_theme_objects_skip_noise_and_use_most_central_headline():
    week = "2026-W02"
    articles = make_articles(3) + [{"article_id": "noise", "title": "Unrelated", "source": "x.com"}]
    angles = np.radians([0, 20, 40, 90])  # article 1 sits in the middle of the cluster
    embeddings = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    labels = np.array([0, 0, 0, -1])

    themes = build_theme_objects(week, articles, embeddings, labels)

    assert len(themes) == 1
    theme = themes[0]
    assert theme["theme_id"] == "2026-W02_theme_0"
    assert theme["size"] == 3
    assert theme["source_count"] == 3
    assert theme["top_companies"] == ["NVIDIA"]
    assert "noise" not in theme["article_ids"]
    # Site suffix stripped; the article nearest the centroid comes first.
    assert theme["label"] == "Nvidia HBM supply story 1"
    assert theme["example_titles"][0] == theme["label"]


def test_single_source_cluster_is_not_a_theme():
    articles = [{**a, "source": "fool.com"} for a in make_articles(5)]
    labels = np.zeros(5, dtype=int)

    assert build_theme_objects("W1", articles, np.eye(5), labels) == []


def test_off_scope_cluster_is_dropped():
    articles = make_articles(3)
    embeddings = np.tile([1.0, 0.0], (3, 1))
    labels = np.zeros(3, dtype=int)
    in_scope = np.array([[1.0, 0.0]])
    out_of_scope = np.array([[0.0, 1.0]])

    assert len(build_theme_objects("W1", articles, embeddings, labels, in_scope)) == 1
    assert build_theme_objects("W1", articles, embeddings, labels, out_of_scope) == []


def test_keyphrases_favor_terms_distinct_to_each_theme():
    phrases = keyphrases_by_cluster([
        ["Nvidia invests in OpenAI", "OpenAI raises funding from Nvidia"],
        ["AMD shares plunge on forecast", "AMD forecast disappoints investors"],
    ])

    assert "openai" in phrases[0] and "amd" not in phrases[0]
    assert "forecast" in phrases[1] and "openai" not in phrases[1]


def test_headline_strips_site_suffix():
    assert headline("Nvidia to invest $20B in OpenAI | Reuters") == "Nvidia to invest $20B in OpenAI"
    assert headline("Intel - AMD rivalry heats up - CNBC") == "Intel - AMD rivalry heats up"

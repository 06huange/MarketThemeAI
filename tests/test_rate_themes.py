from types import SimpleNamespace

from src.frontend_export.build_dashboard_data import build_stats, theme_rank
from src.themes.rate_themes import ThemeRating, cache_key, rate_all, theme_prompt


def theme(theme_id: str, titles: list[str]) -> dict:
    return {
        "theme_id": theme_id,
        "week": "2026-W13",
        "size": 13,
        "source_count": 12,
        "top_companies": ["Tesla", "Intel"],
        "example_titles": titles,
    }


class FakeMessages:
    def __init__(self, ratings: dict[str, ThemeRating | None]):
        self.ratings = ratings
        self.calls = []

    def parse(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        self.calls.append(prompt)
        rating = next(r for title, r in self.ratings.items() if title in prompt)
        if rating is None:
            return SimpleNamespace(stop_reason="refusal", parsed_output=None)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=rating)


def fake_client(ratings):
    return SimpleNamespace(messages=FakeMessages(ratings))


FAB = ThemeRating(significance=5, category="manufacturing", reason="A $25B chip fab reshapes US supply.")
SUMMIT = ThemeRating(significance=2, category="policy_and_trade", reason="A regional summit with no concrete action.")


def test_prompt_shows_headlines_companies_and_coverage():
    prompt = theme_prompt(theme("t", ["Musk launches Terafab"]))

    assert "- Musk launches Terafab" in prompt
    assert "Tesla, Intel" in prompt
    assert "13 articles from 12 outlets" in prompt


def test_rates_unseen_themes_and_reuses_cached_ones():
    fab, summit = theme("a", ["Musk launches Terafab"]), theme("b", ["India AI summit opens"])
    cache = {cache_key(summit): SUMMIT.model_dump()}
    client = fake_client({"Terafab": FAB, "summit": SUMMIT})

    calls = rate_all({"w": [fab, summit]}, cache, client)

    assert calls == 1
    assert len(client.messages.calls) == 1 and "Terafab" in client.messages.calls[0]
    assert fab["significance"] == 5 and fab["significance_category"] == "manufacturing"
    assert summit["significance"] == 2
    assert cache_key(fab) in cache


def test_failed_rating_leaves_theme_unrated_and_uncached():
    t = theme("a", ["Something odd"])
    cache = {}

    rate_all({"w": [t]}, cache, fake_client({"odd": None}))

    assert t["significance"] is None
    assert cache == {}


def test_without_a_client_only_cached_ratings_apply():
    cached, fresh = theme("a", ["Musk launches Terafab"]), theme("b", ["New story"])
    cache = {cache_key(cached): FAB.model_dump()}

    assert rate_all({"w": [cached, fresh]}, cache, None) == 0
    assert cached["significance"] == 5
    assert fresh["significance"] is None


def test_significant_themes_rank_first_and_win_hottest():
    chatter = {"theme_id": "chatter", "significance": 1, "emerging_score": 1.0, "size": 150}
    fab = {"theme_id": "fab", "significance": 5, "emerging_score": 0.6, "size": 13}
    unrated = {"theme_id": "unrated", "significance": None, "emerging_score": 0.9, "size": 40}

    ranked = sorted([chatter, fab, unrated], key=theme_rank, reverse=True)
    stats = build_stats([chatter, fab, unrated], ["W1"])

    assert [t["theme_id"] for t in ranked] == ["fab", "chatter", "unrated"]
    assert stats["hottest_theme"]["theme_id"] == "fab"
    assert stats["major_themes"] == 1

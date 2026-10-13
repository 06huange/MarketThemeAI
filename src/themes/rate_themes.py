"""Rate how significant each weekly theme is for the AI and semiconductor industry.

Clustering finds what got covered, not what mattered: laptop deals can draw more
articles than a $25B chip fab. A short Claude call per theme reads its headlines
and scores significance from 1 (not industry news) to 5 (industry-shaping), which
the dashboard uses to lead with pivotal themes.

Ratings are cached by the theme's headlines, so a weekly run only rates themes it
hasn't seen. Without ANTHROPIC_API_KEY the step is skipped and themes are unrated.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

WEEKLY_DIR = Path("data/themes/weekly")
CACHE_PATH = Path("data/themes/ratings_cache.json")

MODEL = "claude-haiku-5-5"
# Bump when the prompt or rubric changes so every theme is re-rated.
PROMPT_VERSION = "1"
MAX_HEADLINES = 8
WORKERS = 4

SYSTEM_PROMPT = """You are the editor of a weekly briefing on the AI and semiconductor industry, read by engineers and investors who want to know what changed the industry, not everything that was published.

You will get one news theme: a cluster of articles from the same week, shown as its headlines, the companies it mentions, and how widely it was covered. Rate how significant the underlying development is for the global AI and semiconductor industry.

Significance scale:
5 - Industry-shaping. Changes the competitive landscape, supply, or rules for the whole industry. Examples: a new multi-billion-dollar fab or chip megaproject, an acquisition or investment above roughly $10B between major players, a major change to export controls or tariffs on chips, a dominant company's strategy shift.
4 - Major. A significant move that industry watchers will remember: a large funding round for a leading AI lab, a new flagship GPU or accelerator architecture, record results from a bellwether like TSMC or Samsung that signal a trend, a government action against a major AI company, a big supply deal.
3 - Notable but incremental. Real news with limited reach: mid-size partnerships, product updates from major companies, earnings from mid-size players, ongoing policy debates.
2 - Minor. Regional or niche: national AI summits and initiatives, conference recaps, small partnerships, routine product refreshes, executive commentary without action.
1 - Not industry news. Consumer product reviews and shopping deals, stock-price moves and investment advice, analyst ratings, general opinion pieces.

Judge the development, not the amount of coverage: a widely covered summit can still be a 2, and a thinly covered fab announcement can still be a 5. If the headlines mix several stories, rate the dominant one."""


class ThemeRating(BaseModel):
    significance: int = Field(ge=1, le=5, description="1-5 on the scale in the instructions")
    category: Literal[
        "manufacturing", "deals_and_funding", "policy_and_trade", "products_and_tech",
        "earnings_and_demand", "markets_and_stocks", "consumer", "other",
    ]
    reason: str = Field(description="One short sentence naming the development and why it matters (or doesn't)")


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def theme_prompt(theme: dict) -> str:
    headlines = "\n".join(f"- {t}" for t in theme.get("example_titles", [])[:MAX_HEADLINES])
    companies = ", ".join(theme.get("top_companies", [])) or "none identified"
    return (
        f"Week: {theme.get('week')}\n"
        f"Coverage: {theme.get('size')} articles from {theme.get('source_count')} outlets\n"
        f"Companies mentioned most: {companies}\n"
        f"Headlines:\n{headlines}"
    )


def cache_key(theme: dict) -> str:
    """Ratings depend only on what the model sees, so the prompt is the key."""
    raw = f"{MODEL}\n{PROMPT_VERSION}\n{theme_prompt(theme)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rate_theme(client, theme: dict) -> dict | None:
    import anthropic

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": theme_prompt(theme)}],
            output_config={"effort": "low"},
            output_format=ThemeRating,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        print(f"  could not rate {theme.get('theme_id')}: {e}")
        return None

    if response.stop_reason != "end_turn" or response.parsed_output is None:
        print(f"  could not rate {theme.get('theme_id')}: stop_reason={response.stop_reason}")
        return None
    return response.parsed_output.model_dump()


def apply_rating(theme: dict, rating: dict | None) -> None:
    theme["significance"] = rating["significance"] if rating else None
    theme["significance_category"] = rating["category"] if rating else None
    theme["significance_reason"] = rating["reason"] if rating else None


def rate_all(weekly: dict[Path, list[dict]], cache: dict[str, dict], client) -> int:
    """Fill in ratings from the cache, calling the model for unseen themes. Returns calls made."""
    themes = [t for week_themes in weekly.values() for t in week_themes]
    missing = {cache_key(t): t for t in themes if cache_key(t) not in cache}

    if missing and client is not None:
        print(f"Rating {len(missing)} themes with {MODEL} ({len(themes) - len(missing)} cached)")
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for key, rating in zip(missing, pool.map(lambda t: rate_theme(client, t), missing.values())):
                if rating is not None:
                    cache[key] = rating

    for theme in themes:
        apply_rating(theme, cache.get(cache_key(theme)))
    return len(missing) if client is not None else 0


def main() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()
    else:
        client = None
        print("ANTHROPIC_API_KEY not set: themes will only get cached ratings")

    cache = load_json(CACHE_PATH, {})
    weekly = {path: load_json(path, []) for path in sorted(WEEKLY_DIR.glob("*.json"))}

    rate_all(weekly, cache, client)

    for path, themes in weekly.items():
        save_json(path, themes)
    save_json(CACHE_PATH, cache)

    rated = [t for themes in weekly.values() for t in themes if t.get("significance")]
    total = sum(len(themes) for themes in weekly.values())
    print(f"Rated {len(rated)} of {total} themes")
    for level in range(5, 0, -1):
        print(f"  significance {level}: {sum(1 for t in rated if t['significance'] == level)}")


if __name__ == "__main__":
    main()

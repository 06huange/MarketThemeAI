from pathlib import Path

import pytest

from src.preprocess.filter_articles import filter_articles, is_relevant_article, load_company_data, low_signal_reason, is_syndicated_commentary

COMPANY_CSV = Path("data/company_universe.csv")


def companies():
    return load_company_data(COMPANY_CSV)


def article(text: str, title: str = "") -> dict:
    return {"title": title, "text": text}


def test_alias_counts_as_canonical_company():
    terms, groups = companies()
    keep, meta = is_relevant_article(article("Samsung and Hynix raised HBM output."), terms, groups)

    assert keep
    assert meta["matched_companies"] == ["SK hynix", "Samsung Electronics"]
    assert meta["mentioned_groups"] == ["foundry", "memory"]


def test_company_names_match_whole_words_only():
    terms, groups = companies()
    keep, meta = is_relevant_article(article("Artificial intelligence is everywhere."), terms, groups)

    assert "Intel" not in meta["matched_companies"]
    assert not keep


def test_two_domain_keywords_keep_an_article_without_companies():
    terms, groups = companies()
    keep, meta = is_relevant_article(article("A new wafer fab for advanced packaging."), terms, groups)

    assert keep
    assert meta["company_count"] == 0
    assert meta["keyword_count"] >= 2


def test_irrelevant_article_is_dropped():
    terms, groups = companies()
    keep, _ = is_relevant_article(article("The local bakery won a pie contest."), terms, groups)

    assert not keep


def test_every_company_has_a_group():
    terms, groups = companies()

    assert len(terms) == 60
    assert set(terms) == set(groups)


def test_company_must_appear_in_headline_or_lead():
    terms, groups = companies()
    buried = article("Oil prices climbed on supply fears. " + "Crude rallied again. " * 60 + "Nvidia also rose.", title="Oil rallies")

    keep, meta = is_relevant_article(buried, terms, groups)

    assert not keep
    assert meta["matched_companies"] == ["NVIDIA"]  # still tagged from the full text


@pytest.mark.parametrize(
    "title, reason",
    [
        ("2 No-Brainer AI Stocks to Buy Right Now | The Motley Fool", "stock advice"),
        ("Korea Investment CORP Purchases 21,736 Shares of Broadcom Inc. $AVGO", "holdings filing"),
        ("Cimpress (CMPR) Q2 2026 Earnings Call Transcript", "earnings transcript"),
        ("Asia shares falter as Kospi sinks", "market wrap"),
        ("Prediction: This AI Stock Will Outperform Nvidia in 2026", "stock advice"),
        ("4 Reasons to Buy Nvidia Stock Like There's No Tomorrow", "stock advice"),
        ("Why Coherent (COHR) Stock Is Trading Up Today", "stock advice"),
        ("Is Amazon Stock a Good Buy?", "stock advice"),
        ("Selloff wipes out $1 trillion from software stocks as investors debate AI", None),
        ("Nvidia to invest $20 billion in OpenAI", None),
        ("TSMC beats forecasts on AI demand", None),
    ],
)
def test_low_signal_formats(title, reason):
    assert low_signal_reason(title) == reason


def test_filter_drops_syndicated_copies_and_keeps_the_earliest():
    terms, groups = companies()
    story = "TSMC raises capex on AI chip demand"
    arts = [
        {"title": f"{story} - Yahoo Finance", "text": "TSMC said...", "date": "20260105000000", "article_id": "copy"},
        {"title": f"{story} | Reuters", "text": "TSMC said...", "date": "20260104000000", "article_id": "original"},
        {"title": "Best AI stocks to buy now", "text": "Nvidia...", "date": "20260104000000", "article_id": "advice"},
    ]

    kept, dropped = filter_articles(arts, terms, groups)

    assert [a["article_id"] for a in kept] == ["original"]
    assert dropped == {"duplicate": 1, "stock advice": 1}


def test_syndicated_commentary_detected_from_disclosure_footer():
    body = "Nvidia's data center revenue keeps climbing. " * 20
    footer = "The Motley Fool has positions in and recommends Nvidia. The Motley Fool has a disclosure policy."

    assert is_syndicated_commentary(body + footer)
    assert not is_syndicated_commentary(body)

from pathlib import Path

from src.preprocess.filter_articles import is_relevant_article, load_company_data

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

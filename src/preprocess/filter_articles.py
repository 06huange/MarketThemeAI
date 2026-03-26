from __future__ import annotations

import csv
import json
import re
from pathlib import Path


RAW_ARTICLES_PATH = Path("data/raw/articles.json")
COMPANY_CSV_PATH = Path("data/company_universe.csv")
OUT_PATH = Path("data/processed/articles_filtered.json")

DOMAIN_KEYWORDS = [
    "semiconductor",
    "chip",
    "chips",
    "gpu",
    "ai accelerator",
    "datacenter",
    "data center",
    "advanced packaging",
    "wafer",
    "foundry",
    "lithography",
    "memory",
    "hbm",
    "ai server",
    "chipmaking",
    "inference",
    "training",
    "compute",
    "server",
]


def load_articles(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_company_data(path: Path) -> tuple[list[str], dict[str, str]]:
    company_terms = []
    company_to_group = {}
    seen = set()

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip()
            group = (row.get("group") or "").strip()

            if company:
                key = company.lower()
                if key not in seen:
                    seen.add(key)
                    company_terms.append(company)

                if group:
                    company_to_group[company] = group

    return company_terms, company_to_group


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_term(text: str, term: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)"
    return re.search(pattern, text) is not None


def count_matches(text: str, terms: list[str]) -> tuple[int, list[str]]:
    matched = []
    for term in terms:
        if contains_term(text, term):
            matched.append(term)
    return len(matched), matched


def is_relevant_article(
    article: dict,
    company_terms: list[str],
    company_to_group: dict[str, str],
) -> tuple[bool, dict]:
    title = article.get("title", "")
    body = article.get("text", "")
    combined = normalize_text(f"{title} {body}")

    company_count, matched_companies = count_matches(combined, company_terms)
    keyword_count, matched_keywords = count_matches(combined, DOMAIN_KEYWORDS)

    matched_companies = sorted(set(matched_companies))
    matched_keywords = sorted(set(matched_keywords))

    mentioned_groups = sorted({
        company_to_group[company]
        for company in matched_companies
        if company in company_to_group
    })

    keep = (company_count >= 1) or (keyword_count >= 2)

    meta = {
        "matched_companies": matched_companies,
        "matched_keywords": matched_keywords,
        "mentioned_groups": mentioned_groups,
        "company_match_count": company_count,
        "keyword_match_count": keyword_count,
        "company_count": len(matched_companies),
        "group_count": len(mentioned_groups),
        "keyword_count": len(matched_keywords),
    }
    return keep, meta


def main() -> None:
    articles = load_articles(RAW_ARTICLES_PATH)
    company_terms, company_to_group = load_company_data(COMPANY_CSV_PATH)

    kept = []
    dropped = []

    for article in articles:
        keep, meta = is_relevant_article(article, company_terms, company_to_group)

        enriched = dict(article)
        enriched.update(meta)

        if keep:
            kept.append(enriched)
        else:
            dropped.append(enriched)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"Input articles:   {len(articles)}")
    print(f"Kept articles:    {len(kept)}")
    print(f"Dropped articles: {len(dropped)}")
    print(f"Saved filtered dataset to: {OUT_PATH}")


if __name__ == "__main__":
    main()
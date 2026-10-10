from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path


RAW_ARTICLES_PATH = Path("data/raw/articles.json")
COMPANY_CSV_PATH = Path("data/company_universe.csv")
OUT_PATH = Path("data/processed/articles_filtered.json")

# Relevance is judged on the headline plus the opening of the article. An article
# that only names NVIDIA in its ninth paragraph (a typical oil-market or macro
# story) is not about the AI/semiconductor industry.
LEAD_CHARS = 600

DOMAIN_KEYWORDS = [
    "semiconductor",
    "chip",
    "chips",
    "chipmaker",
    "gpu",
    "cpu",
    "processor",
    "ai accelerator",
    "datacenter",
    "data center",
    "data centre",
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
    "ai",
    "artificial intelligence",
    "llm",
    "openai",
    "anthropic",
]

# Formats that mention the right companies but carry no industry news: stock-picking
# advice, automated 13F holding notices, earnings-call transcripts and templated
# analyst write-ups, and daily market wraps. Matched against the headline only.
LOW_SIGNAL_PATTERNS = {
    "stock advice": (
        r"\b(stocks? to (buy|own|hold|watch)|should you buy|buy (now|right now|and hold|before|today)"
        r"|best (ai |tech |growth |dividend )?stocks?|millionaire|\$\d[\d,]* (right now|today)|motley fool"
        r"|price target|(top|great) (ai )?stocks?|dividend|etfs?\b|hold forever|is it (too late|time) to buy"
        r"|stock (split|forecast|prediction)|(could|will) (soar|skyrocket|double|triple|make you)"
        r"|unstoppable|no-brainer|super stocks?|stocks? (that|i'd|i would|you can|worth)|buy the dip|better buy)\b"
        r"|^prediction\b|^\d+ (\w+[\s()-]+){0,6}stocks?\b|\b(this|these|my) (\w+[\s()-]+){0,6}stocks?\b(?! (market|exchange))"
        # single-stock price explainers: "Why X Stock Is Trading Up Today", "Is X Stock a Buy?"
        r"|\bwhy .{0,50}\b(stock|shares)\b.{0,25}\b(popped|jumped|soared|surged|sank|fell|plunged|dropped|rose|climbed|tumbled"
        r"|is (up|down|sinking|soaring|trading|underperforming|rising|falling|plunging))\b"
        r"|\bis .{0,40}\bstock an? (good |great )?buy\b|\btime to buy\b|\bsend .{0,30}\bstock\b"
    ),
    "holdings filing": (
        r"\b(increases|decreases|raises|lowers|trims|boosts|cuts|grows|reduces|lifts|sells|buys|acquires|purchases)\b"
        r".{0,40}\b(stake|position|holdings|shares)\b.{0,10}\bin\b|\$[A-Z]{1,5}\b|\b(shares|stock) (sold|bought|purchased) by\b"
    ),
    "earnings transcript": r"earnings call transcript|\btranscript\b|\bq[1-4] deep dive\b|analyst questions",
    "market wrap": (
        r"^(stocks?|wall street|dow|s&p|nasdaq|stock market|markets?"
        r"|(u\.?s\.?|us|asian?|asia-pacific|european?|global|world|wall st\.?|asx|kospi|nikkei|sensex|nifty|ftse|hang seng|tsx)\b"
        r".{0,25}\b(stocks?|shares|markets?|indexes|indices|futures|climbs?|falls?|rises?|slips?|drops?|gains?|ends?|closes?|opens?))\b"
        r"|stock market today|\b(sensex|nifty|kospi|nikkei)\b"
    ),
}
LOW_SIGNAL_RES = {reason: re.compile(p, re.I) for reason, p in LOW_SIGNAL_PATTERNS.items()}

# Investment-commentary publishers are often republished under another domain
# (mostly yahoo.com), so the source field misses them. Their standard bylines and
# disclosure footers give them away.
COMMENTARY_PUBLISHERS = re.compile(
    r"motley fool (has|recommends|has a disclosure)|the motley fool|fool\.com"
    r"|zacks (investment research|rank|equity research)|zacks\.com|stockstory|simply wall st"
    r"|investorplace|insider monkey|24/7 wall st|gurufocus|tipranks|seeking alpha",
    re.I,
)


def load_articles(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_company_data(path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return {company: [search terms]} and {company: group}.

    Search terms are the company name plus any `aliases` (semicolon-separated),
    so "Samsung" counts as a mention of "Samsung Electronics".
    """
    company_terms: dict[str, list[str]] = {}
    company_to_group = {}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip()
            group = (row.get("group") or "").strip()

            if company and company not in company_terms:
                aliases = [a.strip() for a in (row.get("aliases") or "").split(";")]
                company_terms[company] = [company] + [a for a in aliases if a]

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


def match_companies(text: str, company_terms: dict[str, list[str]]) -> list[str]:
    return sorted(
        company
        for company, terms in company_terms.items()
        if any(contains_term(text, term) for term in terms)
    )


def low_signal_reason(title: str) -> str | None:
    for reason, pattern in LOW_SIGNAL_RES.items():
        if pattern.search(title or ""):
            return reason
    return None


def is_syndicated_commentary(text: str) -> bool:
    text = text or ""
    return bool(COMMENTARY_PUBLISHERS.search(text[:500]) or COMMENTARY_PUBLISHERS.search(text[-3000:]))


def title_key(title: str) -> str:
    """Normalized headline used to spot the same story syndicated across sites."""
    headline = re.split(r"\s[|\-–]\s(?=[^|\-–]*$)", (title or "").lower())[0]
    return re.sub(r"[^a-z0-9]+", " ", headline).strip()


def is_relevant_article(
    article: dict,
    company_terms: dict[str, list[str]],
    company_to_group: dict[str, str],
) -> tuple[bool, dict]:
    title = article.get("title", "")
    body = article.get("text", "")
    combined = normalize_text(f"{title} {body}")
    lead = normalize_text(f"{title} {body[:LEAD_CHARS]}")

    # Tagging uses the full text; relevance only the headline and lead.
    matched_companies = match_companies(combined, company_terms)
    keyword_count, matched_keywords = count_matches(combined, DOMAIN_KEYWORDS)
    lead_companies = match_companies(lead, company_terms)
    lead_keyword_count, _ = count_matches(lead, DOMAIN_KEYWORDS)

    matched_keywords = sorted(set(matched_keywords))
    mentioned_groups = sorted({
        company_to_group[company]
        for company in matched_companies
        if company in company_to_group
    })

    keep = bool(lead_companies) or lead_keyword_count >= 2

    meta = {
        "matched_companies": matched_companies,
        "matched_keywords": matched_keywords,
        "mentioned_groups": mentioned_groups,
        "company_match_count": len(matched_companies),
        "keyword_match_count": keyword_count,
        "company_count": len(matched_companies),
        "group_count": len(mentioned_groups),
        "keyword_count": len(matched_keywords),
    }
    return keep, meta


def filter_articles(
    articles: list[dict],
    company_terms: dict[str, list[str]],
    company_to_group: dict[str, str],
) -> tuple[list[dict], Counter]:
    """Keep relevant, non-duplicate, newsworthy articles. Returns them plus drop counts by reason."""
    kept = []
    dropped: Counter = Counter()
    seen_titles: set[str] = set()

    # Oldest first, so the original publication wins over later syndicated copies.
    for article in sorted(articles, key=lambda a: a.get("date", "")):
        reason = low_signal_reason(article.get("title", ""))
        if reason:
            dropped[reason] += 1
            continue

        if is_syndicated_commentary(article.get("text", "")):
            dropped["syndicated commentary"] += 1
            continue

        key = title_key(article.get("title", ""))
        if key in seen_titles:
            dropped["duplicate"] += 1
            continue

        keep, meta = is_relevant_article(article, company_terms, company_to_group)
        if not keep:
            dropped["off-topic"] += 1
            continue

        seen_titles.add(key)
        kept.append({**article, **meta})

    return kept, dropped


def main() -> None:
    articles = load_articles(RAW_ARTICLES_PATH)
    company_terms, company_to_group = load_company_data(COMPANY_CSV_PATH)

    kept, dropped = filter_articles(articles, company_terms, company_to_group)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"Input articles:   {len(articles)}")
    print(f"Kept articles:    {len(kept)}")
    for reason, count in dropped.most_common():
        print(f"Dropped ({reason}): {count}")
    print(f"Saved filtered dataset to: {OUT_PATH}")


if __name__ == "__main__":
    main()

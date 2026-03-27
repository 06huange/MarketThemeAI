from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from collections import Counter
import re
from sklearn.feature_extraction.text import TfidfVectorizer

STOPWORDS = {
    "this", "that", "will", "with", "have", "from", "they", "here", "what",
    "when", "where", "after", "before", "could", "would", "about", "says",
    "said", "amid", "over", "into", "more", "than", "just", "your", "dont",
    "reveals", "raise", "raises", "need", "know", "today", "stock", "stocks",
    "wall", "street", "late", "highest", "through", "explains", "accused",
    "conspiring", "artificial", "james", "kenny", "now", "and"
}

BAD_PHRASES = {
    "through the",
    "its highest",
    "late",
    "and",
    "james nvidia",
    "kenny now",
    "ambassador explains",
    "lands wall",
    "oil prices",   # optional: keep if you want
}

def clean_title_for_label(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"[|:–—-].*$", "", title).strip()
    return title

def extract_best_phrase(titles: list[str]) -> str | None:
    if not titles:
        return None

    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words=list(STOPWORDS),
            ngram_range=(2, 3),
            max_features=100,
            max_df=1.0,
            min_df=1,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b",
        )
        X = vectorizer.fit_transform(titles)
        scores = X.sum(axis=0).A1
        terms = vectorizer.get_feature_names_out()

        ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)

        for term, _ in ranked:
            if term in BAD_PHRASES:
                continue
            words = term.split()
            if len(words) < 2 or len(words) > 3:
                continue
            if any(w in STOPWORDS for w in words):
                continue
            return term
    except ValueError:
        return None

    return None


def generate_label(cluster_articles: list[dict]) -> str:
    # Use only the most central articles
    cluster_articles = sorted(
        cluster_articles,
        key=lambda a: a.get("cluster_probability", 0.0),
        reverse=True
    )

    top_articles = cluster_articles[:8]

    titles = [
        clean_title_for_label(a.get("title", ""))
        for a in top_articles
        if a.get("title")
    ]

    company_counter = Counter()
    keyword_counter = Counter()

    for a in cluster_articles:
        company_counter.update(a.get("matched_companies", []))
        keyword_counter.update(a.get("matched_keywords", []))

    top_company = company_counter.most_common(1)[0][0] if company_counter else None
    top_keyword = keyword_counter.most_common(1)[0][0] if keyword_counter else None

    best_phrase = extract_best_phrase(titles)

    # Best case: company + phrase
    if top_company and best_phrase:
        phrase_words = set(best_phrase.lower().split())
        if top_company.lower() not in phrase_words:
            return f"{top_company} {best_phrase}"
        return best_phrase.title()

    # Fallback: company + keyword
    if top_company and top_keyword:
        return f"{top_company} {top_keyword}"

    # Fallback: cleaned best title
    if titles:
        return titles[0]

    return "Unlabeled theme"

EMBED_PATH = Path("data/embeddings/article_embeddings.npy")
CLUSTERED_ARTICLES_PATH = Path("data/clustered/articles_clustered.json")
OUT_PATH = Path("data/themes/themes.json")


def load_embeddings(path: Path) -> np.ndarray:
    return np.load(path)


def load_articles(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    embeddings = load_embeddings(EMBED_PATH)
    articles = load_articles(CLUSTERED_ARTICLES_PATH)

    assert len(articles) == embeddings.shape[0], "Embeddings and articles are misaligned."

    cluster_to_articles: dict[int, list[dict]] = defaultdict(list)
    cluster_to_vectors: dict[int, list[np.ndarray]] = defaultdict(list)

    for article, emb in zip(articles, embeddings):
        cluster_id = article.get("cluster_id", -1)

        # skip HDBSCAN noise
        if cluster_id == -1:
            continue

        cluster_to_articles[cluster_id].append(article)
        cluster_to_vectors[cluster_id].append(emb)

    themes = []

    for cluster_id in sorted(cluster_to_articles.keys()):
        cluster_articles = cluster_to_articles[cluster_id]
        cluster_vectors = np.array(cluster_to_vectors[cluster_id])

        centroid = np.mean(cluster_vectors, axis=0)

        company_counter = Counter()
        keyword_counter = Counter()

        for article in cluster_articles:
            company_counter.update(article.get("matched_companies", []))
            keyword_counter.update(article.get("matched_keywords", []))

        example_titles = []
        for article in cluster_articles[:5]:
            title = article.get("title", "").strip()
            if title:
                example_titles.append(title)

        label = generate_label(cluster_articles)

        theme = {
            "theme_id": f"theme_{cluster_id}",
            "label": label,
            "cluster_id": cluster_id,
            "size": len(cluster_articles),
            "top_companies": [x for x, _ in company_counter.most_common(5)],
            "top_keywords": [x for x, _ in keyword_counter.most_common(8)],
            "example_titles": example_titles,
            "centroid": centroid.tolist(),
        }

        themes.append(theme)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False, indent=2)

    print(f"Built {len(themes)} themes")
    print(f"Saved themes to: {OUT_PATH}")


if __name__ == "__main__":
    main()
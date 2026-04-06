from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import hdbscan
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


ARTICLES_PATH = Path("data/raw/articles.json")
OUT_DIR = Path("data/themes/weekly")

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
MIN_CLUSTER_SIZE = 5
MIN_SAMPLES = 3
TOP_K_COMPANIES = 5
TOP_K_KEYWORDS = 8
TOP_K_TITLE_TERMS = 5
MAX_LABEL_TERMS = 3


def load_articles() -> list[dict]:
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_week(date_str: str) -> str:
    date_str = (date_str or "").strip()

    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            year, week, _ = dt.isocalendar()
            return f"{year}-W{week:02d}"
        except ValueError:
            pass

    raise ValueError(f"Unrecognized date format: {date_str!r}")


def group_by_week(articles: list[dict]) -> dict[str, list[dict]]:
    weekly = defaultdict(list)
    for article in articles:
        week = get_week(article["date"])
        weekly[week].append(article)
    return dict(weekly)


def make_embedding_text(article: dict, max_chars: int = 2000) -> str:
    title = (article.get("title") or "").strip()
    text = (article.get("text") or "").strip()
    body = text[:max_chars]
    return f"{title}\n\n{body}".strip()


def get_top_items(items: list[str], k: int) -> list[str]:
    counter = Counter(x for x in items if x)
    return [x for x, _ in counter.most_common(k)]


def build_label(theme_articles: list[dict]) -> str:
    titles = [(a.get("title") or "").strip() for a in theme_articles if a.get("title")]
    matched_companies = []
    matched_keywords = []

    for a in theme_articles:
        matched_companies.extend(a.get("matched_companies", []))
        matched_keywords.extend(a.get("matched_keywords", []))

    top_companies = get_top_items(matched_companies, TOP_K_COMPANIES)
    top_keywords = get_top_items(matched_keywords, TOP_K_KEYWORDS)

    title_terms = []
    if titles:
        tfidf = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=200,
        )
        X = tfidf.fit_transform(titles)
        scores = np.asarray(X.sum(axis=0)).ravel()
        vocab = np.array(tfidf.get_feature_names_out())
        ranked = vocab[np.argsort(scores)[::-1]]
        title_terms = ranked[:TOP_K_TITLE_TERMS].tolist()

    label_parts = []
    for token in title_terms + top_companies + top_keywords:
        if token not in label_parts:
            label_parts.append(token)
        if len(label_parts) >= MAX_LABEL_TERMS:
            break

    return " | ".join(label_parts) if label_parts else "misc theme"


def build_theme_objects(
    week: str,
    articles: list[dict],
    embeddings: np.ndarray,
    cluster_labels: np.ndarray,
) -> list[dict]:
    themes = []

    unique_clusters = sorted(set(cluster_labels.tolist()))
    for cluster_id in unique_clusters:
        if cluster_id == -1:
            continue

        idxs = np.where(cluster_labels == cluster_id)[0]
        cluster_articles = [articles[i] for i in idxs]
        cluster_embs = embeddings[idxs]

        centroid = cluster_embs.mean(axis=0)

        matched_companies = []
        matched_keywords = []
        for a in cluster_articles:
            matched_companies.extend(a.get("matched_companies", []))
            matched_keywords.extend(a.get("matched_keywords", []))

        theme = {
            "theme_id": f"{week}_theme_{cluster_id}",
            "week": week,
            "cluster_id": int(cluster_id),
            "size": int(len(cluster_articles)),
            "label": build_label(cluster_articles),
            "top_companies": get_top_items(matched_companies, TOP_K_COMPANIES),
            "top_keywords": get_top_items(matched_keywords, TOP_K_KEYWORDS),
            "example_titles": [
                (a.get("title") or "").strip()
                for a in cluster_articles[:5]
            ],
            "article_ids": [
                a.get("article_id") or a.get("id") or f"{week}_{i}"
                for i, a in enumerate(cluster_articles)
            ],
            "centroid": centroid.tolist(),
        }
        themes.append(theme)

    return themes


def cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    if len(embeddings) < MIN_CLUSTER_SIZE:
        return np.full(len(embeddings), -1, dtype=int)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric="euclidean",
        prediction_data=False,
    )
    return clusterer.fit_predict(embeddings)


def process_week(
    week: str,
    articles: list[dict],
    model: SentenceTransformer,
) -> list[dict]:
    texts = [make_embedding_text(a) for a in articles]
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    cluster_labels = cluster_embeddings(embeddings)
    themes = build_theme_objects(week, articles, embeddings, cluster_labels)
    return themes


def main() -> None:
    articles = load_articles()
    weekly_articles = group_by_week(articles)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    model = SentenceTransformer(EMBED_MODEL_NAME)

    for week, articles_in_week in sorted(weekly_articles.items()):
        print(f"{week}: {len(articles_in_week)} articles")

        themes = process_week(week, articles_in_week, model)

        out_path = OUT_DIR / f"{week}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(themes, f, indent=2, ensure_ascii=False)

        print(f"  -> saved {len(themes)} themes to {out_path}")


if __name__ == "__main__":
    main()
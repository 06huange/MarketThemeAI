from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import hdbscan
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


ARTICLES_PATH = Path("data/processed/articles_filtered.json")
OUT_DIR = Path("data/themes/weekly")
EMBED_CACHE_PATH = Path("data/embeddings/embedding_cache.npz")

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
MIN_CLUSTER_SIZE = 5
MIN_SAMPLES = 3
TOP_K_COMPANIES = 5
TOP_K_KEYPHRASES = 5
EXAMPLE_TITLES = 5

# HDBSCAN on raw 384-d embeddings either discards most articles as noise or merges
# a week into one blob (density is meaningless in high dimensions). Reducing to a
# few dimensions with UMAP first is the standard fix.
UMAP_COMPONENTS = 5
UMAP_NEIGHBORS = 15
RANDOM_STATE = 42

# A theme is a story several outlets cover, not one site's recurring format.
MIN_SOURCES = 3

# Themes whose centroid is far from every scope description are off-topic
# (consumer finance, oil, politics). Deliberately a low floor: centroid similarity
# is noisy, so this only removes the clearly unrelated.
SCOPE_ANCHORS = [
    "semiconductor chip manufacturing, foundries, and fabs",
    "AI accelerators and GPUs for training and inference",
    "AI data center construction, power, and infrastructure spending",
    "memory chips: HBM, DRAM, and NAND supply",
    "chip export controls and semiconductor trade policy",
    "AI model companies, funding rounds, and partnerships",
    "networking, optical interconnects, and servers for AI",
    "consumer devices powered by new processors and chips",
]
MIN_SCOPE_SIMILARITY = 0.30

# Words that appear in nearly every headline in this corpus and say nothing
# about what distinguishes one theme from another.
LABEL_STOPWORDS = ENGLISH_STOP_WORDS | {
    "ai", "artificial", "intelligence", "stock", "stocks", "shares", "share",
    "company", "companies", "new", "says", "said", "report", "reports", "year",
    "week", "today", "inc", "corp", "corporation", "nasdaq", "nyse", "news",
    "update", "billion", "million", "market", "markets", "tech", "technology",
    "com", "www", "going", "know", "just", "really", "heres", "here",
}


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


def headline(title: str) -> str:
    """Article title without a trailing " | Site Name" / " - Site Name"."""
    return re.split(r"\s[|\-–]\s(?=[^|\-–]*$)", (title or "").strip())[0].strip()


def is_usable_headline(title: str) -> bool:
    # Scraped titles are occasionally page furniture ("Date Posted") or a bare URL.
    return len(title.split()) >= 4 and not title.lower().startswith("http")


def rank_by_centrality(embeddings: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Indices ordered most-to-least representative, plus the normalized centroid."""
    centroid = embeddings.mean(axis=0)
    centroid = centroid / (np.linalg.norm(centroid) or 1.0)
    return np.argsort(-(embeddings @ centroid), kind="stable"), centroid


def keyphrases_by_cluster(titles_by_cluster: list[list[str]], k: int = TOP_K_KEYPHRASES) -> list[list[str]]:
    """Class-based TF-IDF: terms frequent in one theme's headlines but rare in the week's other themes."""
    docs = [" ".join(headline(t) for t in titles) for titles in titles_by_cluster]
    if not any(docs):
        return [[] for _ in docs]
    vectorizer = CountVectorizer(
        stop_words=list(LABEL_STOPWORDS),
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]+\b",
    )
    try:
        counts = vectorizer.fit_transform(docs).toarray().astype(float)
    except ValueError:  # every word was a stopword
        return [[] for _ in docs]
    vocab = vectorizer.get_feature_names_out()

    tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1.0)
    avg_words = counts.sum() / len(docs)
    idf = np.log(1.0 + avg_words / np.maximum(counts.sum(axis=0), 1.0))
    scores = tf * idf

    phrases = []
    for row in scores:
        # Highest score first; ties broken alphabetically so output is identical across machines.
        order = np.lexsort((vocab, -row))
        picked: list[str] = []
        for term in vocab[order]:
            if row[vectorizer.vocabulary_[term]] <= 0 or len(picked) == k:
                break
            if any(term in p or p in term for p in picked):
                continue
            picked.append(term)
        phrases.append(picked)
    return phrases


def build_theme_objects(
    week: str,
    articles: list[dict],
    embeddings: np.ndarray,
    cluster_labels: np.ndarray,
    scope_embeddings: np.ndarray | None = None,
) -> list[dict]:
    clusters = []
    for cluster_id in sorted(c for c in set(cluster_labels.tolist()) if c != -1):
        idxs = np.where(cluster_labels == cluster_id)[0]
        sources = {articles[i].get("source") for i in idxs}
        if len(sources) < MIN_SOURCES:
            continue

        order, centroid = rank_by_centrality(embeddings[idxs])
        relevance = float((scope_embeddings @ centroid).max()) if scope_embeddings is not None else None
        if relevance is not None and relevance < MIN_SCOPE_SIMILARITY:
            continue

        ranked = [articles[idxs[j]] for j in order]
        clusters.append((cluster_id, ranked, embeddings[idxs].mean(axis=0), len(sources), relevance))

    keyphrases = keyphrases_by_cluster([[a.get("title", "") for a in ranked] for _, ranked, *_ in clusters])

    themes = []
    for (cluster_id, ranked, centroid, n_sources, relevance), phrases in zip(clusters, keyphrases):
        titles: list[str] = []
        for a in ranked:
            t = headline(a.get("title", ""))
            if is_usable_headline(t) and t not in titles:
                titles.append(t)

        companies = [c for a in ranked for c in a.get("matched_companies", [])]
        theme = {
            "theme_id": f"{week}_theme_{cluster_id}",
            "week": week,
            "cluster_id": int(cluster_id),
            "size": len(ranked),
            # The most representative headline reads better than any keyword list.
            "label": titles[0] if titles else " · ".join(phrases[:3]) or "untitled theme",
            "top_companies": get_top_items(companies, TOP_K_COMPANIES),
            "top_keywords": phrases,
            "example_titles": titles[:EXAMPLE_TITLES],
            "source_count": n_sources,
            "relevance": None if relevance is None else round(relevance, 3),
            "article_ids": [a.get("article_id") for a in ranked],
            "centroid": centroid.tolist(),
        }
        themes.append(theme)

    return themes


def cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    if len(embeddings) < max(MIN_CLUSTER_SIZE, UMAP_COMPONENTS + 2):
        return np.full(len(embeddings), -1, dtype=int)

    import umap  # heavy import (numba); only needed when clustering

    reduced = umap.UMAP(
        n_components=UMAP_COMPONENTS,
        n_neighbors=min(UMAP_NEIGHBORS, len(embeddings) - 1),
        min_dist=0.0,
        metric="cosine",
        random_state=RANDOM_STATE,
    ).fit_transform(embeddings)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric="euclidean",
        prediction_data=False,
    )
    return clusterer.fit_predict(reduced)


def load_embedding_cache(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    data = np.load(path, allow_pickle=False)
    if str(data["model"]) != EMBED_MODEL_NAME:
        return {}
    return dict(zip(data["ids"].tolist(), data["vectors"]))


def save_embedding_cache(path: Path, cache: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = list(cache)
    np.savez(
        path,
        model=np.array(EMBED_MODEL_NAME),
        ids=np.array(ids),
        vectors=np.stack([cache[i] for i in ids]),
    )


def embed_articles(
    articles: list[dict],
    model: SentenceTransformer,
    cache: dict[str, np.ndarray],
) -> np.ndarray:
    """Embed articles, reusing cached vectors so weekly runs only embed new articles."""
    missing = [a for a in articles if a["article_id"] not in cache]
    if missing:
        print(f"Embedding {len(missing)} new articles ({len(articles) - len(missing)} cached)")
        vectors = model.encode(
            [make_embedding_text(a) for a in missing],
            convert_to_numpy=True,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        cache.update(zip((a["article_id"] for a in missing), vectors))
    return np.stack([cache[a["article_id"]] for a in articles])


def process_week(
    week: str,
    articles: list[dict],
    embeddings: np.ndarray,
    scope_embeddings: np.ndarray | None = None,
) -> list[dict]:
    cluster_labels = cluster_embeddings(embeddings)
    return build_theme_objects(week, articles, embeddings, cluster_labels, scope_embeddings)


def main() -> None:
    articles = load_articles()
    weekly_articles = group_by_week(articles)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Imported here so the rest of this module (and its tests) loads without torch.
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL_NAME)
    cache = load_embedding_cache(EMBED_CACHE_PATH)
    embed_articles(articles, model, cache)
    save_embedding_cache(EMBED_CACHE_PATH, cache)
    scope = model.encode(SCOPE_ANCHORS, convert_to_numpy=True, normalize_embeddings=True)

    # Rebuild every week from scratch so files for weeks that no longer have themes don't linger.
    for stale in OUT_DIR.glob("*.json"):
        stale.unlink()

    for week, articles_in_week in sorted(weekly_articles.items()):
        print(f"{week}: {len(articles_in_week)} articles")

        embeddings = embed_articles(articles_in_week, model, cache)
        themes = process_week(week, articles_in_week, embeddings, scope)

        out_path = OUT_DIR / f"{week}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(themes, f, indent=2, ensure_ascii=False)

        print(f"  -> saved {len(themes)} themes to {out_path}")


if __name__ == "__main__":
    main()
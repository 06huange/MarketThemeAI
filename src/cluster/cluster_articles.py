from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from collections import defaultdict

import hdbscan
import numpy as np


EMBED_PATH = Path("data/embeddings/article_embeddings.npy")
META_PATH = Path("data/processed/articles_for_clustering.json")
OUT_PATH = Path("data/clustered/articles_clustered.json")


def load_embeddings(path: Path) -> np.ndarray:
    return np.load(path)


def load_articles(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def preview_clusters(clustered_articles: list[dict], top_k: int = 10, samples_per_cluster: int = 5) -> None:
    buckets = defaultdict(list)
    for article in clustered_articles:
        cid = article["cluster_id"]
        if cid == -1:
            continue
        buckets[cid].append(article)

    ranked = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)

    for cid, items in ranked[:top_k]:
        print(f"\n=== Cluster {cid} | size={len(items)} ===")
        for article in items[:samples_per_cluster]:
            print("-", article.get("title", "")[:160])

def main() -> None:
    embeddings = load_embeddings(EMBED_PATH)
    articles = load_articles(META_PATH)

    assert embeddings.shape[0] == len(articles), "Embeddings and articles are misaligned."

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=15,
        min_samples=5,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )

    labels = clusterer.fit_predict(embeddings)
    probabilities = clusterer.probabilities_

    clustered_articles = []
    for article, label, prob in zip(articles, labels, probabilities):
        enriched = dict(article)
        enriched["cluster_id"] = int(label)
        enriched["cluster_probability"] = float(prob)
        clustered_articles.append(enriched)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(clustered_articles, f, ensure_ascii=False, indent=2)

    num_noise = int(np.sum(labels == -1))
    num_clustered = len(labels) - num_noise
    num_clusters = len(set(labels)) - (1 if -1 in labels else 0)

    print("num clusters:", num_clusters)
    print("num clustered articles:", num_clustered)
    print("num noise articles:", num_noise)
    print("cluster sizes:", Counter(labels).most_common(20))
    print("saved to:", OUT_PATH)

    print("\nPreviewing Clusters")
    preview_clusters(clustered_articles)

if __name__ == "__main__":
    main()
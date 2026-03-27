import json
from pathlib import Path
import re
from sentence_transformers import SentenceTransformer
import numpy as np

INPUT_PATH = Path("data/processed/articles_filtered.json")

# load filtered articles json file
with open(INPUT_PATH, "r", encoding="utf-8") as f:
    articles = json.load(f)


MAX_BODY_CHARS = 2000

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

# normalize white space in article and merge title + body, limiting to 2000 characters for body
def build_embedding_text(article: dict) -> str:
    title = normalize_whitespace(article.get("title", ""))
    body = normalize_whitespace(article.get("text", ""))

    body = body[:MAX_BODY_CHARS]

    if title and body:
        return f"{title}\n\n{body}"
    return title or body

texts = []
kept_articles = []

# preprocess article content into text array
for article in articles:
    text = build_embedding_text(article)
    if not text:
        continue
    texts.append(text)
    kept_articles.append(article)

print("texts to embed:", len(texts))
print("first text preview:\n", texts[0][:500])

# load sentence transformer model (all-MiniLM-L6-v2)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# embed articles saved in texts[]
embeddings = model.encode(
    texts,
    batch_size=32,
    show_progress_bar=True,
    convert_to_numpy=True,
    normalize_embeddings=True,
)

print(embeddings.shape)

# save embedding
EMBED_PATH = Path("data/embeddings/article_embeddings.npy")
META_PATH = Path("data/processed/articles_for_clustering.json")

EMBED_PATH.parent.mkdir(parents=True, exist_ok=True)

np.save(EMBED_PATH, embeddings)

with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(kept_articles, f, ensure_ascii=False, indent=2)

print("saved embeddings:", EMBED_PATH)
print("saved metadata:", META_PATH)
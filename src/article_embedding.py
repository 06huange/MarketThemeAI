import json
from pathlib import Path

INPUT_PATH = Path("data/processed/articles_filtered.json")

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    articles = json.load(f)

print("num articles:", len(articles))
print("keys:", articles[0].keys())
print("title sample:", articles[0]["title"][:120])
print("text sample:", articles[0]["text"][:300])
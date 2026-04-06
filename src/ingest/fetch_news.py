from __future__ import annotations

import argparse
import csv
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import trafilatura


BQ_CSV_PATH = Path("data/raw/gdelt_bq_articles.csv")
OUT_PATH = Path("data/raw/articles.json")
FAILED_URLS_PATH = Path("data/raw/failed_urls.json")

ARTICLE_SLEEP_SECONDS = 0.0
MAX_WORKERS = 12
SAVE_EVERY = 25


@dataclass
class Article:
    article_id: str
    date: str
    title: str
    text: str
    source: str
    url: str
    query: str
    language: str | None = None
    v2organizations: str | None = None
    v2themes: str | None = None
    translationinfo: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=BQ_CSV_PATH,
        help="Path to BigQuery-exported CSV.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=MAX_WORKERS,
        help="Number of concurrent article fetches.",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=SAVE_EVERY,
        help="Flush to disk every N newly saved articles.",
    )
    return parser.parse_args()


def make_article_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def load_existing_articles(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dedupe_by_url(items: list[dict]) -> list[dict]:
    seen = set()
    out = []

    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)

    return out


def normalize_bq_date(raw_date: str) -> str:
    raw_date = (raw_date or "").strip()
    if not raw_date:
        return ""

    digits = "".join(ch for ch in raw_date if ch.isdigit())

    if len(digits) == 14:
        return digits
    if len(digits) == 8:
        return f"{digits}000000"

    return raw_date


def infer_language(translation_info: str | None) -> str | None:
    if not translation_info:
        return None

    ti = translation_info.lower()
    if "srclc:eng" in ti:
        return "English"

    return None


def load_raw_hits_from_bq_csv(path: Path) -> list[dict]:
    hits: list[dict] = []

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hits.append(
                {
                    "url": (row.get("url") or "").strip(),
                    "title": "",
                    "domain": (row.get("SourceCommonName") or "").strip(),
                    "seendate": normalize_bq_date(row.get("DATE") or ""),
                    "sourceLanguage": infer_language(row.get("TranslationInfo")),
                    "V2Organizations": row.get("V2Organizations"),
                    "V2Themes": row.get("V2Themes"),
                    "TranslationInfo": row.get("TranslationInfo"),
                }
            )

    return hits


def extract_article_content(url: str) -> tuple[str, str]:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "", ""

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
    )
    text = text.strip() if text else ""

    metadata = trafilatura.extract_metadata(downloaded)
    title = metadata.title.strip() if metadata and metadata.title else ""

    return title, text


def normalize_bq_article(
    raw: dict,
    query: str,
    title: str,
    text: str,
) -> Article:
    url = (raw.get("url") or "").strip()
    source = (raw.get("domain") or "").strip()
    date = (raw.get("seendate") or "").strip()
    language = raw.get("sourceLanguage")

    return Article(
        article_id=make_article_id(url),
        date=date,
        title=title.strip(),
        text=text.strip(),
        source=source,
        url=url,
        query=query,
        language=language,
        v2organizations=raw.get("V2Organizations"),
        v2themes=raw.get("V2Themes"),
        translationinfo=raw.get("TranslationInfo"),
    )


def build_final_records(existing: list[dict], new_records: list[dict]) -> list[dict]:
    by_id = {item["article_id"]: item for item in existing}
    for item in new_records:
        by_id[item["article_id"]] = item

    return sorted(
        by_id.values(),
        key=lambda x: x.get("date", ""),
        reverse=True,
    )


def process_one(raw: dict, query: str) -> tuple[dict | None, dict | None]:
    url = (raw.get("url") or "").strip()
    if not url:
        return None, {"url": "", "error": "missing url"}

    try:
        fetched_title, text = extract_article_content(url)
    except Exception as e:
        return None, {"url": url, "error": str(e)}

    if not text:
        return None, {"url": url, "error": "no text extracted"}

    article = normalize_bq_article(
        raw,
        query=query,
        title=fetched_title or url,
        text=text,
    )

    if not article.url:
        return None, {"url": url, "error": "normalized article missing url"}

    return asdict(article), None


def main() -> None:
    args = parse_args()

    query = "bigquery_gkg_export"
    all_raw_hits = load_raw_hits_from_bq_csv(args.input_csv)
    all_raw_hits = dedupe_by_url(all_raw_hits)

    print(f"Unique URLs from BigQuery CSV: {len(all_raw_hits)}")

    existing = load_existing_articles(OUT_PATH)
    existing_urls = {
        (item.get("url") or "").strip()
        for item in existing
        if item.get("url")
    }

    new_raw_hits = []
    for raw in all_raw_hits:
        url = (raw.get("url") or "").strip()
        if not url or url in existing_urls:
            continue
        new_raw_hits.append(raw)

    print(f"New URLs not already in archive: {len(new_raw_hits)}")

    new_records: list[dict] = []
    failed: list[dict] = []
    lock = threading.Lock()
    saved_since_flush = 0
    completed = 0
    total = len(new_raw_hits)

    def flush() -> None:
        final_records = build_final_records(existing, new_records)
        save_json(OUT_PATH, final_records)
        save_json(FAILED_URLS_PATH, failed)
        print(
            f"Flushed to disk: +{len(new_records)} new, "
            f"{len(final_records)} total, {len(failed)} failed"
        )

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(process_one, raw, query): raw
            for raw in new_raw_hits
        }

        for future in as_completed(futures):
            article_dict, fail_dict = future.result()
            completed += 1

            with lock:
                if article_dict is not None:
                    new_records.append(article_dict)
                    saved_since_flush += 1
                    print(
                        f"[{completed}/{total}] saved: "
                        f"{article_dict['title'][:90]}"
                    )
                else:
                    failed.append(fail_dict or {"url": "", "error": "unknown error"})
                    url = (fail_dict or {}).get("url", "")
                    err = (fail_dict or {}).get("error", "unknown error")
                    print(f"[{completed}/{total}] skipped: {url} ({err})")

                if saved_since_flush >= args.save_every:
                    flush()
                    saved_since_flush = 0

            if ARTICLE_SLEEP_SECONDS > 0:
                time.sleep(ARTICLE_SLEEP_SECONDS)

    flush()

    print(f"Added {len(new_records)} new articles")
    print(f"Saved failed URL log to {FAILED_URLS_PATH}")


if __name__ == "__main__":
    main()
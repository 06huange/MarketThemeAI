from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

import requests
import trafilatura


GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
COMPANY_CSV = Path("data/company_universe.csv")
OUT_PATH = Path("data/raw/articles.json")

REQUEST_TIMEOUT = 20
ARTICLE_SLEEP_SECONDS = 0.5
GDELT_MIN_INTERVAL_SECONDS = 8
GDELT_RETRY_SLEEP_SECONDS = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

LAST_GDELT_CALL_TS = 0.0


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


def make_article_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")


def load_company_universe(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "company": (row.get("company") or "").strip(),
                "ticker": (row.get("ticker") or "").strip(),
                "group": (row.get("group") or row.get("sector") or "").strip(),
                "keywords": (row.get("keywords") or "").strip(),
            })
    return rows


def clean_term(term: str) -> str:
    return " ".join(term.strip().split())


def quote_term(term: str) -> str:
    term = clean_term(term)
    return f'"{term}"' if term else ""


def extract_company_terms(rows: list[dict], max_companies: int = 8) -> list[str]:
    terms = []
    seen = set()

    for row in rows:
        company = clean_term(row["company"])
        if company and company.lower() not in seen:
            terms.append(company)
            seen.add(company.lower())

        if len(terms) >= max_companies:
            break

    return terms[:max_companies]


def extract_keyword_terms(rows: list[dict], max_keywords: int = 8) -> list[str]:
    priority_terms = [
        "AI accelerator",
        "advanced packaging",
        "CoWoS",
        "HBM",
        "GPU",
        "semiconductor",
        "datacenter",
        "wafer fabrication",
        "lithography",
        "chipmaking",
        "AI server",
        "memory",
    ]

    seen = set()
    terms = []

    for term in priority_terms:
        if term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)

    for row in rows:
        raw_keywords = clean_term(row["keywords"])
        if not raw_keywords:
            continue

        # assume semicolon-separated keywords if available
        if ";" in raw_keywords:
            pieces = [clean_term(x) for x in raw_keywords.split(";")]
        else:
            # fallback: keep whole field only if short enough
            pieces = [raw_keywords] if len(raw_keywords.split()) <= 4 else []

        for piece in pieces:
            if not piece:
                continue
            key = piece.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(piece)

        if len(terms) >= max_keywords:
            break

    return terms[:max_keywords]


def build_gdelt_query(rows: list[dict]) -> str:
    return 'sourcelang:english ("NVIDIA" OR "Intel" OR "Qualcomm" OR "Broadcom" OR "semiconductor" OR "advanced packaging" OR "AI accelerator")'


def wait_for_gdelt_rate_limit() -> None:
    global LAST_GDELT_CALL_TS

    now = time.time()
    elapsed = now - LAST_GDELT_CALL_TS
    wait_time = GDELT_MIN_INTERVAL_SECONDS - elapsed
    if wait_time > 0:
        time.sleep(wait_time)


def call_gdelt(query: str, start_dt: datetime, end_dt: datetime, maxrecords: int = 100) -> list[dict]:
    global LAST_GDELT_CALL_TS

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "DateDesc",
        "maxrecords": maxrecords,
        "STARTDATETIME": fmt_dt(start_dt),
        "ENDDATETIME": fmt_dt(end_dt),
    }
    url = f"{GDELT_BASE}?{urlencode(params)}"

    wait_for_gdelt_rate_limit()
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    LAST_GDELT_CALL_TS = time.time()

    if resp.status_code == 429:
        print("429 from GDELT. Sleeping and retrying once...")
        time.sleep(GDELT_RETRY_SLEEP_SECONDS)
        wait_for_gdelt_rate_limit()
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        LAST_GDELT_CALL_TS = time.time()

    print("STATUS:", resp.status_code)
    print("CONTENT-TYPE:", resp.headers.get("Content-Type"))
    print("RESPONSE PREVIEW:", resp.text[:300])

    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        return []

    try:
        data = resp.json()
    except Exception:
        print("Non-JSON response from GDELT:")
        print(text[:1000])
        return []

    if not isinstance(data, dict):
        print("Unexpected JSON structure:", type(data))
        return []

    return data.get("articles", [])


def extract_text_from_url(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return ""

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
    )
    return text.strip() if text else ""


def normalize_gdelt_article(raw: dict, query: str, text: str) -> Article:
    url = (raw.get("url") or "").strip()
    title = (raw.get("title") or "").strip()
    source = (raw.get("domain") or "").strip()
    date = (raw.get("seendate") or "").strip()
    language = raw.get("language") or raw.get("sourceLanguage")

    return Article(
        article_id=make_article_id(url),
        date=date,
        title=title,
        text=text,
        source=source,
        url=url,
        query=query,
        language=language,
    )


def daterange_chunks(start_dt: datetime, end_dt: datetime, chunk_days: int) -> Iterable[tuple[datetime, datetime]]:
    cur = start_dt
    while cur < end_dt:
        nxt = min(cur + timedelta(days=chunk_days), end_dt)
        yield cur, nxt
        cur = nxt


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


def load_existing_articles(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_articles(path: Path, articles: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


def main() -> None:
    rows = load_company_universe(COMPANY_CSV)
    query = build_gdelt_query(rows)

    print("GDELT query:")
    print(query)

    # start small while testing
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30)

    all_raw_hits: list[dict] = []
    for chunk_start, chunk_end in daterange_chunks(start_dt, end_dt, chunk_days=1):
        try:
            hits = call_gdelt(query, chunk_start, chunk_end, maxrecords=100)
        except Exception as e:
            print(f"Failed for window {chunk_start} -> {chunk_end}: {e}")
            continue

        all_raw_hits.extend(hits)
        print(f"{chunk_start.date()} -> {chunk_end.date()}: {len(hits)} hits")

    all_raw_hits = dedupe_by_url(all_raw_hits)
    print(f"Unique URLs from GDELT: {len(all_raw_hits)}")

    records: list[dict] = []
    for i, raw in enumerate(all_raw_hits, start=1):
        url = (raw.get("url") or "").strip()
        if not url:
            continue

        try:
            text = extract_text_from_url(url)
        except Exception as e:
            print(f"Text extraction failed for {url}: {e}")
            text = ""

        if not text:
            continue

        article = normalize_gdelt_article(raw, query=query, text=text)
        if not article.title or not article.url:
            continue

        records.append(asdict(article))
        print(f"[{i}/{len(all_raw_hits)}] saved: {article.title[:90]}")
        time.sleep(ARTICLE_SLEEP_SECONDS)

    existing = load_existing_articles(OUT_PATH)
    by_id = {item["article_id"]: item for item in existing}
    for item in records:
        by_id[item["article_id"]] = item

    final_records = sorted(by_id.values(), key=lambda x: x["date"], reverse=True)
    save_articles(OUT_PATH, final_records)

    print(f"Saved {len(final_records)} total articles to {OUT_PATH}")


if __name__ == "__main__":
    main()
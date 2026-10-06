"""Run the GDELT GKG query in BigQuery and save the hits as the CSV that ingestion reads.

Replaces the manual "run gkg_query.sql in the console and export a CSV" step.
Needs Google Cloud credentials (`gcloud auth application-default login` locally,
or GOOGLE_APPLICATION_CREDENTIALS in automation) and a GCP project to bill
queries to (GOOGLE_CLOUD_PROJECT).
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

QUERY_PATH = Path(__file__).with_name("gkg_query.sql")
OUT_PATH = Path("data/raw/gdelt_bq_articles.csv")

DEFAULT_DAYS = 8
# The GKG table is large and billed by bytes scanned. Refuse to run a query that
# would scan more than this, so a typo in --days can't burn the free tier.
DEFAULT_MAX_GB = 150

COLUMNS = ["DATE", "SourceCommonName", "url", "V2Organizations", "V2Themes", "TranslationInfo"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Days of news to query.")
    parser.add_argument("--max-gb", type=float, default=DEFAULT_MAX_GB, help="Abort if the query would scan more than this.")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    return parser.parse_args()


def main() -> None:
    from google.cloud import bigquery

    args = parse_args()
    client = bigquery.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    sql = QUERY_PATH.read_text(encoding="utf-8")
    params = [bigquery.ScalarQueryParameter("days", "INT64", args.days)]

    dry_run = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=params, dry_run=True, use_query_cache=False),
    )
    scan_gb = dry_run.total_bytes_processed / 1e9
    print(f"Query will scan {scan_gb:.1f} GB for the last {args.days} days")
    if scan_gb > args.max_gb:
        raise SystemExit(f"Refusing to run: {scan_gb:.1f} GB > --max-gb {args.max_gb}")

    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=params,
            maximum_bytes_billed=int(args.max_gb * 1e9),
        ),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in job.result():
            writer.writerow({col: row.get(col) for col in COLUMNS})
            count += 1

    print(f"Saved {count} article URLs to {args.out}")


if __name__ == "__main__":
    main()

"""Sync pipeline state with S3 so a fresh container can pick up where the last run left off.

Layout in the bucket:
    s3://<bucket>/data/...        pipeline state (article archive, embedding cache, themes)
    s3://<bucket>/dashboard/...   the export the API serves

Credentials come from the environment (the ECS task role in AWS, your profile locally).
"""

from __future__ import annotations

from pathlib import Path

STATE_DIR = Path("data")
STATE_PREFIX = "data"
DASHBOARD_DIR = Path("frontend/public/data")
DASHBOARD_PREFIX = "dashboard"


def _client():
    import boto3

    return boto3.client("s3")


def download_prefix(bucket: str, prefix: str, dest: Path) -> int:
    s3 = _client()
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{prefix}/"):
        for obj in page.get("Contents", []):
            target = dest / obj["Key"].removeprefix(f"{prefix}/")
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, obj["Key"], str(target))
            count += 1
    return count


def upload_dir(src: Path, bucket: str, prefix: str) -> int:
    s3 = _client()
    count = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        key = f"{prefix}/{path.relative_to(src).as_posix()}"
        extra = {"ContentType": "application/json"} if path.suffix == ".json" else {}
        s3.upload_file(str(path), bucket, key, ExtraArgs=extra)
        count += 1
    return count


def pull_state(bucket: str) -> None:
    print(f"Pulled {download_prefix(bucket, STATE_PREFIX, STATE_DIR)} state files from s3://{bucket}/{STATE_PREFIX}/")


def push_state(bucket: str) -> None:
    print(f"Pushed {upload_dir(STATE_DIR, bucket, STATE_PREFIX)} state files to s3://{bucket}/{STATE_PREFIX}/")
    print(f"Published {upload_dir(DASHBOARD_DIR, bucket, DASHBOARD_PREFIX)} dashboard files to s3://{bucket}/{DASHBOARD_PREFIX}/")

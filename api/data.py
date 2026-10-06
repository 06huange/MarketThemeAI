"""Loads the pipeline's dashboard export from a local folder or S3.

DATA_URI selects the source:
    frontend/public/data          local folder (default, for development)
    s3://bucket/prefix            S3 (Lambda reads through its IAM role, no keys)

The export is a few hundred KB and only changes weekly, so it's cached in memory
for CACHE_TTL_SECONDS; warm Lambda invocations don't refetch it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DASHBOARD_FILE = "dashboard.json"


def read_dashboard(data_uri: str) -> dict[str, Any]:
    if data_uri.startswith("s3://"):
        import boto3

        bucket, _, prefix = data_uri.removeprefix("s3://").partition("/")
        key = f"{prefix.rstrip('/')}/{DASHBOARD_FILE}" if prefix else DASHBOARD_FILE
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)

    return json.loads((Path(data_uri) / DASHBOARD_FILE).read_text(encoding="utf-8"))


class DashboardStore:
    def __init__(self, data_uri: str | None = None, ttl_seconds: float | None = None):
        self.data_uri = data_uri or os.environ.get("DATA_URI", "frontend/public/data")
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else float(os.environ.get("CACHE_TTL_SECONDS", "300"))
        self._data: dict[str, Any] | None = None
        self._themes_by_id: dict[str, dict] = {}
        self._loaded_at = 0.0

    def get(self) -> dict[str, Any]:
        if self._data is None or time.monotonic() - self._loaded_at > self.ttl_seconds:
            data = read_dashboard(self.data_uri)
            self._themes_by_id = {t["theme_id"]: t for t in data.get("themes", [])}
            self._data = data
            self._loaded_at = time.monotonic()
        return self._data

    def theme(self, theme_id: str) -> dict | None:
        self.get()
        return self._themes_by_id.get(theme_id)

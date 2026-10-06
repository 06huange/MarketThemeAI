"""Read API over the weekly theme data.

    uvicorn api.main:app --reload --port 8000

The same container runs locally and on AWS Lambda (via the Lambda Web Adapter).
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.data import DashboardStore

app = FastAPI(
    title="MarketThemeAI API",
    description="Weekly AI and semiconductor market themes discovered from news coverage.",
    version=os.environ.get("APP_VERSION", "dev"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)

store = DashboardStore()

Status = Literal["all", "emerging", "new", "continuing"]
MAX_TRAJECTORY_STEPS = 52


@app.get("/health")
def health() -> dict:
    """Liveness check. Deliberately doesn't touch the data store."""
    return {"status": "ok", "version": app.version}


@app.get("/dashboard")
def dashboard() -> dict:
    """The full export in the shape the frontend has always consumed."""
    return store.get()


@app.get("/weeks")
def weeks() -> dict:
    return {"weeks": store.get()["weeks"]}


@app.get("/stats")
def stats() -> dict:
    return store.get()["stats"]


def matches_status(theme: dict, status: Status) -> bool:
    if status == "emerging":
        return bool(theme.get("is_emerging"))
    if status == "new":
        return bool(theme.get("is_new_theme"))
    if status == "continuing":
        return theme.get("previous_theme_id") is not None
    return True


def matches_query(theme: dict, q: str) -> bool:
    haystack = " ".join(
        [theme.get("label", "")]
        + theme.get("top_companies", [])
        + theme.get("top_keywords", [])
        + theme.get("example_titles", [])
    ).lower()
    return q.lower() in haystack


@app.get("/themes")
def themes(
    week: str | None = None,
    status: Status = "all",
    company: str | None = Query(None, description="Exact company name, e.g. NVIDIA"),
    q: str | None = Query(None, description="Text search over labels, companies, keywords, headlines"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    results = [
        t
        for t in store.get()["themes"]
        if (week is None or t.get("week") == week)
        and matches_status(t, status)
        and (company is None or company in t.get("top_companies", []))
        and (q is None or matches_query(t, q))
    ]
    results.sort(key=lambda t: (t.get("emerging_score", 0), t.get("size", 0)), reverse=True)
    return {"total": len(results), "themes": results[offset : offset + limit]}


@app.get("/themes/{theme_id}")
def theme_detail(theme_id: str) -> dict:
    theme = store.theme(theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail=f"Unknown theme {theme_id!r}")
    return {"theme": theme, "trajectory": trajectory(theme)}


def trajectory(theme: dict) -> list[dict]:
    """The theme's history across weeks: earlier versions, itself, then later ones."""
    summary = lambda t: {k: t.get(k) for k in ("theme_id", "week", "label", "size", "emerging_score")}

    earlier = []
    current = theme
    while (prev_id := current.get("previous_theme_id")) and len(earlier) < MAX_TRAJECTORY_STEPS:
        current = store.theme(prev_id)
        if current is None:
            break
        earlier.append(summary(current))

    later = []
    current = theme
    while current.get("next_theme_ids") and len(later) < MAX_TRAJECTORY_STEPS:
        current = store.theme(current["next_theme_ids"][0])
        if current is None:
            break
        later.append(summary(current))

    return list(reversed(earlier)) + [summary(theme)] + later

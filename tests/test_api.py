import json

import pytest
from fastapi.testclient import TestClient

import api.main
from api.data import DashboardStore


def theme(theme_id, week, *, size=10, score=0.5, new=False, emerging=False, prev=None, nxt=(), companies=("NVIDIA",)):
    return {
        "theme_id": theme_id,
        "week": week,
        "label": f"label {theme_id}",
        "size": size,
        "top_companies": list(companies),
        "top_keywords": ["hbm"],
        "example_titles": [f"headline {theme_id}"],
        "previous_theme_id": prev,
        "next_theme_ids": list(nxt),
        "is_new_theme": new,
        "is_emerging": emerging,
        "emerging_score": score,
    }


DASHBOARD = {
    "weeks": ["W1", "W2", "W3"],
    "stats": {"num_weeks": 3, "total_themes": 4},
    "themes": [
        theme("w1_a", "W1", nxt=["w2_a"]),
        theme("w2_a", "W2", prev="w1_a", nxt=["w3_a"], emerging=True, score=0.9),
        theme("w3_a", "W3", prev="w2_a"),
        theme("w3_b", "W3", new=True, emerging=True, score=0.7, companies=("TSMC",)),
    ],
    "emerging": [],
    "links": [],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "dashboard.json").write_text(json.dumps(DASHBOARD))
    monkeypatch.setattr(api.main, "store", DashboardStore(str(tmp_path), ttl_seconds=60))
    return TestClient(api.main.app)


def ids(response):
    return [t["theme_id"] for t in response.json()["themes"]]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_returns_full_export(client):
    assert client.get("/dashboard").json() == DASHBOARD


def test_weeks_and_stats(client):
    assert client.get("/weeks").json() == {"weeks": ["W1", "W2", "W3"]}
    assert client.get("/stats").json()["total_themes"] == 4


def test_themes_sorted_by_emerging_score(client):
    response = client.get("/themes")

    assert response.json()["total"] == 4
    assert ids(response)[:2] == ["w2_a", "w3_b"]


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"week": "W3"}, {"w3_a", "w3_b"}),
        ({"status": "new"}, {"w3_b"}),
        ({"status": "emerging"}, {"w2_a", "w3_b"}),
        ({"status": "continuing"}, {"w2_a", "w3_a"}),
        ({"company": "TSMC"}, {"w3_b"}),
        ({"q": "headline w1"}, {"w1_a"}),
    ],
)
def test_theme_filters(client, params, expected):
    assert set(ids(client.get("/themes", params=params))) == expected


def test_pagination(client):
    page = client.get("/themes", params={"limit": 1, "offset": 1}).json()

    assert page["total"] == 4
    assert [t["theme_id"] for t in page["themes"]] == ["w3_b"]


def test_invalid_status_is_rejected(client):
    assert client.get("/themes", params={"status": "trending"}).status_code == 422


def test_theme_detail_includes_full_trajectory(client):
    body = client.get("/themes/w2_a").json()

    assert body["theme"]["theme_id"] == "w2_a"
    assert [step["theme_id"] for step in body["trajectory"]] == ["w1_a", "w2_a", "w3_a"]


def test_unknown_theme_is_404(client):
    assert client.get("/themes/nope").status_code == 404


def test_store_caches_until_ttl(tmp_path):
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(DASHBOARD))
    store = DashboardStore(str(tmp_path), ttl_seconds=60)
    store.get()

    path.write_text(json.dumps({**DASHBOARD, "weeks": ["changed"]}))

    assert store.get()["weeks"] == ["W1", "W2", "W3"]

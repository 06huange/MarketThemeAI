import numpy as np

from src.track.link_themes_over_time import build_links_between_weeks


def theme(theme_id: str, vector: list[float], size: int = 10) -> dict:
    v = np.asarray(vector, dtype=float)
    return {"theme_id": theme_id, "label": theme_id, "size": size, "centroid": v / np.linalg.norm(v)}


def test_links_similar_themes_one_to_one():
    prev = [theme("p_hbm", [1, 0, 0]), theme("p_export", [0, 1, 0])]
    curr = [theme("c_hbm", [0.95, 0.05, 0]), theme("c_hbm_dupe", [0.9, 0.1, 0]), theme("c_new", [0, 0, 1])]

    links = build_links_between_weeks("W1", prev, "W2", curr, threshold=0.72, max_links_per_theme=1)

    assert [(l["from_theme_id"], l["to_theme_id"]) for l in links] == [("p_hbm", "c_hbm")]


def test_no_links_below_threshold():
    prev = [theme("p", [1, 0])]
    curr = [theme("c", [0.5, 0.5])]  # cosine ~0.71

    assert build_links_between_weeks("W1", prev, "W2", curr, threshold=0.72, max_links_per_theme=1) == []


def test_empty_week_produces_no_links():
    assert build_links_between_weeks("W1", [], "W2", [theme("c", [1, 0])], 0.72, 1) == []

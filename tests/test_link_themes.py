import numpy as np

from src.track.link_themes_over_time import build_links, center_centroids


def theme(theme_id: str, week: str, vector: list[float], size: int = 10) -> dict:
    v = np.asarray(vector, dtype=float)
    return {"theme_id": theme_id, "week": week, "label": theme_id, "size": size, "centroid": v / np.linalg.norm(v)}


def pairs(links):
    return [(l["from_theme_id"], l["to_theme_id"]) for l in links]


def test_links_each_theme_to_its_most_similar_predecessor():
    weekly = [
        ("W1", [theme("p_hbm", "W1", [1, 0, 0]), theme("p_export", "W1", [0, 1, 0])]),
        ("W2", [theme("c_hbm", "W2", [0.95, 0.05, 0]), theme("c_new", "W2", [0, 0, 1])]),
    ]

    assert pairs(build_links(weekly, threshold=0.7)) == [("p_hbm", "c_hbm")]


def test_a_story_can_split_into_several_themes():
    weekly = [
        ("W1", [theme("p", "W1", [1, 0])]),
        ("W2", [theme("c1", "W2", [0.95, 0.05]), theme("c2", "W2", [0.9, 0.1])]),
    ]

    assert pairs(build_links(weekly, threshold=0.7)) == [("p", "c1"), ("p", "c2")]


def test_looks_back_past_a_week_without_the_story():
    weekly = [
        ("W1", [theme("terafab", "W1", [1, 0, 0])]),
        ("W2", [theme("other", "W2", [0, 1, 0])]),
        ("W3", [theme("terafab_again", "W3", [0.95, 0.05, 0])]),
    ]

    assert pairs(build_links(weekly, threshold=0.7, lookback=2)) == [("terafab", "terafab_again")]
    assert build_links(weekly, threshold=0.7, lookback=1) == []


def test_no_links_below_threshold():
    weekly = [("W1", [theme("p", "W1", [1, 0])]), ("W2", [theme("c", "W2", [0.5, 0.5])])]  # cosine ~0.71

    assert build_links(weekly, threshold=0.72) == []


def test_centering_removes_the_direction_all_themes_share():
    # Every theme leans heavily on the first axis ("this is about AI"), which makes
    # unrelated themes look alike until the shared component is removed.
    weekly = [("W1", [theme("a", "W1", [5, 1, 0]), theme("b", "W1", [5, 0, 1])])]
    a, b = weekly[0][1]
    assert a["centroid"] @ b["centroid"] > 0.9

    center_centroids(weekly)

    assert a["centroid"] @ b["centroid"] < 0

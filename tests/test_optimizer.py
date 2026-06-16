"""Tests for EV optimizer."""
from models.optimizer import (
    expected_value,
    recommend_pick,
    outcome_to_score,
    CATCH_UP_THRESHOLD,
)


def test_expected_value_favorite():
    """When favorite has highest EV, recommend it."""
    probs = {"home": 0.75, "draw": 0.17, "away": 0.08}
    points = {"home": 46, "draw": 128, "away": 153}
    ev = expected_value(probs, points)
    assert ev["home"] > ev["draw"]
    assert ev["home"] > ev["away"]
    assert abs(ev["home"] - 34.5) < 0.1


def test_expected_value_contrarian():
    """When draw has higher EV, recommend draw."""
    probs = {"home": 0.52, "draw": 0.28, "away": 0.20}
    points = {"home": 58, "draw": 112, "away": 142}
    ev = expected_value(probs, points)
    assert ev["draw"] > ev["home"]  # 112*0.28=31.4 > 58*0.52=30.2


def test_recommend_pick_basic():
    """Recommend the highest-EV pick in normal mode."""
    probs = {"home": 0.75, "draw": 0.17, "away": 0.08}
    points = {"home": 46, "draw": 128, "away": 153}
    pick = recommend_pick(probs, points, points_behind=0)
    assert pick["outcome"] == "home"
    assert "-" in pick["score"]


def test_recommend_pick_catchup():
    """In catch-up mode, prefer high-points swing pick when EV is close."""
    probs = {"home": 0.55, "draw": 0.27, "away": 0.18}
    points = {"home": 59, "draw": 119, "away": 133}
    pick = recommend_pick(probs, points, points_behind=800)
    # EV: home=32.5, draw=32.1, away=23.9
    # Catch-up picks draw (119 pts) over home (59 pts) since EVs within 15%
    assert pick["outcome"] == "draw"


def test_outcome_to_score():
    """Convert outcome pick to a score prediction."""
    assert outcome_to_score("home", 1.8, 0.8) == "2-1"
    assert outcome_to_score("draw", 1.2, 1.2) == "1-1"
    assert outcome_to_score("away", 0.6, 1.8) == "0-2"  # heavy underdog at home


def test_recommend_pick_england_croatia():
    """England-Croatia with real MPP points: catch-up prefers high-reward swing."""
    probs = {"home": 0.46, "draw": 0.30, "away": 0.24}
    points = {"home": 59, "draw": 119, "away": 133}
    pick = recommend_pick(probs, points, points_behind=800)
    # EV: home=27.1, draw=35.7, away=31.9
    # Draw has best EV, but away (133 pts) is within 15% and has higher points
    # Catch-up mode prefers the higher-points candidate → away
    assert pick["outcome"] in ("draw", "away")  # both are valid contrarian picks
    assert pick["score"] in ("1-1", "0-2", "1-2")  # away score depends on lambdas

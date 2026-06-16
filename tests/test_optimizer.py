"""Tests for EV optimizer with rarity bonuses and double points."""
from models.optimizer import (
    expected_value,
    recommend_pick,
    outcome_to_score,
    estimate_bonus,
    recommend_double_match,
    CATCH_UP_THRESHOLD,
    EXACT_SCORE_BONUS,
    RARITY_TIERS,
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
    assert outcome_to_score("away", 0.6, 1.8) == "0-2"


def test_recommend_pick_england_croatia():
    """England-Croatia: catch-up prefers high-reward swing."""
    probs = {"home": 0.46, "draw": 0.30, "away": 0.24}
    points = {"home": 59, "draw": 119, "away": 133}
    pick = recommend_pick(probs, points, points_behind=800)
    assert pick["outcome"] in ("draw", "away")
    assert pick["score"] in ("1-1", "0-2", "1-2")


# --- NEW: Rarity bonus tests ---

def test_estimate_bonus_mega_rare():
    """1% crowd → megaRare +200."""
    name, pts = estimate_bonus(0.01)
    assert name == "megaRare"
    assert pts == 200


def test_estimate_bonus_ultra_rare():
    """4% crowd → ultraRare +100."""
    name, pts = estimate_bonus(0.04)
    assert name == "ultraRare"
    assert pts == 100


def test_estimate_bonus_rare():
    """8% crowd → rare +50."""
    name, pts = estimate_bonus(0.08)
    assert name == "rare"
    assert pts == 50


def test_estimate_bonus_very_rare():
    """12% crowd → veryRare +25."""
    name, pts = estimate_bonus(0.12)
    assert name == "veryRare"
    assert pts == 25


def test_estimate_bonus_none():
    """20% crowd → no bonus."""
    name, pts = estimate_bonus(0.20)
    assert name is None
    assert pts == 0


def test_ev_with_rarity_bonus():
    """EV should include rarity bonus when crowd data available."""
    probs = {"home": 0.75, "draw": 0.17, "away": 0.08}
    points = {"home": 46, "draw": 128, "away": 153}
    crowd = {"home": 0.88, "draw": 0.09, "away": 0.03}  # away is 3% → ultraRare

    ev_no_bonus = expected_value(probs, points)
    ev_with_bonus = expected_value(probs, points, crowd)

    # Away EV should be higher with rarity bonus
    assert ev_with_bonus["away"] > ev_no_bonus["away"]
    # 8% × 153 base + 8% × 100 bonus = 12.24 + 8.0 = 20.24
    assert abs(ev_with_bonus["away"] - 20.24) < 0.2


def test_recommend_pick_with_crowd():
    """Pick should include bonus info when crowd data available."""
    probs = {"home": 0.50, "draw": 0.25, "away": 0.25}
    points = {"home": 46, "draw": 128, "away": 153}
    crowd = {"home": 0.88, "draw": 0.09, "away": 0.03}  # away=3%=ultraRare, draw=9%=rare

    pick = recommend_pick(probs, points, crowd_pcts=crowd)
    assert pick["outcome"] == "away"  # EV: 38.25 base + 25 bonus = 63.25
    assert pick["bonus_name"] == "ultraRare"
    assert pick["bonus_points"] == 100
    assert pick["total_possible"] == 153 + 100 + EXACT_SCORE_BONUS  # base + bonus + exact


def test_double_points():
    """Double points should multiply EV and total_possible by 2."""
    probs = {"home": 0.50, "draw": 0.25, "away": 0.25}
    points = {"home": 46, "draw": 128, "away": 153}
    crowd = {"home": 0.88, "draw": 0.09, "away": 0.03}

    normal = recommend_pick(probs, points, crowd_pcts=crowd, double_match=False)
    doubled = recommend_pick(probs, points, crowd_pcts=crowd, double_match=True)

    assert doubled["ev"] == normal["ev"] * 2
    assert doubled["total_possible"] == normal["total_possible"] * 2
    assert doubled["doubled"] is True
    assert normal["doubled"] is False


def test_rarity_tiers_ordered():
    """Rarity tiers should be ordered from most to least rare."""
    for i in range(len(RARITY_TIERS) - 1):
        assert RARITY_TIERS[i][0] < RARITY_TIERS[i + 1][0]
        assert RARITY_TIERS[i][2] > RARITY_TIERS[i + 1][2]

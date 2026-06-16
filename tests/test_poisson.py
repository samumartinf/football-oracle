"""Tests for Poisson goal model."""
import math
from models.poisson import (
    expected_goals,
    score_probability,
    match_probabilities,
    MAX_GOALS,
)

def test_expected_goals_equal():
    """Equal teams should have similar expected goals around 1.4 each."""
    home_lambda, away_lambda = expected_goals(1500, 1500)
    assert 1.2 < home_lambda < 1.7, f"home λ={home_lambda}"
    assert 1.0 < away_lambda < 1.4, f"away λ={away_lambda}"

def test_expected_goals_favorite():
    """Stronger team should have more expected goals."""
    home_lambda, away_lambda = expected_goals(1800, 1500)
    assert home_lambda > away_lambda
    assert home_lambda > 1.8

def test_score_probability_sums():
    """Score probability matrix should sum to ~1."""
    probs = score_probability(1.5, 1.2)
    total = sum(sum(row) for row in probs)
    assert 0.98 < total < 1.01, f"total={total:.4f}"

def test_match_probabilities_shape():
    """match_probabilities should return home/draw/away."""
    probs = match_probabilities(1500, 1500)
    assert "home" in probs and "draw" in probs and "away" in probs
    total = probs["home"] + probs["draw"] + probs["away"]
    assert abs(total - 1.0) < 0.01

def test_strong_favorite_high_win_prob():
    """France (1720) vs Qatar (1502) should give clear home win prob."""
    probs = match_probabilities(1720, 1502)
    assert probs["home"] > 0.50, f"home={probs['home']}"
    assert probs["away"] < 0.25, f"away={probs['away']}"
    assert probs["home"] > probs["draw"] > probs["away"]

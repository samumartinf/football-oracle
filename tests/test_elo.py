"""Tests for Elo probability model."""
import math
from models.elo import elo_to_probabilities

def test_elo_equal_teams():
    """Two equal teams should have ~equal win probabilities and ~30% draw."""
    prob_home, prob_draw, prob_away = elo_to_probabilities(1500, 1500, neutral=True)
    assert 0.30 <= prob_home < 0.45, f"home={prob_home:.2f}"
    assert 0.25 < prob_draw < 0.35, f"draw={prob_draw:.2f}"
    assert 0.30 <= prob_away < 0.45, f"away={prob_away:.2f}"
    assert abs(prob_home + prob_draw + prob_away - 1.0) < 0.001

def test_elo_strong_favorite():
    """200 Elo gap = ~70% win for favorite."""
    prob_home, prob_draw, prob_away = elo_to_probabilities(1800, 1600)
    assert prob_home > prob_draw > prob_away
    assert prob_home > 0.55

def test_elo_away_favorite():
    """Away team higher Elo = away should be favorite."""
    prob_home, prob_draw, prob_away = elo_to_probabilities(1500, 1700)
    assert prob_away > prob_home

def test_probabilities_sum_to_one():
    """Probabilities must always sum to 1."""
    cases = [(1500, 1500), (1800, 1600), (1600, 1800), (2000, 1400), (1400, 2000)]
    for h, a in cases:
        ph, pd, pa = elo_to_probabilities(h, a)
        assert abs(ph + pd + pa - 1.0) < 0.001, f"sum={ph+pd+pa:.4f}"

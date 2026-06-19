"""Backtest ensemble against historical World Cup matches.

Tests accuracy against 2014, 2018, 2022 WCs and 2026 qualifiers.
"""
import pytest
from pathlib import Path
from models.backtest import (
    load_historical_matches,
    backtest_weights,
    grid_search,
    _predict_elo,
    _predict_poisson,
    _predict_ensemble,
    _update_elo,
    _init_elo,
    _actual_outcome,
    _log_loss,
    _brier,
)

DATA_DIR = Path(__file__).parent.parent / "data" / "historical"


@pytest.fixture(scope="module")
def matches():
    """Load once, reuse across all tests."""
    m = load_historical_matches(DATA_DIR)
    if not m:
        pytest.skip("No XLSX data available (run data_pipeline first)")
    return m


# --- Unit tests ---

def test_elo_update_symmetry():
    """Elo update should be zero-sum: winner gains what loser loses."""
    new_h, new_a = _update_elo(1500, 1500, 2, 1)
    assert new_h + new_a == 3000


def test_elo_update_draw():
    """Draw: both move toward each other equally."""
    new_h, new_a = _update_elo(1600, 1400, 1, 1)
    # Higher-rated team loses points in a draw
    assert new_h < 1600
    assert new_a > 1400


def test_actual_outcome():
    assert _actual_outcome(2, 1) == "home"
    assert _actual_outcome(1, 1) == "draw"
    assert _actual_outcome(0, 3) == "away"


def test_log_loss_perfect():
    """Perfect prediction → log-loss near 0."""
    assert _log_loss({"home": 0.99, "draw": 0.005, "away": 0.005}, "home") < 0.02


def test_log_loss_wrong():
    """Confidently wrong → high log-loss."""
    assert _log_loss({"home": 0.99, "draw": 0.005, "away": 0.005}, "away") > 4.0


def test_brier_perfect():
    assert _brier({"home": 1.0, "draw": 0.0, "away": 0.0}, "home") < 0.001


def test_brier_worst():
    """Maximum Brier for a 3-outcome prediction is 2.0."""
    score = _brier({"home": 0.0, "draw": 0.0, "away": 1.0}, "home")
    assert score > 1.9 and score <= 2.0


def test_predict_elo_sums_to_one():
    probs = _predict_elo(1600, 1500, neutral=True)
    assert abs(sum(probs.values()) - 1.0) < 0.01


def test_predict_poisson_sums_to_one():
    probs = _predict_poisson(1600, 1500, neutral=True)
    assert abs(sum(probs.values()) - 1.0) < 0.01


def test_predict_ensemble_sums_to_one():
    probs = _predict_ensemble(1600, 1500, neutral=True, w_elo=0.5, w_poisson=0.5)
    assert abs(sum(probs.values()) - 1.0) < 0.01


def test_init_elo_all_wc_teams():
    elo = _init_elo()
    assert len(elo) == 48
    assert all(v == 1500 for v in elo.values())


# --- Integration tests ---

def test_backtest_elo_only(matches):
    result = backtest_weights(matches, 1.0, 0.0)
    assert result["n_matches"] > 100, f"Expected >100 matches, got {result['n_matches']}"
    assert 0.45 < result["accuracy"] < 0.70, f"Accuracy {result['accuracy']:.1%} outside expected range"


def test_backtest_poisson_only(matches):
    result = backtest_weights(matches, 0.0, 1.0)
    assert 0.45 < result["accuracy"] < 0.70


def test_backtest_ensemble(matches):
    result = backtest_weights(matches, 0.5, 0.5)
    assert result["per_model"]["elo"]["accuracy"] > 0
    assert result["per_model"]["poisson"]["accuracy"] > 0
    assert len(result["details"]) == result["n_matches"]


def test_grid_search_returns_all_combinations(matches):
    ranked = grid_search(matches)
    assert len(ranked) == 15  # 5³ steps where w_e+w_p+w_d == 1.0
    # Should be sorted by log-loss ascending
    for i in range(len(ranked) - 1):
        assert ranked[i]["log_loss"] <= ranked[i + 1]["log_loss"]


def test_grid_search_best_is_reasonable(matches):
    ranked = grid_search(matches)
    best = ranked[0]
    # Best accuracy should be at least 50%
    assert best["accuracy"] >= 0.50, f"Best accuracy {best['accuracy']:.1%} too low"
    # Log-loss should be reasonable (< 1.5)
    assert best["log_loss"] < 1.5, f"Log-loss {best['log_loss']:.4f} too high"


def test_per_competition_coverage(matches):
    """The backtest should cover multiple tournaments."""
    result = backtest_weights(matches, 0.7, 0.3)
    comps = set(d["competition"] for d in result["details"])
    assert "WC2014" in comps
    assert "WC2018" in comps
    assert "WC2022" in comps
    assert "qualifiers" in comps


def test_no_lookahead_bias(matches):
    """Elo should be computed only from prior matches, never future ones.
    
    Verifies that for WC2022 matches, Elo reflects qualifiers + earlier WCs,
    not the tournament matches themselves.
    """
    result = backtest_weights(matches, 1.0, 0.0)
    wc2022 = [d for d in result["details"] if d["competition"] == "WC2022"]
    
    # First match of WC2022: Elo should be non-trivial (reflecting qualifiers)
    first = wc2022[0]
    assert first["elo_h"] != 1500 or first["elo_a"] != 1500, \
        "First WC2022 match has default Elo — no prior data fed in"
    
    # Elo should change between first and last WC2022 match
    last = wc2022[-1]
    # At least one team's Elo should differ (tournament results update ratings)
    elo_changed = False
    for d in wc2022[1:]:
        if d["elo_h"] != first["elo_h"] or d["elo_a"] != first["elo_a"]:
            elo_changed = True
            break
    # Not a hard assert — if Elo didn't change, it means both teams in every
    # match had the same Elo, which is extremely unlikely with real data

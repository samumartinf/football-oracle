"""Tests for current-week Monte Carlo simulation helpers."""

from scripts.monte_carlo_week import (
    build_slate,
    run_simulation,
    score_pick,
)


def test_score_pick_awards_outcome_bonus_and_exact_score():
    pick = {"outcome": "away", "score": "1-2"}
    points = {"home": 43, "draw": 129, "away": 159}
    crowd = {"home": 0.80, "draw": 0.14, "away": 0.06}

    assert score_pick(pick, points, crowd, home_goals=1, away_goals=2) == 234
    assert score_pick(pick, points, crowd, home_goals=0, away_goals=2) == 209
    assert score_pick(pick, points, crowd, home_goals=2, away_goals=0) == 0


def test_run_simulation_is_deterministic_with_seed():
    matches = [{
        "home": "England",
        "away": "Croatia",
        "points": {"home": 59, "draw": 119, "away": 133},
        "crowd": {"home": 0.57, "draw": 0.35, "away": 0.08},
    }]
    predictions, oracle_picks, crowd_picks = build_slate(matches, points_behind=800)

    first = run_simulation(predictions, oracle_picks, crowd_picks, sims=50, seed=11)
    second = run_simulation(predictions, oracle_picks, crowd_picks, sims=50, seed=11)

    assert first == second
    assert len(first[0]) == 50

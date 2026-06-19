#!/usr/bin/env python3
"""Backtest the Oracle against all completed WC2026 matches.

Runs the model on every completed match from the tournament start,
showing what the Oracle would have picked vs what happened.

For a proper backtest without lookahead bias, this uses the pre-tournament
dataset snapshots (_pre_elo_*, _pre_gf_*, etc.) to reconstruct team strengths
at tournament start, then updates chronologically.

Usage:
    cd ~/src/football-oracle
    .venv/bin/python scripts/backtest_full_tournament.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.ensemble import EnsemblePredictor, load_dataset, normalize_team_name
from models.optimizer import recommend_pick, estimate_bonus, outcome_to_score

OUTCOMES = ("home", "draw", "away")


def load_completed_matches():
    """Load all completed WC2026 matches from MPP API."""
    try:
        from mpp.results import get_completed_matches
        return get_completed_matches()
    except Exception as e:
        print(f"Could not fetch MPP results: {e}")
        return []


def restore_pre_tournament_dataset():
    """Rebuild the dataset as it was at tournament start using _pre_* snapshots."""
    full = load_dataset()
    pre = {}
    for team, entry in full.items():
        if team.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue
        pre[team] = {
            "name": entry.get("name", team),
            "elo": full.get(f"_pre_elo_{team}", entry.get("elo", 1500)),
            "goals_for": full.get(f"_pre_gf_{team}", 0),
            "goals_against": full.get(f"_pre_ga_{team}", 0),
            "matches_played": full.get(f"_pre_mp_{team}", 0),
        }
        if "market_prob" in entry:
            pre[team]["market_prob"] = entry["market_prob"]
    return pre


def update_dataset(dataset, home, away, hg, ag):
    """Update dataset in-place with a completed match result (chronological)."""
    for team, gf, ga in [(home, hg, ag), (away, ag, hg)]:
        if team not in dataset:
            dataset[team] = {"name": team, "elo": 1500, "goals_for": 0, "goals_against": 0, "matches_played": 0}
        d = dataset[team]
        d["matches_played"] = d.get("matches_played", 0) + 1
        d["goals_for"] = d.get("goals_for", 0) + gf
        d["goals_against"] = d.get("goals_against", 0) + ga


def predict_match(predictor, dataset, home, away, points, crowd):
    """Predict a single match and return the pick."""
    dataset_home = normalize_team_name(home)
    dataset_away = normalize_team_name(away)

    result = predictor.predict(home, away, neutral=True)
    probs = {k: result[k] for k in OUTCOMES}

    # Get lambdas (same logic as predict.py)
    for model_name in ("poisson", "decomposed", "xg"):
        if model_name in result.get("models", {}):
            m = result["models"][model_name]
            probs["home_lambda"] = m.get("home_lambda", probs.get("home_lambda", 1.4))
            probs["away_lambda"] = m.get("away_lambda", probs.get("away_lambda", 1.1))

    home_mp = dataset.get(dataset_home, {}).get("matches_played", 0)
    away_mp = dataset.get(dataset_away, {}).get("matches_played", 0)
    home_elo = dataset.get(dataset_home, {}).get("elo", 1500)
    away_elo = dataset.get(dataset_away, {}).get("elo", 1500)
    elo_gap = abs(home_elo - away_elo)
    avg = 2.7 / 2
    gap_factor = 1.0 + (elo_gap / 100) * 0.12
    elo_hl = max(0.3, avg * gap_factor + (home_elo - away_elo) / 100 * 0.18)
    elo_al = max(0.3, avg * gap_factor - (home_elo - away_elo) / 100 * 0.18)

    home_gf = dataset.get(dataset_home, {}).get("goals_for", 0)
    away_gf = dataset.get(dataset_away, {}).get("goals_for", 0)
    home_form_lam = home_gf / max(home_mp, 1) if home_mp > 0 else None
    away_form_lam = away_gf / max(away_mp, 1) if away_mp > 0 else None
    form_trust = min(min(home_mp, away_mp) / 5, 0.5)

    if home_form_lam is not None and home_form_lam > 0:
        probs["home_lambda"] = elo_hl * (1 - form_trust) + home_form_lam * form_trust
    else:
        probs["home_lambda"] = elo_hl
    if away_form_lam is not None and away_form_lam > 0:
        probs["away_lambda"] = elo_al * (1 - form_trust) + away_form_lam * form_trust
    else:
        probs["away_lambda"] = elo_al

    pick = recommend_pick(probs, points, crowd_pcts=crowd)
    return pick, probs


def score_outcome(outcome, actual_hg, actual_ag, points, crowd, pick):
    """Score a pick against the actual result."""
    if actual_hg > actual_ag:
        actual = "home"
    elif actual_hg == actual_ag:
        actual = "draw"
    else:
        actual = "away"

    if pick["outcome"] != actual:
        return 0

    pts = points[actual]
    _, bonus = estimate_bonus(crowd.get(actual, 1.0))
    pts += bonus

    # Exact score bonus
    predicted_h, predicted_a = map(int, pick["score"].split("-"))
    if predicted_h == actual_hg and predicted_a == actual_ag:
        pts += 25

    return pts


def crowd_favorite(crowd):
    return max(crowd, key=crowd.get)


def main():
    results = load_completed_matches()
    if not results:
        print("No completed matches found.")
        return

    # Sort chronologically
    results.sort(key=lambda r: r.get("date", ""))

    # Start with pre-tournament dataset
    dataset = restore_pre_tournament_dataset()
    predictor = EnsemblePredictor(dataset)

    print(f"Backtesting {len(results)} completed WC2026 matches")
    print(f"Using pre-tournament Elo snapshots, updating chronologically")
    print()
    print(f"{'#':>3} {'Match':<36} {'Pick':>10} {'Score':>5} {'Actual':>7} {'Pts':>5} {'Crowd':>10}")
    print("-" * 82)

    total_oracle = 0
    total_crowd = 0
    correct = 0
    crowd_correct = 0

    for i, match in enumerate(results, 1):
        home = match["home"]
        away = match["away"]
        hg = match["hg"]
        ag = match["ag"]

        # MPP points for this match (from API or estimated)
        points = {
            "home": match.get("home_points", 50),
            "draw": match.get("draw_points", 100),
            "away": match.get("away_points", 100),
        }
        crowd = {
            "home": match.get("crowd_home", 0.33),
            "draw": match.get("crowd_draw", 0.33),
            "away": match.get("crowd_away", 0.34),
        }

        # Predict
        pick, probs = predict_match(predictor, dataset, home, away, points, crowd)
        crowd_pick_outcome = crowd_favorite(crowd)

        # Score
        oracle_pts = score_outcome(pick["outcome"], hg, ag, points, crowd, pick)
        crowd_pts = score_outcome(crowd_pick_outcome, hg, ag, points, crowd,
                                   {"outcome": crowd_pick_outcome, "score": "1-0"})

        total_oracle += oracle_pts
        total_crowd += crowd_pts
        if oracle_pts > 0:
            correct += 1
        if crowd_pts > 0:
            crowd_correct += 1

        fixture = f"{home} v {away}"[:36]
        actual = f"{hg}-{ag}"
        print(f"{i:>3} {fixture:<36} {pick['outcome']:>10} {pick['score']:>5} {actual:>7} {oracle_pts:>5} {crowd_pick_outcome:>10}")

        # Update dataset with this match result (for next iteration)
        update_dataset(dataset, home, away, hg, ag)
        # Rebuild predictor with updated dataset
        predictor = EnsemblePredictor(dataset)

    print("-" * 82)
    print(f"Oracle: {total_oracle} pts ({correct}/{len(results)} correct)")
    print(f"Crowd:  {total_crowd} pts ({crowd_correct}/{len(results)} correct)")
    print(f"Delta:  {total_oracle - total_crowd:+d}")
    if len(results) > 0:
        print(f"Accuracy: {correct/len(results):.1%} vs crowd {crowd_correct/len(results):.1%}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Monte Carlo simulation for the currently known MPP match slate.

This intentionally simulates only matches we can see now. It does not invent
future fixtures, brackets, or leaderboard behavior.
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.ensemble import EnsemblePredictor, load_dataset, normalize_team_name
from models.optimizer import (
    EXACT_SCORE_BONUS,
    estimate_bonus,
    outcome_to_score,
    recommend_batch,
    recommend_pick,
)
from models.poisson import dixon_coles_adjust, score_probability
from predict import FALLBACK_MATCHES


OUTCOMES = ("home", "draw", "away")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Simulate current-week MPP point distributions."
    )
    parser.add_argument("--sims", type=int, default=20000, help="Number of simulations")
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    parser.add_argument("--catch-up", type=int, default=0, help="Points behind leader")
    parser.add_argument(
        "--max-contrarian",
        type=int,
        default=4,
        help="Optional cap on non-crowd-favorite picks",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch live MPP matches instead of using fallback matches",
    )
    parser.add_argument(
        "--html-output",
        default=None,
        help="Write browser-readable JS results for prediction_viewer.html",
    )
    parser.add_argument(
        "--actuals",
        action="store_true",
        help="Fetch completed MPP results and compare overlapping matches",
    )
    return parser.parse_args()


def load_matches(use_live=False):
    if not use_live:
        return list(FALLBACK_MATCHES)

    from mpp.client import get_matches

    api_matches = get_matches()
    if not api_matches:
        return list(FALLBACK_MATCHES)

    matches = []
    for match in api_matches:
        matches.append({
            "home": match["home_team"],
            "away": match["away_team"],
            "points": {
                "home": match["home_points"],
                "draw": match["draw_points"],
                "away": match["away_points"],
            },
            "crowd": {
                "home": match["crowd_home"],
                "draw": match["crowd_draw"],
                "away": match["crowd_away"],
            },
            "match_id": match["match_id"],
        })
    for match in matches:
        api_match = next(
            (m for m in (api_matches if use_live else []) if m.get("match_id") == match.get("match_id")), None
        )
        if api_match:
            match["status"] = api_match.get("period", "notStarted")
            match["live_home"] = api_match.get("home_score")
            match["live_away"] = api_match.get("away_score")
        else:
            match["status"] = "unknown"
    return matches


def enrich_probabilities(dataset, predictor, match):
    home = match["home"]
    away = match["away"]
    dataset_home = normalize_team_name(home)
    dataset_away = normalize_team_name(away)

    result = predictor.predict(home, away, neutral=True)
    probs = {outcome: result[outcome] for outcome in OUTCOMES}

    for model_name in ("poisson", "decomposed", "xg"):
        if model_name in result.get("models", {}):
            model = result["models"][model_name]
            probs["home_lambda"] = model.get("home_lambda", probs.get("home_lambda", 1.4))
            probs["away_lambda"] = model.get("away_lambda", probs.get("away_lambda", 1.1))

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

    # Per-model probabilities for the viewer
    model_probs = {}
    for model_name, model in result.get("models", {}).items():
        model_probs[model_name] = {
            outcome: round(model[outcome], 4)
            for outcome in OUTCOMES
            if outcome in model
        }
    if model_probs:
        probs["model_probs"] = model_probs

    # Full 11×11 Dixon-Coles score probability matrix for heatmap
    sp = score_probability(probs.get("home_lambda", 1.4), probs.get("away_lambda", 1.1))
    sp = dixon_coles_adjust(sp, probs.get("home_lambda", 1.4), probs.get("away_lambda", 1.1))
    # Truncate to 7×7 (scores beyond 6 are negligible) and round
    max_goals = 7
    score_grid = []
    for i in range(max_goals):
        row = []
        for j in range(max_goals):
            if i < len(sp) and j < len(sp[0]):
                row.append(round(sp[i][j], 5))
            else:
                row.append(0.0)
        score_grid.append(row)
    probs["score_matrix"] = score_grid

    return probs


def crowd_favorite(crowd):
    return max(crowd, key=crowd.get)


def build_slate(matches, points_behind=0, max_contrarian=None):
    dataset = load_dataset()
    predictor = EnsemblePredictor(dataset)

    predictions = []
    for match in matches:
        probs = enrich_probabilities(dataset, predictor, match)
        predictions.append((match, probs, match["points"], match.get("crowd", {})))

    if max_contrarian is None:
        oracle_picks = [
            recommend_pick(probs, points, points_behind, crowd)
            for match, probs, points, crowd in predictions
        ]
    else:
        oracle_picks = recommend_batch(
            predictions,
            points_behind=points_behind,
            max_contrarian=max_contrarian,
        )

    crowd_picks = []
    for match, probs, points, crowd in predictions:
        outcome = crowd_favorite(crowd)
        score = outcome_to_score(
            outcome,
            probs.get("home_lambda", 1.4),
            probs.get("away_lambda", 1.1),
        )
        bonus_name, bonus_points = estimate_bonus(crowd[outcome])
        crowd_picks.append({
            "outcome": outcome,
            "score": score,
            "base_points": points[outcome],
            "bonus_name": bonus_name,
            "bonus_points": bonus_points,
        })

    return predictions, oracle_picks, crowd_picks


def outcome_from_score(home_goals, away_goals):
    if home_goals > away_goals:
        return "home"
    if home_goals == away_goals:
        return "draw"
    return "away"


def conditional_scores(home_lambda, away_lambda, outcome):
    matrix = dixon_coles_adjust(
        score_probability(home_lambda, away_lambda),
        home_lambda,
        away_lambda,
    )
    scores = []
    total = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            if outcome_from_score(home_goals, away_goals) != outcome:
                continue
            scores.append((home_goals, away_goals, probability))
            total += probability

    if total <= 0:
        return [(0, 0, 1.0)]

    return [
        (home_goals, away_goals, probability / total)
        for home_goals, away_goals, probability in scores
    ]


def weighted_choice(items, rng):
    target = rng.random()
    cumulative = 0.0
    for item in items:
        cumulative += item[-1]
        if target <= cumulative:
            return item
    return items[-1]


def sample_score(probs, rng):
    outcome_roll = rng.random()
    cumulative = 0.0
    actual_outcome = "away"
    for outcome in OUTCOMES:
        cumulative += probs[outcome]
        if outcome_roll <= cumulative:
            actual_outcome = outcome
            break

    scores = conditional_scores(
        probs.get("home_lambda", 1.4),
        probs.get("away_lambda", 1.1),
        actual_outcome,
    )
    home_goals, away_goals, _probability = weighted_choice(scores, rng)
    return home_goals, away_goals


def score_pick(pick, points, crowd, home_goals, away_goals):
    actual = outcome_from_score(home_goals, away_goals)
    if pick["outcome"] != actual:
        return 0

    points_won = points[actual]
    _bonus_name, bonus_points = estimate_bonus(crowd.get(actual, 1.0))
    points_won += bonus_points

    predicted_home, predicted_away = [int(part) for part in pick["score"].split("-")]
    if predicted_home == home_goals and predicted_away == away_goals:
        points_won += EXACT_SCORE_BONUS

    return points_won


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def summarize(values):
    return {
        "mean": statistics.fmean(values),
        "p10": percentile(values, 0.10),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
    }


def histogram(values):
    bins = [
        {"label": "< -200", "min": float("-inf"), "max": -200, "count": 0},
        {"label": "-200..-101", "min": -200, "max": -100, "count": 0},
        {"label": "-100..-1", "min": -100, "max": 0, "count": 0},
        {"label": "0..149", "min": 0, "max": 150, "count": 0},
        {"label": "150..299", "min": 150, "max": 300, "count": 0},
        {"label": "300..499", "min": 300, "max": 500, "count": 0},
        {"label": "500+", "min": 500, "max": float("inf"), "count": 0},
    ]

    for value in values:
        for bin_data in bins:
            if bin_data["min"] <= value < bin_data["max"]:
                bin_data["count"] += 1
                break

    for bin_data in bins:
        del bin_data["min"]
        del bin_data["max"]
    return bins


def write_html_results(path, predictions, oracle_picks, crowd_picks, oracle_totals,
                       crowd_totals, deltas, sims, seed, actuals=None):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for (match, probs, _points, crowd), oracle, crowd_pick in zip(
        predictions,
        oracle_picks,
        crowd_picks,
    ):
        row = {
            "match": f"{match['home']} v {match['away']}",
            "oracle": f"{oracle['outcome']} {oracle['score']}",
            "crowd": f"{crowd_pick['outcome']} {crowd_pick['score']}",
            "ev": oracle.get("ev", 0),
            "swing": oracle["outcome"] != crowd_favorite(crowd),
        }
        if "model_probs" in probs:
            row["model_probs"] = probs["model_probs"]
        if "score_matrix" in probs:
            row["score_matrix"] = probs["score_matrix"]
        if "status" in match:
            row["status"] = match["status"]
            row["live_home"] = match.get("live_home")
            row["live_away"] = match.get("live_away")
        rows.append(row)

    payload = {
        "source": "python",
        "sims": sims,
        "seed": seed,
        "matches": len(predictions),
        "rows": rows,
        "oracle": summarize(oracle_totals),
        "crowd": summarize(crowd_totals),
        "delta": summarize(deltas),
        "beatRate": sum(1 for value in deltas if value > 0) / len(deltas),
        "bigSwingRate": sum(1 for value in deltas if value >= 150) / len(deltas),
        "downsideRate": sum(1 for value in deltas if value <= -100) / len(deltas),
        "histogram": histogram(deltas),
        "actuals": actuals,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("window.MONTE_CARLO_RESULTS = ")
        json.dump(payload, f, indent=2)
        f.write(";\n")

    print(f"\nWrote HTML results: {output_path}")


def compare_actuals(completed_results, predictions, oracle_picks, crowd_picks,
                    sims=20000, seed=7):
    completed_by_pair = {
        (normalize_team_name(result["home"]), normalize_team_name(result["away"])): result
        for result in completed_results
    }

    matched_predictions = []
    rows = []
    oracle_total = 0
    crowd_total = 0

    for prediction, oracle, crowd_pick in zip(predictions, oracle_picks, crowd_picks):
        match, _probs, points, crowd = prediction
        key = (normalize_team_name(match["home"]), normalize_team_name(match["away"]))
        if key not in completed_by_pair:
            continue

        result = completed_by_pair[key]
        oracle_points = score_pick(oracle, points, crowd, result["hg"], result["ag"])
        crowd_points = score_pick(crowd_pick, points, crowd, result["hg"], result["ag"])
        oracle_total += oracle_points
        crowd_total += crowd_points
        matched_predictions.append((prediction, oracle, crowd_pick))
        rows.append({
            "match": f"{match['home']} v {match['away']}",
            "actual": f"{result['hg']}-{result['ag']}",
            "oracle": f"{oracle['outcome']} {oracle['score']}",
            "oraclePoints": oracle_points,
            "crowd": f"{crowd_pick['outcome']} {crowd_pick['score']}",
            "crowdPoints": crowd_points,
        })

    if matched_predictions:
        matched_sim = run_simulation(
            [item[0] for item in matched_predictions],
            [item[1] for item in matched_predictions],
            [item[2] for item in matched_predictions],
            sims=sims,
            seed=seed,
        )
        _oracle_totals, _crowd_totals, deltas = matched_sim
        actual_delta = oracle_total - crowd_total
        percentile_rank = sum(1 for delta in deltas if delta <= actual_delta) / len(deltas)
        delta_summary = summarize(deltas)
    else:
        actual_delta = 0
        percentile_rank = 0
        delta_summary = None

    return {
        "matched": len(rows),
        "oraclePoints": oracle_total,
        "crowdPoints": crowd_total,
        "delta": actual_delta,
        "deltaPercentile": percentile_rank,
        "deltaSummary": delta_summary,
        "rows": rows,
    }


def run_simulation(predictions, oracle_picks, crowd_picks, sims, seed):
    rng = random.Random(seed)
    oracle_totals = []
    crowd_totals = []
    deltas = []

    for _ in range(sims):
        oracle_total = 0
        crowd_total = 0
        for (match, probs, points, crowd), oracle_pick, crowd_pick in zip(
            predictions,
            oracle_picks,
            crowd_picks,
        ):
            home_goals, away_goals = sample_score(probs, rng)
            oracle_total += score_pick(oracle_pick, points, crowd, home_goals, away_goals)
            crowd_total += score_pick(crowd_pick, points, crowd, home_goals, away_goals)

        oracle_totals.append(oracle_total)
        crowd_totals.append(crowd_total)
        deltas.append(oracle_total - crowd_total)

    return oracle_totals, crowd_totals, deltas


def print_pick_table(predictions, oracle_picks, crowd_picks):
    print("Portfolio")
    print("-" * 86)
    print(f"{'Match':<34} {'Oracle':<13} {'Crowd':<13} {'EV':>7} {'Swing':>8}")
    print("-" * 86)
    for (match, _probs, _points, crowd), oracle, crowd_pick in zip(
        predictions,
        oracle_picks,
        crowd_picks,
    ):
        fixture = f"{match['home']} v {match['away']}"[:34]
        oracle_text = f"{oracle['outcome']} {oracle['score']}"
        crowd_text = f"{crowd_pick['outcome']} {crowd_pick['score']}"
        swing = "yes" if oracle["outcome"] != crowd_favorite(crowd) else "no"
        print(
            f"{fixture:<34} {oracle_text:<13} {crowd_text:<13} "
            f"{oracle.get('ev', 0):>7.1f} {swing:>8}"
        )


def print_summary(label, values):
    summary = summarize(values)
    print(
        f"{label:<12} mean={summary['mean']:>6.1f}  p10={summary['p10']:>4}  "
        f"p50={summary['p50']:>4}  p75={summary['p75']:>4}  "
        f"p90={summary['p90']:>4}  p95={summary['p95']:>4}"
    )


def main():
    args = parse_args()
    matches = load_matches(args.live)
    predictions, oracle_picks, crowd_picks = build_slate(
        matches,
        points_behind=args.catch_up,
        max_contrarian=args.max_contrarian,
    )

    oracle_totals, crowd_totals, deltas = run_simulation(
        predictions,
        oracle_picks,
        crowd_picks,
        sims=args.sims,
        seed=args.seed,
    )

    print_pick_table(predictions, oracle_picks, crowd_picks)
    print()
    print(f"Simulations: {args.sims:,} | matches: {len(predictions)} | seed: {args.seed}")
    print_summary("Oracle", oracle_totals)
    print_summary("Crowd", crowd_totals)
    print_summary("Delta", deltas)
    beat_rate = sum(1 for value in deltas if value > 0) / len(deltas)
    big_swing = sum(1 for value in deltas if value >= 150) / len(deltas)
    downside = sum(1 for value in deltas if value <= -100) / len(deltas)
    print()
    print(f"P(oracle beats crowd baseline): {beat_rate:.1%}")
    print(f"P(delta >= +150):              {big_swing:.1%}")
    print(f"P(delta <= -100):              {downside:.1%}")

    actuals = None
    if args.actuals:
        from mpp.results import get_completed_matches

        actuals = compare_actuals(
            get_completed_matches(),
            predictions,
            oracle_picks,
            crowd_picks,
            sims=args.sims,
            seed=args.seed,
        )
        print()
        print(f"Actual completed overlap: {actuals['matched']} matches")
        for row in actuals["rows"]:
            print(
                f"  {row['match']}: actual {row['actual']} | "
                f"oracle {row['oracle']} = {row['oraclePoints']} | "
                f"crowd {row['crowd']} = {row['crowdPoints']}"
            )
        print(f"Actual oracle points: {actuals['oraclePoints']}")
        print(f"Actual crowd points:  {actuals['crowdPoints']}")
        print(f"Actual delta:         {actuals['delta']}")
        if actuals["matched"]:
            print(f"Actual delta percentile in matched simulation: {actuals['deltaPercentile']:.1%}")

    if args.html_output:
        write_html_results(
            args.html_output,
            predictions,
            oracle_picks,
            crowd_picks,
            oracle_totals,
            crowd_totals,
            deltas,
            sims=args.sims,
            seed=args.seed,
            actuals=actuals,
        )


if __name__ == "__main__":
    main()

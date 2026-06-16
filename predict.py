#!/usr/bin/env python3
"""Predict optimal MPP picks for upcoming matches.

Usage:
    python predict.py                          # All upcoming matches
    python predict.py --catch-up 800            # Catch-up mode
    python predict.py --match England Croatia   # Specific match
"""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models.ensemble import EnsemblePredictor, load_dataset
from models.optimizer import recommend_pick

# MPP point values from the API (snapshot June 16, 2026)
MPP_MATCHES = [
    # Matchday 2 — Wednesday June 17
    {"home": "Argentina", "away": "Algeria", "points": {"home": 43, "draw": 129, "away": 159}},
    {"home": "Austria", "away": "Jordan", "points": {"home": 38, "draw": 136, "away": 163}},
    {"home": "Portugal", "away": "DR Congo", "points": {"home": 34, "draw": 140, "away": 170}},
    {"home": "England", "away": "Croatia", "points": {"home": 59, "draw": 119, "away": 133}},
    # Matchday 3 — Thursday June 18
    {"home": "Ghana", "away": "Panama", "points": {"home": 73, "draw": 113, "away": 116}},
    {"home": "Uzbekistan", "away": "Colombia", "points": {"home": 157, "draw": 130, "away": 44}},
    {"home": "Czech Republic", "away": "South Africa", "points": {"home": 62, "draw": 112, "away": 142}},
    {"home": "Switzerland", "away": "Bosnia", "points": {"home": 76, "draw": 108, "away": 134}},
    {"home": "Canada", "away": "Qatar", "points": {"home": 71, "draw": 104, "away": 148}},
]


def main():
    catch_up = 0
    filter_match = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("--catch-up", "-c") and i + 1 < len(args):
            catch_up = int(args[i + 1])
            i += 2
        elif args[i] == "--match" and i + 2 < len(args):
            filter_match = (args[i + 1], args[i + 2])
            i += 3
        else:
            i += 1

    print("Loading dataset...")
    dataset = load_dataset()
    predictor = EnsemblePredictor(dataset)

    header = f"{'Match':<30} {'Elo':>10} {'Ensemble':>19} {'Points':>18} {'EV':>18} {'Pick':>10} {'Score':>6}"
    print("\n" + header)
    print("-" * len(header))

    for match in MPP_MATCHES:
        home = match["home"]
        away = match["away"]
        points = match["points"]

        if filter_match and (home, away) != filter_match:
            continue

        result = predictor.predict(home, away, neutral=True)
        probs = {k: result[k] for k in ["home", "draw", "away"]}

        # Add lambdas from Poisson model if available
        if "poisson" in result.get("models", {}):
            p = result["models"]["poisson"]
            probs["home_lambda"] = p.get("home_lambda", 1.4)
            probs["away_lambda"] = p.get("away_lambda", 1.1)

        pick = recommend_pick(probs, points, points_behind=catch_up)

        elo_h = dataset.get(home, {}).get("elo", "?")
        elo_a = dataset.get(away, {}).get("elo", "?")
        prob_str = f"{probs['home']:.0%}/{probs['draw']:.0%}/{probs['away']:.0%}"
        pts_str = f"{points['home']}/{points['draw']}/{points['away']}"
        ev_str = f"{pick['all_ev']['home']}/{pick['all_ev']['draw']}/{pick['all_ev']['away']}"

        flag = " 🔥" if pick["outcome"] != "home" else ""

        print(
            f"{home[:12]:<12} v {away[:12]:<12}  "
            f"{elo_h:>4}v{elo_a:<4} "
            f"{prob_str:>19} {pts_str:>18} {ev_str:>18} "
            f"{pick['outcome']:>10}{flag} {pick['score']:>6}"
        )

    mode = f"CATCH-UP ({catch_up}pts behind)" if catch_up > 200 else "Normal (max EV)"
    print(f"\nMode: {mode}")


if __name__ == "__main__":
    main()

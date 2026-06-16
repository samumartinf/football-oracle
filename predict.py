#!/usr/bin/env python3
"""Predict optimal MPP picks for upcoming matches.

Usage:
    python predict.py                          # All matches, normal mode
    python predict.py --catch-up 800            # Catch-up mode (800 pts behind)
    python predict.py --double                  # Show double-points recommendation
    python predict.py --news                    # Check news for injury disruptions
    python predict.py --match England Croatia   # Specific match only
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.ensemble import EnsemblePredictor, load_dataset
from models.optimizer import recommend_pick
from models.news_adjuster import get_adjustments, apply_adjustments

# MPP match data with crowd percentages from the API (snapshot June 16, 2026)
MPP_MATCHES = [
    # Matchday 2 — Wednesday June 17
    {
        "home": "Argentina", "away": "Algeria",
        "points": {"home": 43, "draw": 129, "away": 159},
        "crowd": {"home": 0.80, "draw": 0.14, "away": 0.06},
    },
    {
        "home": "Austria", "away": "Jordan",
        "points": {"home": 38, "draw": 136, "away": 163},
        "crowd": {"home": 0.83, "draw": 0.14, "away": 0.03},
    },
    {
        "home": "Portugal", "away": "DR Congo",
        "points": {"home": 34, "draw": 140, "away": 170},
        "crowd": {"home": 0.95, "draw": 0.04, "away": 0.01},
    },
    {
        "home": "England", "away": "Croatia",
        "points": {"home": 59, "draw": 119, "away": 133},
        "crowd": {"home": 0.57, "draw": 0.35, "away": 0.08},
    },
    # Matchday 3 — Thursday June 18
    {
        "home": "Ghana", "away": "Panama",
        "points": {"home": 73, "draw": 113, "away": 116},
        "crowd": {"home": 0.60, "draw": 0.33, "away": 0.07},
    },
    {
        "home": "Uzbekistan", "away": "Colombia",
        "points": {"home": 157, "draw": 130, "away": 44},
        "crowd": {"home": 0.03, "draw": 0.07, "away": 0.90},
    },
    {
        "home": "Czech Republic", "away": "South Africa",
        "points": {"home": 62, "draw": 112, "away": 142},
        "crowd": {"home": 0.58, "draw": 0.27, "away": 0.15},
    },
    {
        "home": "Switzerland", "away": "Bosnia",
        "points": {"home": 76, "draw": 108, "away": 134},
        "crowd": {"home": 0.72, "draw": 0.21, "away": 0.06},
    },
    {
        "home": "Canada", "away": "Qatar",
        "points": {"home": 71, "draw": 104, "away": 148},
        "crowd": {"home": 0.76, "draw": 0.17, "away": 0.07},
    },
]


def main():
    catch_up = 0
    show_double = False
    check_news = False
    filter_match = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("--catch-up", "-c") and i + 1 < len(args):
            catch_up = int(args[i + 1])
            i += 2
        elif args[i] == "--double":
            show_double = True
            i += 1
        elif args[i] == "--news":
            check_news = True
            i += 1
        elif args[i] == "--match" and i + 2 < len(args):
            filter_match = (args[i + 1], args[i + 2])
            i += 3
        else:
            i += 1

    print("Loading dataset...")
    dataset = load_dataset()
    predictor = EnsemblePredictor(dataset)

    # News check (before predictions)
    adjustments = {}
    if check_news:
        print("\n📰 Checking news for disruptions...")
        adjustments = get_adjustments(MPP_MATCHES)
        if adjustments:
            print(f"\n⚠️  {len(adjustments)} teams with disruptions detected\n")
        else:
            print("   No disruptions found\n")

    # Print predictions
    header = (
        f"{'Match':<30} {'Pick':>10} {'Score':>6} {'EV':>8} {'Total':>8} {'Bonus':>14} {'Notes':>20}"
    )
    print("\n" + header)
    print("-" * len(header))

    double_candidate = None
    best_double_boost = 0
    double_pick_for_best = None

    for match in MPP_MATCHES:
        home = match["home"]
        away = match["away"]
        points = match["points"]
        crowd = match.get("crowd", {})

        if filter_match and (home, away) != filter_match:
            continue

        result = predictor.predict(home, away, neutral=True)
        probs = {k: result[k] for k in ["home", "draw", "away"]}
        if "poisson" in result.get("models", {}):
            p = result["models"]["poisson"]
            probs["home_lambda"] = p.get("home_lambda", 1.4)
            probs["away_lambda"] = p.get("away_lambda", 1.1)

        # Apply news adjustments
        note = ""
        if adjustments:
            probs, note = apply_adjustments(probs, home, away, adjustments)
        note_str = f" ⚠️ {note[:50]}" if note else ""

        pick = recommend_pick(probs, points, points_behind=catch_up, crowd_pcts=crowd)

        # Track best double-points candidate
        double = recommend_pick(probs, points, points_behind=catch_up, crowd_pcts=crowd, double_match=True)
        boost = double["ev"] - pick["ev"]
        if boost > best_double_boost:
            best_double_boost = boost
            double_candidate = match
            double_pick_for_best = double

        flag = " 🔥" if pick["outcome"] != "home" else ""
        bonus_str = (
            f"+{pick['bonus_points']} ({pick['bonus_name']})"
            if pick["bonus_name"]
            else "—"
        )

        print(
            f"{home[:12]:<12} v {away[:12]:<12}  "
            f"{pick['outcome']:>10}{flag} {pick['score']:>6} "
            f"{pick['ev']:>7.1f}  {pick['total_possible']:>5}   {bonus_str:<14} {note_str:<20}"
        )

    mode = "CATCH-UP" if catch_up > 200 else "Normal"
    news_note = " + news-adjusted" if adjustments else ""
    print(f"\nMode: {mode} (max EV){news_note}" + (f" — {catch_up}pts behind leader" if catch_up > 200 else ""))

    # Double-points recommendation
    if show_double and double_candidate:
        dp = double_pick_for_best
        print(f"\n⚡ DOUBLE POINTS: use on **{double_candidate['home']} vs {double_candidate['away']}**")
        print(f"   Pick: {dp['outcome']} {dp['score']} → {dp['total_possible']} total possible pts")
        print(f"   EV boost: +{best_double_boost:.1f} pts over normal pick")
    elif not show_double:
        print("\n(Add --double to see double-points recommendation)")
    if not check_news:
        print("(Add --news to check for injury/disruption news)")


if __name__ == "__main__":
    main()

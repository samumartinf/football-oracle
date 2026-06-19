#!/usr/bin/env python3
"""Predict optimal MPP picks for upcoming matches.

Usage:
    python predict.py                          # Hardcoded matches, normal mode
    python predict.py --submit                  # Fetch live MPP data + auto-submit
    python predict.py --catch-up 800            # Catch-up mode (800 pts behind)
    python predict.py --double                  # Show double-points recommendation
    python predict.py --news                    # Check news for injury disruptions
    python predict.py --match England Croatia   # Specific match only
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))

from models.ensemble import EnsemblePredictor, load_dataset, normalize_team_name
from models.optimizer import recommend_pick, recommend_batch
from models.news_adjuster import get_adjustments, apply_adjustments
from models.form_updater import apply_tournament_form

# Fallback match data (used when API returns nothing)
FALLBACK_MATCHES = [
    # Matchday 2 — Wednesday June 17
    {"home": "Argentina", "away": "Algeria", "points": {"home": 43, "draw": 129, "away": 159}, "crowd": {"home": 0.80, "draw": 0.14, "away": 0.06}},
    {"home": "Austria", "away": "Jordan", "points": {"home": 38, "draw": 136, "away": 163}, "crowd": {"home": 0.83, "draw": 0.14, "away": 0.03}},
    {"home": "Portugal", "away": "DR Congo", "points": {"home": 34, "draw": 140, "away": 170}, "crowd": {"home": 0.95, "draw": 0.04, "away": 0.01}},
    {"home": "England", "away": "Croatia", "points": {"home": 59, "draw": 119, "away": 133}, "crowd": {"home": 0.57, "draw": 0.35, "away": 0.08}},
    # Matchday 3 — Thursday June 18
    {"home": "Ghana", "away": "Panama", "points": {"home": 73, "draw": 113, "away": 116}, "crowd": {"home": 0.60, "draw": 0.33, "away": 0.07}},
    {"home": "Uzbekistan", "away": "Colombia", "points": {"home": 157, "draw": 130, "away": 44}, "crowd": {"home": 0.03, "draw": 0.07, "away": 0.90}},
    {"home": "Czech Republic", "away": "South Africa", "points": {"home": 62, "draw": 112, "away": 142}, "crowd": {"home": 0.58, "draw": 0.27, "away": 0.15}},
    {"home": "Switzerland", "away": "Bosnia", "points": {"home": 76, "draw": 108, "away": 134}, "crowd": {"home": 0.72, "draw": 0.21, "away": 0.06}},
    {"home": "Canada", "away": "Qatar", "points": {"home": 71, "draw": 104, "away": 148}, "crowd": {"home": 0.76, "draw": 0.17, "away": 0.07}},
]


def main():
    catch_up = 0
    show_double = False
    check_news = False
    do_submit = False
    update_form = False
    filter_match = None
    max_contrarian = 4  # int = cap, None = unlimited

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("--catch-up", "-c") and i + 1 < len(args):
            catch_up = int(args[i + 1]); i += 2
        elif args[i] == "--double":
            show_double = True; i += 1
        elif args[i] == "--news":
            check_news = True; i += 1
        elif args[i] == "--submit":
            do_submit = True; i += 1
        elif args[i] == "--update-form":
            update_form = True; i += 1
        elif args[i] == "--max-contrarian" and i + 1 < len(args):
            max_contrarian = int(args[i + 1]); i += 2
        elif args[i] == "--match" and i + 2 < len(args):
            filter_match = (args[i + 1], args[i + 2]); i += 3
        else:
            i += 1

    # Update form from live tournament results before predicting
    if update_form:
        print("🔄 Updating form from live tournament results...")
        dataset = apply_tournament_form()
    else:
        print("Loading dataset...")
        dataset = load_dataset()
    predictor = EnsemblePredictor(dataset)

    # Fetch live matches from MPP API, fall back to hardcoded
    matches = list(FALLBACK_MATCHES)
    if do_submit:
        try:
            from mpp.client import get_matches as api_get_matches
            print("Fetching live MPP data...")
            api_matches = api_get_matches()
            if api_matches:
                matches = []
                for m in api_matches:
                    matches.append({
                        "home": m["home_team"], "away": m["away_team"],
                        "points": {"home": m["home_points"], "draw": m["draw_points"], "away": m["away_points"]},
                        "crowd": {"home": m["crowd_home"], "draw": m["crowd_draw"], "away": m["crowd_away"]},
                        "match_id": m["match_id"],
                    })
                print(f"  Got {len(matches)} live matches")
            else:
                print("  API returned 0 WC matches — using fallback data")
        except Exception as e:
            print(f"  API fetch failed ({e}) — using fallback data")

    # News check
    adjustments = {}
    if check_news:
        print("\n📰 Checking news for disruptions...")
        adjustments = get_adjustments(matches)
        if adjustments:
            print(f"\n⚠️  {len(adjustments)} teams with disruptions\n")
        else:
            print("   No disruptions found\n")

    # Predictions — collect all match data first
    match_predictions = []  # (match, probs, points, crowd)
    
    for match in matches:
        home = match["home"]; away = match["away"]
        dataset_home = normalize_team_name(home)
        dataset_away = normalize_team_name(away)
        points = match["points"]; crowd = match.get("crowd", {})

        if filter_match and (home, away) != filter_match:
            continue

        result = predictor.predict(home, away, neutral=True)
        probs = {k: result[k] for k in ["home", "draw", "away"]}
        if "poisson" in result.get("models", {}):
            p = result["models"]["poisson"]
            probs["home_lambda"] = p.get("home_lambda", 1.4)
            probs["away_lambda"] = p.get("away_lambda", 1.1)
        # Also check decomposed/xg models for lambdas
        for model_name in ["decomposed", "xg"]:
            if model_name in result.get("models", {}):
                m = result["models"][model_name]
                probs["home_lambda"] = m.get("home_lambda", probs.get("home_lambda", 1.4))
                probs["away_lambda"] = m.get("away_lambda", probs.get("away_lambda", 1.1))

        # Fall back to Elo-derived λ when decomposed data is weak.
        # For score prediction, also blend in actual tournament goals-per-match
        # to capture red-hot form (e.g. Germany 7 goals in 1 match).
        home_mp = dataset.get(dataset_home, {}).get("matches_played", 0)
        away_mp = dataset.get(dataset_away, {}).get("matches_played", 0)
        home_elo = dataset.get(dataset_home, {}).get("elo", 1500)
        away_elo = dataset.get(dataset_away, {}).get("elo", 1500)
        elo_gap = abs(home_elo - away_elo)

        # Elo-derived λ with super-linear scaling for large gaps.
        # Base: tournament average ~2.7 goals/match → 1.35 per team.
        # Large Elo gaps produce more goals (favorite scores freely).
        # 100 Elo gap → ~10% boost; 300 gap → ~40% boost.
        AVG = 2.7 / 2  # 1.35
        gap_factor = 1.0 + (elo_gap / 100) * 0.12
        elo_hl = max(0.3, AVG * gap_factor + (home_elo - away_elo) / 100 * 0.18)
        elo_al = max(0.3, AVG * gap_factor - (home_elo - away_elo) / 100 * 0.18)

        # Tournament form λ: actual goals per match in this tournament
        # Only use if team has played and scored
        home_gf = dataset.get(dataset_home, {}).get("goals_for", 0)
        away_gf = dataset.get(dataset_away, {}).get("goals_for", 0)
        home_form_lam = home_gf / max(home_mp, 1) if home_mp > 0 else None
        away_form_lam = away_gf / max(away_mp, 1) if away_mp > 0 else None

        # Blend: Elo base + tournament form. More trust in form with more matches.
        # Skip form blend if team hasn't scored (form_lam=0 would unfairly punish
        # teams coming off a 0-0 draw like Spain).
        form_trust = min(min(home_mp, away_mp) / 5, 0.5)  # max 50% form influence
        if home_form_lam is not None and home_form_lam > 0:
            probs["home_lambda"] = elo_hl * (1 - form_trust) + home_form_lam * form_trust
        else:
            probs["home_lambda"] = elo_hl
        if away_form_lam is not None and away_form_lam > 0:
            probs["away_lambda"] = elo_al * (1 - form_trust) + away_form_lam * form_trust
        else:
            probs["away_lambda"] = elo_al

        if adjustments:
            probs, _note = apply_adjustments(probs, home, away, adjustments)
        else:
            _note = ""

        match_predictions.append((match, probs, points, crowd))

    # Find best double-points match (independent of contrarian cap)
    double_match_idx = None
    if show_double and match_predictions:
        best_double_boost = 0
        for i, (match, probs, points, crowd) in enumerate(match_predictions):
            base = recommend_pick(probs, points, points_behind=catch_up, crowd_pcts=crowd, double_match=False)
            dbl = recommend_pick(probs, points, points_behind=catch_up, crowd_pcts=crowd, double_match=True)
            boost = dbl["ev"] - base["ev"]
            if boost > best_double_boost:
                best_double_boost = boost
                double_match_idx = i
                double_candidate = match
                double_pick_for_best = dbl

    # Batch-optimize picks (with contrarian cap)
    if max_contrarian is not None:
        picks = recommend_batch(match_predictions, points_behind=catch_up,
                               max_contrarian=max_contrarian,
                               double_match_idx=double_match_idx)
    else:
        # Fallback: per-match optimization (legacy)
        picks = []
        for match, probs, points, crowd in match_predictions:
            picks.append(recommend_pick(probs, points, points_behind=catch_up, crowd_pcts=crowd))

    # Display
    header = f"{'Match':<30} {'Pick':>10} {'Score':>6} {'EV':>8} {'Total':>8} {'Bonus':>14} {'Notes':>25}"
    print("\n" + header)
    print("-" * len(header))

    submissions = []
    for i, ((match, probs, points, crowd), pick) in enumerate(zip(match_predictions, picks)):
        home = match["home"]; away = match["away"]
        contrarian_flag = " 🔥" if pick.get("contrarian") else ""
        switched_flag = " ⚠️ capped" if pick.get("switched_from_contrarian") else ""
        bonus_str = f"+{pick['bonus_points']} ({pick['bonus_name']})" if pick.get("bonus_name") else "—"
        double_flag = " ⚡×2" if pick.get("doubled") else ""
        note = pick.get("reasoning", "")
        if len(note) > 45:
            note = note[:42] + "..."

        print(
            f"{home[:12]:<12} v {away[:12]:<12}  "
            f"{pick['outcome']:>10}{contrarian_flag} {pick['score']:>6} "
            f"{pick['ev']:>7.1f}  {pick['total_possible']:>5}   {bonus_str:<14} {note:<25}{switched_flag}{double_flag}"
        )

        submissions.append({"match": match, "pick": pick})

    mode = "CATCH-UP" if catch_up > 200 else "Normal"
    print(f"\nMode: {mode} (max EV)" + (f" — {catch_up}pts behind leader" if catch_up > 200 else ""))

    if show_double and double_candidate:
        dp = double_pick_for_best
        print(f"\n⚡ DOUBLE POINTS: use on **{double_candidate['home']} vs {double_candidate['away']}**")
        print(f"   Pick: {dp['outcome']} {dp['score']} → {dp['total_possible']} total possible pts")
        print(f"   EV boost: +{best_double_boost:.1f} pts")

    # Submit
    if do_submit:
        print("\n📤 Submitting predictions...")
        from mpp.client import submit_prediction
        for s in submissions:
            mid = s["match"].get("match_id")
            if not mid:
                print(f"  ⚠️  {s['match']['home']} vs {s['match']['away']}: no match_id — skipping")
                continue
            hs, aws = map(int, s["pick"]["score"].split("-"))
            try:
                submit_prediction(mid, hs, aws)
                print(f"  ✅ {s['match']['home']} vs {s['match']['away']}: {s['pick']['score']}")
            except Exception as e:
                print(f"  ❌ {s['match']['home']} vs {s['match']['away']}: {e}")
        print("Done.")

    if not do_submit:
        print("\n(Add --submit to auto-submit predictions)")
    if not check_news:
        print("(Add --news to check for injury disruptions)")
    if not show_double:
        print("(Add --double for double-points recommendation)")


if __name__ == "__main__":
    main()

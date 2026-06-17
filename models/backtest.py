"""Backtest ensemble against historical matches with weight grid search.

Walks matches chronologically, building Elo step-by-step to avoid look-ahead
bias. Tests Elo-only, Poisson-only, and blended ensembles to find the optimal
weight mix.

Usage:
    python models/backtest.py              # Full backtest + grid search
    python models/backtest.py --quick      # Fast: grid search only
"""

import math
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.elo import expected_score
from models.poisson import match_probabilities, match_probabilities_decomposed
from collections import defaultdict

# --- Constants ---
ELO_K = 32
HOME_ADVANTAGE = 100
INITIAL_ELO = 1500
AVG_GOALS = 2.7
ROLLING_WINDOW = 10  # matches for attack/defense rolling average

# WC teams we care about (for filtering from XLSX)
WC_TEAMS = {
    # Group stage (48 teams)
    "France", "Senegal", "Iraq", "Norway",
    "Argentina", "Algeria", "Austria", "Jordan",
    "Portugal", "DR Congo", "England", "Croatia",
    "Ghana", "Panama", "Uzbekistan", "Colombia",
    "Czechia", "South Africa", "Switzerland", "Bosnia",
    "Canada", "Qatar", "Mexico", "South Korea",
    "United States", "Paraguay", "Brazil", "Morocco",
    "Haiti", "Scotland", "Australia", "Türkiye",
    "Germany", "Curaçao", "Netherlands", "Japan",
    "Ivory Coast", "Ecuador", "Sweden", "Tunisia",
    "Spain", "Cape Verde", "Belgium", "Egypt",
    "Saudi Arabia", "Uruguay", "Iran", "New Zealand",
}

XLSX_TEAM_MAP = {
    "D.R. Congo": "DR Congo",
    "Bosnia & Herzegovina": "Bosnia",
    "Czech Republic": "Czechia",
}

# Grid: (elo_weight, poisson_weight) — market excluded from backtest
# since historical betting odds aren't available
WEIGHT_GRID = [(elo / 10, round(1.0 - elo / 10, 1)) for elo in range(0, 11)]

# --- Data loading ---


def _norm(name):
    return XLSX_TEAM_MAP.get(name.strip(), name.strip())


def load_historical_matches(data_dir=None):
    """Load all WC matches from XLSX, sorted chronologically.

    Returns list of (date, home, away, hg, ag, competition) dicts.
    """
    import pandas as pd

    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data" / "historical"
    xlsx_path = Path(data_dir) / "worldcup_data.xlsx"

    if not xlsx_path.exists():
        print(f"ERROR: {xlsx_path} not found. Run scrape_elo.py first.")
        return []

    xls = pd.ExcelFile(xlsx_path)
    matches = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        if sheet == "WorldCup2026Qualifiers":
            for _, r in df.iterrows():
                home = _norm(str(r["Home"]))
                away = _norm(str(r["Away"]))
                hg = r["HG"] if pd.notna(r["HG"]) else None
                ag = r["AG"] if pd.notna(r["AG"]) else None
                date = str(r.get("Date", ""))
                if hg is None or ag is None:
                    continue
                matches.append({
                    "date": date, "home": home, "away": away,
                    "hg": int(hg), "ag": int(ag),
                    "competition": "qualifiers", "neutral": False,
                })

        elif sheet in ("WorldCup2022", "WorldCup2018", "WorldCup2014"):
            for _, r in df.iterrows():
                home = _norm(str(r["Home"]))
                away = _norm(str(r["Away"]))
                hg = r["HGFT"] if pd.notna(r["HGFT"]) else None
                ag = r["AGFT"] if pd.notna(r["AGFT"]) else None
                date = str(r.get("Date", ""))
                if hg is None or ag is None:
                    continue
                matches.append({
                    "date": date, "home": home, "away": away,
                    "hg": int(hg), "ag": int(ag),
                    "competition": sheet.replace("WorldCup", "WC"),
                    "neutral": True,
                })

    # Sort by date
    matches.sort(key=lambda m: m["date"])
    return matches


# --- Elo state machine ---


def _init_elo():
    return {team: INITIAL_ELO for team in WC_TEAMS}


def _update_elo(elo_home, elo_away, hg, ag, recency=1.0):
    """Update Elo ratings after a match. Returns (new_home, new_away).
    
    recency: multiplier 0-1 scaling the K-factor (1.0 = full weight, 0.0 = no update).
    """
    exp_home = expected_score(elo_home + HOME_ADVANTAGE, elo_away)

    if hg > ag:
        result = 1.0
    elif hg == ag:
        result = 0.5
    else:
        result = 0.0

    goal_diff = abs(hg - ag)
    k = ELO_K * (1 + goal_diff / 4) if goal_diff <= 3 else ELO_K * 1.75
    k *= recency  # Time-weighted: older matches move Elo less

    new_home = elo_home + k * (result - exp_home)
    new_away = elo_away + k * ((1 - result) - (1 - exp_home))
    return round(new_home), round(new_away)

RECENCY_HALF_LIFE = 4.0  # years after which a match has half weight


def _recency_weight(match_date_str, reference_date="2026-06-01"):
    """Compute recency weight for a match given its date.
    
    Matches near the reference get weight ~1.0; matches from 2014 get ~0.3.
    Uses exponential decay: weight = 0.3 + 0.7 * exp(-years_ago / half_life)
    """
    import datetime as _dt
    try:
        match_date = _dt.datetime.strptime(match_date_str[:10], "%Y-%m-%d")
    except (ValueError, IndexError):
        return 1.0  # Can't parse date, assume recent
    
    ref_date = _dt.datetime.strptime(reference_date, "%Y-%m-%d")
    years_ago = (ref_date - match_date).days / 365.25
    if years_ago < 0:
        return 1.0  # Future match? Full weight
    
    return 0.3 + 0.7 * math.exp(-years_ago / RECENCY_HALF_LIFE)


# --- Prediction ---


def _predict_elo(elo_h, elo_a, neutral):
    """Elo-only prediction → {home, draw, away}."""
    ha = 0 if neutral else HOME_ADVANTAGE
    exp_home = expected_score(elo_h + ha, elo_a)
    elo_diff = abs((elo_h + ha) - elo_a)
    prob_draw = 0.30 * math.exp(-elo_diff / 800)
    remaining = 1.0 - prob_draw
    prob_home = exp_home * remaining
    prob_away = remaining - prob_home
    return {"home": prob_home, "draw": prob_draw, "away": prob_away}


def _predict_poisson(elo_h, elo_a, neutral):
    """Poisson-only prediction → {home, draw, away}."""
    result = match_probabilities(elo_h, elo_a, neutral=neutral)
    return {"home": result["home"], "draw": result["draw"], "away": result["away"]}


def _predict_poisson_decomposed(att_h, def_h, att_a, def_a, neutral):
    """Decomposed Poisson using attack/defense strengths."""
    result = match_probabilities_decomposed(att_h, def_h, att_a, def_a, neutral=neutral)
    return {"home": result["home"], "draw": result["draw"], "away": result["away"]}


def _rolling_strength(gf_list, ga_list, min_matches=3):
    """Compute attack/defense multipliers from rolling GF/GA lists.

    attack = avg_goals_scored / league_avg (1.0 = average)
    defense = avg_goals_conceded / league_avg (>1 = leaky)
    Returns (attack, defense) or (1.0, 1.0) if not enough data.
    """
    if len(gf_list) < min_matches or len(ga_list) < min_matches:
        return 1.0, 1.0
    league_avg = AVG_GOALS / 2
    avg_gf = sum(gf_list[-ROLLING_WINDOW:]) / min(len(gf_list), ROLLING_WINDOW)
    avg_ga = sum(ga_list[-ROLLING_WINDOW:]) / min(len(ga_list), ROLLING_WINDOW)
    attack = max(0.3, avg_gf / league_avg)
    defense = max(0.3, avg_ga / league_avg)
    return attack, defense


def _predict_ensemble(elo_h, elo_a, neutral, w_elo, w_poisson):
    """Blend Elo + Poisson with given weights."""
    e = _predict_elo(elo_h, elo_a, neutral)
    p = _predict_poisson(elo_h, elo_a, neutral)
    return {
        "home":  e["home"]  * w_elo + p["home"]  * w_poisson,
        "draw":  e["draw"]  * w_elo + p["draw"]  * w_poisson,
        "away":  e["away"]  * w_elo + p["away"]  * w_poisson,
    }


# --- Metrics ---


def _actual_outcome(hg, ag):
    if hg > ag: return "home"
    if hg == ag: return "draw"
    return "away"


def _log_loss(probs, actual):
    """Log loss (lower = better calibrated)."""
    p = max(probs.get(actual, 0.0), 1e-10)
    return -math.log(p)


def _brier(probs, actual):
    """Brier score (lower = better)."""
    targets = {"home": (1, 0, 0), "draw": (0, 1, 0), "away": (0, 0, 1)}
    t = targets[actual]
    return (probs["home"] - t[0])**2 + (probs["draw"] - t[1])**2 + (probs["away"] - t[2])**2


# --- Core backtest ---


def backtest_weights(matches, w_elo, w_poisson, w_decom=0.0,
                     progress=False, only_wc_teams=True):
    """Run a chronological backtest with fixed ensemble weights.
    
    Weights should sum to 1.0 across w_elo + w_poisson + w_decom.
    """
    # Normalize weights
    total_w = w_elo + w_poisson + w_decom
    if total_w > 0:
        w_elo /= total_w
        w_poisson /= total_w
        w_decom /= total_w
    elo = _init_elo()
    results = []

    # Rolling GF/GA for decomposed Poisson (last N matches per team)
    team_gf = defaultdict(list)
    team_ga = defaultdict(list)

    # Per-model accumulators
    elo_correct = 0
    poisson_correct = 0
    decom_correct = 0
    elo_ll = 0.0
    poisson_ll = 0.0
    decom_ll = 0.0

    for m in matches:
        home = m["home"]
        away = m["away"]
        hg = m["hg"]
        ag = m["ag"]
        neutral = m["neutral"]

        # Update rolling stats for non-WC matches too (they provide form data)
        team_gf[home].append(hg)
        team_ga[home].append(ag)
        team_gf[away].append(ag)
        team_ga[away].append(hg)

        # Only backtest matches involving WC teams
        if only_wc_teams and home not in WC_TEAMS and away not in WC_TEAMS:
            if home not in elo:
                elo[home] = INITIAL_ELO
            if away not in elo:
                elo[away] = INITIAL_ELO
            elo[home], elo[away] = _update_elo(elo[home], elo[away], hg, ag,
                                               recency=_recency_weight(m["date"]))
            continue

        # Ensure both teams have Elo ratings
        if home not in elo:
            elo[home] = INITIAL_ELO
        if away not in elo:
            elo[away] = INITIAL_ELO

        elo_h = elo[home]
        elo_a = elo[away]

        # Compute decomposed strengths (BEFORE this match's result)
        att_h, def_h = _rolling_strength(team_gf[home][:-1], team_ga[home][:-1])
        att_a, def_a = _rolling_strength(team_gf[away][:-1], team_ga[away][:-1])

        # Predict (BEFORE updating Elo/stats) — compute each model first
        elo_probs = _predict_elo(elo_h, elo_a, neutral)
        poisson_probs = _predict_poisson(elo_h, elo_a, neutral)
        decom_probs = _predict_poisson_decomposed(att_h, def_h, att_a, def_a, neutral)

        # Blend
        probs = {
            "home": (elo_probs["home"] * w_elo +
                     poisson_probs["home"] * w_poisson +
                     decom_probs["home"] * w_decom),
            "draw": (elo_probs["draw"] * w_elo +
                     poisson_probs["draw"] * w_poisson +
                     decom_probs["draw"] * w_decom),
            "away": (elo_probs["away"] * w_elo +
                     poisson_probs["away"] * w_poisson +
                     decom_probs["away"] * w_decom),
        }

        actual = _actual_outcome(hg, ag)

        # Ensemble metrics
        predicted = max(probs, key=probs.get)
        correct = predicted == actual

        results.append({
            "home": home, "away": away,
            "hg": hg, "ag": ag,
            "actual": actual,
            "predicted": predicted,
            "correct": correct,
            "probs": {k: round(v, 3) for k, v in probs.items()},
            "elo_h": elo_h, "elo_a": elo_a,
            "att_h": round(att_h, 2), "def_h": round(def_h, 2),
            "att_a": round(att_a, 2), "def_a": round(def_a, 2),
            "competition": m["competition"],
        })

        # Per-model tracking
        elo_pred = max(elo_probs, key=elo_probs.get)
        if elo_pred == actual:
            elo_correct += 1
        elo_ll += _log_loss(elo_probs, actual)

        poisson_pred = max(poisson_probs, key=poisson_probs.get)
        if poisson_pred == actual:
            poisson_correct += 1
        poisson_ll += _log_loss(poisson_probs, actual)

        decom_pred = max(decom_probs, key=decom_probs.get)
        if decom_pred == actual:
            decom_correct += 1
        decom_ll += _log_loss(decom_probs, actual)

        # Update Elo AFTER predicting
        elo[home], elo[away] = _update_elo(elo_h, elo_a, hg, ag,
                                           recency=_recency_weight(m["date"]))

    n = len(results)
    correct = sum(1 for r in results if r["correct"])
    ll = sum(_log_loss(r["probs"], r["actual"]) for r in results)
    brier = sum(_brier(r["probs"], r["actual"]) for r in results) / n if n > 0 else 0

    return {
        "accuracy": correct / n if n > 0 else 0,
        "log_loss": ll / n if n > 0 else 0,
        "brier": brier,
        "n_matches": n,
        "correct": correct,
        "per_model": {
            "elo": {
                "accuracy": elo_correct / n if n > 0 else 0,
                "log_loss": elo_ll / n if n > 0 else 0,
            },
            "poisson": {
                "accuracy": poisson_correct / n if n > 0 else 0,
                "log_loss": poisson_ll / n if n > 0 else 0,
            },
            "decomposed": {
                "accuracy": decom_correct / n if n > 0 else 0,
                "log_loss": decom_ll / n if n > 0 else 0,
            },
        },
        "details": results,
    }


def grid_search(matches):
    """Try all 3-way weight combinations, return ranked by log-loss.
    
    Tests 21 combinations at 0%, 25%, 50%, 75%, 100% steps for each model.
    """
    steps = [0.0, 0.25, 0.50, 0.75, 1.0]
    ranked = []
    
    for w_e in steps:
        for w_p in steps:
            for w_d in steps:
                if abs(w_e + w_p + w_d - 1.0) > 0.001:
                    continue
                result = backtest_weights(matches, w_e, w_p, w_d)
                ranked.append({
                    "elo_w": w_e,
                    "poisson_w": w_p,
                    "decom_w": w_d,
                    "accuracy": result["accuracy"],
                    "log_loss": result["log_loss"],
                    "brier": result["brier"],
                })

    ranked.sort(key=lambda x: x["log_loss"])
    return ranked


# --- CLI ---


def load_wc2026_results(data_dir=None):
    """Load WC 2026 match results from JSON (fetched via mpp.results).

    Returns list of match dicts compatible with the backtest format:
    {date, home, away, hg, ag, competition, neutral}
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data" / "historical"
    json_path = Path(data_dir) / "wc2026_results.json"

    if not json_path.exists():
        print(f"  No WC2026 results file at {json_path}")
        return []

    with open(json_path) as f:
        results = json.load(f)

    matches = []
    for r in results:
        matches.append({
            "date": r.get("date", ""),
            "home": r["home"],
            "away": r["away"],
            "hg": r["hg"],
            "ag": r["ag"],
            "competition": "WC2026",
            "neutral": True,
        })

    return matches


def run_backtest(data_dir=None, matches=None):
    """Full pipeline: load, backtest all models, grid search, print report."""
    if matches is None:
        print("Loading historical matches...")
        matches = load_historical_matches(data_dir)
    if not matches:
        print("No match data found. Run the data pipeline first:\n"
              "  python data_pipeline/run_all.py")
        return
    print(f"  Loaded {len(matches)} matches from XLSX\n")

    # --- Per-model baselines ---
    print("=" * 60)
    print("MODEL BASELINES")
    print("=" * 60)

    b_elo = backtest_weights(matches, 1.0, 0.0)
    b_poisson = backtest_weights(matches, 0.0, 1.0)

    print(f"{'Model':<18} {'Accuracy':>10} {'Log Loss':>10} {'Matches':>10}")
    print("-" * 50)
    print(f"{'Elo (time-weighted)':<18} {b_elo['accuracy']:>9.1%} {b_elo['log_loss']:>10.4f} {b_elo['n_matches']:>10}")
    print(f"{'Poisson (Elo-based)':<18} {b_poisson['accuracy']:>9.1%} {b_poisson['log_loss']:>10.4f} {b_poisson['n_matches']:>10}")
    print(f"{'Decomposed Poisson':<18} {b_poisson['per_model']['decomposed']['accuracy']:>9.1%} "
          f"{b_poisson['per_model']['decomposed']['log_loss']:>10.4f} {b_poisson['n_matches']:>10}")

    # --- Current ensemble ---
    b_current = backtest_weights(matches, 0.43, 0.57)
    print(f"\nCurrent ensemble (43% Elo / 57% Poisson): "
          f"acc={b_current['accuracy']:.1%}  "
          f"ll={b_current['log_loss']:.4f}")

    # --- Grid search ---
    print("\n" + "=" * 60)
    print("GRID SEARCH (3-way, ranked by log-loss)")
    print("=" * 60)
    print(f"{'Elo%':>6} {'Pois%':>7} {'Decom%':>8} {'Acc':>8} {'LogLoss':>10} {'Brier':>10}")
    print("-" * 55)

    ranked = grid_search(matches)
    for r in ranked[:10]:
        marker = " ←" if r["log_loss"] == ranked[0]["log_loss"] else ""
        print(f"{r['elo_w']:>5.0%} {r['poisson_w']:>6.0%} {r['decom_w']:>7.0%} "
              f"{r['accuracy']:>7.1%} {r['log_loss']:>10.4f} "
              f"{r['brier']:>10.4f}{marker}")

    if len(ranked) > 10:
        print(f"  ... and {len(ranked) - 10} more combinations")

    # --- Best ---
    best = ranked[0]
    print(f"\n✅ Best blend: {best['elo_w']:.0%} Elo / {best['poisson_w']:.0%} Poisson / {best['decom_w']:.0%} Decomposed")
    print(f"   Accuracy: {best['accuracy']:.1%}")
    print(f"   Log-loss: {best['log_loss']:.4f}")
    print(f"   Brier:    {best['brier']:.4f}")

    # --- Per-competition breakdown ---
    print("\n" + "=" * 60)
    print("PER-COMPETITION (best weights)")
    print("=" * 60)
    best_result = backtest_weights(matches, best["elo_w"], best["poisson_w"])
    comps = {}
    for d in best_result["details"]:
        comp = d["competition"]
        if comp not in comps:
            comps[comp] = {"total": 0, "correct": 0}
        comps[comp]["total"] += 1
        if d["correct"]:
            comps[comp]["correct"] += 1

    print(f"{'Tournament':<15} {'Matches':>10} {'Correct':>10} {'Accuracy':>10}")
    print("-" * 45)
    for comp in sorted(comps):
        c = comps[comp]
        print(f"{comp:<15} {c['total']:>10} {c['correct']:>10} {c['correct']/c['total']:>9.1%}")


# --- xG Backtest ---


def backtest_xg(xg_matches):
    """Backtest xG model on StatsBomb international matches.

    Walks matches chronologically, computing rolling xG for/against per team
    (no look-ahead bias). Returns same metrics shape as backtest_weights.
    """
    from models.xg import xg_match_probabilities

    xg_for = defaultdict(list)
    xg_against = defaultdict(list)
    correct = 0
    total_ll = 0.0
    total_brier = 0.0
    total = 0
    details = []

    for m in xg_matches:
        home = m["home_team"]
        away = m["away_team"]
        actual = "home" if m["home_goals"] > m["away_goals"] else \
                 "draw" if m["home_goals"] == m["away_goals"] else "away"

        # Compute strengths from prior matches only
        att_h = def_h = att_a = def_a = 1.0
        if len(xg_for[home]) >= 3:
            avg_gf = sum(xg_for[home][-ROLLING_WINDOW:]) / min(len(xg_for[home]), ROLLING_WINDOW)
            avg_ga = sum(xg_against[home][-ROLLING_WINDOW:]) / min(len(xg_against[home]), ROLLING_WINDOW)
            att_h = max(0.3, avg_gf / 1.2)
            def_h = max(0.3, avg_ga / 1.2)
        if len(xg_for[away]) >= 3:
            avg_gf = sum(xg_for[away][-ROLLING_WINDOW:]) / min(len(xg_for[away]), ROLLING_WINDOW)
            avg_ga = sum(xg_against[away][-ROLLING_WINDOW:]) / min(len(xg_against[away]), ROLLING_WINDOW)
            att_a = max(0.3, avg_gf / 1.2)
            def_a = max(0.3, avg_ga / 1.2)

        probs = xg_match_probabilities(att_h, def_h, att_a, def_a, neutral=True)
        # Only use home/draw/away for prediction (not lambdas)
        pred_probs = {"home": probs["home"], "draw": probs["draw"], "away": probs["away"]}
        predicted = max(pred_probs, key=pred_probs.get)

        if predicted == actual:
            correct += 1

        p = max(probs.get(actual, 0.0), 1e-10)
        total_ll += -math.log(p)
        total_brier += _brier(probs, actual)
        total += 1

        details.append({
            "home": home, "away": away,
            "actual": actual, "predicted": predicted,
            "correct": predicted == actual,
            "probs": {k: round(v, 3) for k, v in probs.items()},
            "competition": m.get("competition", ""),
        })

        # Update rolling xG AFTER predicting
        xg_for[home].append(m["home_xg"])
        xg_against[home].append(m["away_xg"])
        xg_for[away].append(m["away_xg"])
        xg_against[away].append(m["home_xg"])

    return {
        "accuracy": correct / total if total > 0 else 0,
        "log_loss": total_ll / total if total > 0 else 0,
        "brier": total_brier / total if total > 0 else 0,
        "n_matches": total,
        "correct": correct,
        "details": details,
    }


if __name__ == "__main__":
    import sys
    quick = "--quick" in sys.argv
    include_wc2026 = "--wc2026" in sys.argv
    if quick:
        # Just the grid search
        matches = load_historical_matches()
        if include_wc2026:
            wc2026 = load_wc2026_results()
            matches.extend(wc2026)
            matches.sort(key=lambda m: m["date"])
            print(f"Added {len(wc2026)} WC 2026 matches to backtest")
        ranked = grid_search(matches)
        best = ranked[0]
        print(f"Best: {best['elo_w']:.0%} Elo / {best['poisson_w']:.0%} Poisson "
              f"(acc={best['accuracy']:.1%}, ll={best['log_loss']:.4f})")
    else:
        if include_wc2026:
            matches = load_historical_matches()
            wc2026 = load_wc2026_results()
            matches.extend(wc2026)
            matches.sort(key=lambda m: m["date"])
            print(f"Added {len(wc2026)} WC 2026 matches\n")
            run_backtest(matches=matches)
        else:
            run_backtest()
        # Also run xG backtest if data available
        print("\n" + "=" * 60)
        print("xG MODEL BACKTEST (StatsBomb data)")
        print("=" * 60)
        try:
            from models.xg import load_xg_data
            xg_matches = load_xg_data()
            if xg_matches:
                result = backtest_xg(xg_matches)
                print(f"  Matches: {result['n_matches']}")
                print(f"  Accuracy: {result['accuracy']:.1%}")
                print(f"  Log-loss: {result['log_loss']:.4f}")
                print(f"  Brier:    {result['brier']:.4f}")
                # Per-competition
                comps = {}
                for d in result["details"]:
                    comp = d["competition"]
                    if comp not in comps:
                        comps[comp] = {"total": 0, "correct": 0}
                    comps[comp]["total"] += 1
                    if d["correct"]:
                        comps[comp]["correct"] += 1
                print(f"\n  {'Tournament':<25} {'Matches':>8} {'Correct':>8} {'Accuracy':>10}")
                print("  " + "-" * 51)
                for comp in sorted(comps):
                    c = comps[comp]
                    print(f"  {comp:<25} {c['total']:>8} {c['correct']:>8} {c['correct']/c['total']:>9.1%}")
            else:
                print("  No xG data. Run: python data_pipeline/scrape_xg.py")
        except ImportError:
            print("  xG model not available")
        except FileNotFoundError:
            print("  No xG data. Run: python data_pipeline/scrape_xg.py")

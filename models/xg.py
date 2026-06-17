"""Expected Goals (xG) model for football match prediction.

Uses rolling xG averages (xG for, xG against) instead of Elo ratings to
estimate expected goals. The xG metric is provably more predictive than
actual results (Heuer & Rubner, 2012).

Data source: StatsBomb open data (World Cup 2018/2022, Euro 2020/2024, Copa 2024)
"""

import csv
import math
from pathlib import Path
from collections import defaultdict

# Shared with poisson.py
AVG_GOALS = 2.7
MAX_GOALS = 10
HOME_ADVANTAGE_GOALS = 0.3
ROLLING_WINDOW = 10  # matches for rolling xG average

# Average xG per match (used for normalization)
# Across ~250 international matches, avg xG per team is ~1.2
LEAGUE_AVG_XG = 1.2


def load_xg_data(data_dir=None):
    """Load xG match data from CSV.

    Returns list of dicts: date, home_team, away_team, home_xg, away_xg,
    home_goals, away_goals, competition.
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data" / "historical" / "xg"
    path = Path(data_dir) / "matches.csv"
    if not path.exists():
        return []

    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append({
                "date": r["date"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "home_xg": float(r["home_xg"]),
                "away_xg": float(r["away_xg"]),
                "home_goals": int(r["home_goals"]),
                "away_goals": int(r["away_goals"]),
                "competition": r.get("competition", ""),
            })
    return rows


def compute_xg_strengths(xg_matches, reference_date=None):
    """Compute rolling xG attack/defense strengths for all teams.

    Walks matches chronologically. For each match, computes strengths from
    prior matches only (no look-ahead bias).

    Args:
        xg_matches: list of xG match dicts, sorted by date
        reference_date: if set, only use matches before this date

    Returns:
        (attack, defense) dicts: {team: multiplier}
        multiplier > 1.0 = above average; defense > 1.0 = leaky
    """
    # Rolling xG for/against per team
    xg_for = defaultdict(list)
    xg_against = defaultdict(list)

    attack = {}
    defense = {}

    for m in xg_matches:
        if reference_date and m["date"] > reference_date:
            continue

        home = m["home_team"]
        away = m["away_team"]

        # Compute current strengths (from prior matches)
        for team in [home, away]:
            if team not in attack:  # Only compute once
                gf = xg_for[team]
                ga = xg_against[team]
                if len(gf) >= 3:
                    avg_gf = sum(gf[-ROLLING_WINDOW:]) / min(len(gf), ROLLING_WINDOW)
                    avg_ga = sum(ga[-ROLLING_WINDOW:]) / min(len(ga), ROLLING_WINDOW)
                    attack[team] = max(0.3, avg_gf / LEAGUE_AVG_XG)
                    defense[team] = max(0.3, avg_ga / LEAGUE_AVG_XG)
                else:
                    attack[team] = 1.0
                    defense[team] = 1.0

        # Update rolling stats with this match's xG
        xg_for[home].append(m["home_xg"])
        xg_against[home].append(m["away_xg"])
        xg_for[away].append(m["away_xg"])
        xg_against[away].append(m["home_xg"])

    return attack, defense


def expected_goals_xg(att_home, def_away, att_away, def_home, neutral=True):
    """Estimate expected goals from xG-based attack/defense strengths.

    Formula: lambda = attack_strength × opponent_defense × league_avg + home_adv
    """
    ha = 0 if neutral else HOME_ADVANTAGE_GOALS
    home_lambda = att_home * def_away * LEAGUE_AVG_XG + ha
    away_lambda = att_away * def_home * LEAGUE_AVG_XG
    return max(0.2, home_lambda), max(0.2, away_lambda)


def xg_match_probabilities(att_home, def_home, att_away, def_away, neutral=True):
    """Predict match outcome using xG-based Poisson model.

    Returns {home, draw, away, home_lambda, away_lambda}.
    """
    home_lambda, away_lambda = expected_goals_xg(
        att_home, def_away, att_away, def_home, neutral=neutral)

    # Score probability matrix (same as poisson.py)
    probs = [[0.0] * (MAX_GOALS + 1) for _ in range(MAX_GOALS + 1)]
    for i in range(MAX_GOALS + 1):
        p_i = _poisson_pmf(i, home_lambda)
        for j in range(MAX_GOALS + 1):
            probs[i][j] = p_i * _poisson_pmf(j, away_lambda)

    # Dixon-Coles adjustment
    probs = _dixon_coles(probs, home_lambda, away_lambda)

    prob_home = prob_draw = prob_away = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            if i > j:
                prob_home += probs[i][j]
            elif i == j:
                prob_draw += probs[i][j]
            else:
                prob_away += probs[i][j]

    return {
        "home": round(prob_home, 4),
        "draw": round(prob_draw, 4),
        "away": round(prob_away, 4),
        "home_lambda": round(home_lambda, 2),
        "away_lambda": round(away_lambda, 2),
    }


def _poisson_pmf(k, lam):
    """Poisson PMF: P(X=k) = (lambda^k * e^(-lambda)) / k!"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _dixon_coles(probs, home_lambda, away_lambda, rho=-0.13):
    """Dixon-Coles adjustment for low-scoring draws."""
    n = len(probs)
    adjusted = [row[:] for row in probs]
    lambda_prod = home_lambda * away_lambda
    adjusted[0][0] = probs[0][0] * (1 - lambda_prod * rho)
    adjusted[1][1] = probs[1][1] * (1 + (1 - home_lambda) * (1 - away_lambda) * rho)
    total = sum(sum(row) for row in adjusted)
    if total > 0:
        for i in range(n):
            for j in range(n):
                adjusted[i][j] /= total
    return adjusted


# --- CLI ---


if __name__ == "__main__":
    import sys
    data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    matches = load_xg_data(data_dir)
    if not matches:
        print("No xG data found. Run data_pipeline/scrape_xg.py first.")
        sys.exit(1)

    print(f"Loaded {len(matches)} matches with xG data")

    # Compute strengths over the full dataset
    attack, defense = compute_xg_strengths(matches)
    teams = sorted(set(m["home_team"] for m in matches) | set(m["away_team"] for m in matches))
    wc_teams = [t for t in teams if t in {
        "Argentina", "Brazil", "England", "France", "Germany", "Spain",
        "Portugal", "Netherlands", "Croatia", "Uruguay", "Colombia", "Senegal",
        "Morocco", "Japan", "South Korea", "United States", "Mexico", "Belgium",
        "Switzerland", "Canada", "Qatar", "Wales", "Poland", "Denmark",
        "Serbia", "Cameroon", "Ghana", "Ecuador", "Saudi Arabia", "Iran",
        "Tunisia", "Australia", "Costa Rica",
    }]

    print(f"\n{'Team':<18} {'xG Attack':>10} {'xG Defense':>10}")
    print("-" * 40)
    for team in sorted(wc_teams, key=lambda t: attack.get(t, 1.0), reverse=True):
        if team in attack:
            print(f"{team:<18} {attack[team]:>10.2f} {defense[team]:>10.2f}")

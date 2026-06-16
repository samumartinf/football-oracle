"""Poisson model for football match score prediction.

Models goals scored as Poisson random variables with lambda derived from Elo ratings.
Includes the Dixon-Coles adjustment for low-scoring draws.

Pure Python — no scipy/numpy dependency.
"""
import math

AVG_GOALS = 2.7
HOME_ADVANTAGE_GOALS = 0.3
MAX_GOALS = 10


def poisson_pmf(k, lam):
    """Poisson PMF: P(X=k) = (lambda^k * e^(-lambda)) / k!"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def expected_goals(elo_home, elo_away, neutral=True):
    """Estimate expected goals (lambda) for each team based on Elo ratings."""
    ha = 0 if neutral else HOME_ADVANTAGE_GOALS
    elo_diff = (elo_home - elo_away) / 100 * 0.35
    home_lambda = AVG_GOALS / 2 + elo_diff / 2 + ha
    away_lambda = AVG_GOALS / 2 - elo_diff / 2
    return max(0.2, home_lambda), max(0.2, away_lambda)


def score_probability(home_lambda, away_lambda, max_goals=None):
    """Compute probability matrix for all scorelines up to max_goals.

    Returns a 2D list where [i][j] = P(home=i, away=j).
    """
    if max_goals is None:
        max_goals = MAX_GOALS

    probs = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]

    for i in range(max_goals + 1):
        p_i = poisson_pmf(i, home_lambda)
        for j in range(max_goals + 1):
            probs[i][j] = p_i * poisson_pmf(j, away_lambda)

    return probs


def dixon_coles_adjust(probs, home_lambda, away_lambda, rho=-0.13):
    """Apply Dixon-Coles adjustment to reduce probability of 0-0 and 1-1."""
    n = len(probs)
    adjusted = [row[:] for row in probs]  # deep copy

    lambda_prod = home_lambda * away_lambda
    tau_00 = 1 - lambda_prod * rho
    tau_11 = 1 + (1 - home_lambda) * (1 - away_lambda) * rho

    adjusted[0][0] = probs[0][0] * tau_00
    adjusted[1][1] = probs[1][1] * tau_11

    # Re-normalize
    total = sum(sum(row) for row in adjusted)
    if total > 0:
        for i in range(n):
            for j in range(n):
                adjusted[i][j] /= total

    return adjusted


def _argmax_2d(matrix):
    """Find (row, col) of maximum value in a 2D list."""
    max_val = -1.0
    max_pos = (0, 0)
    for i, row in enumerate(matrix):
        for j, val in enumerate(row):
            if val > max_val:
                max_val = val
                max_pos = (i, j)
    return max_pos


def match_probabilities(elo_home, elo_away, neutral=True):
    """Predict match outcome probabilities using Poisson model.

    Returns dict with home, draw, away probabilities and most likely scores.
    """
    home_lambda, away_lambda = expected_goals(elo_home, elo_away, neutral=neutral)
    probs = score_probability(home_lambda, away_lambda)
    probs = dixon_coles_adjust(probs, home_lambda, away_lambda)

    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0

    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            if i > j:
                prob_home += probs[i][j]
            elif i == j:
                prob_draw += probs[i][j]
            else:
                prob_away += probs[i][j]

    max_i, max_j = _argmax_2d(probs)

    return {
        "home": round(prob_home, 4),
        "draw": round(prob_draw, 4),
        "away": round(prob_away, 4),
        "home_lambda": round(home_lambda, 2),
        "away_lambda": round(away_lambda, 2),
        "most_likely_score": f"{max_i}-{max_j}",
        "most_likely_prob": round(probs[max_i][max_j], 4),
    }


def predict_match(home_team, away_team, dataset, neutral=True):
    """Predict match outcome from team names using Poisson model."""
    home_elo = dataset[home_team]["elo"]
    away_elo = dataset[away_team]["elo"]

    if home_elo is None or away_elo is None:
        return {"home": 0.40, "draw": 0.30, "away": 0.30}

    return match_probabilities(home_elo, away_elo, neutral=neutral)

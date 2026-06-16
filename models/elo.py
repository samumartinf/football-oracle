"""Convert Elo ratings to match outcome probabilities.

Uses the standard Elo expected score formula for win probabilities,
then derives draw probability from the closeness of the matchup.
"""
import math

HOME_ADVANTAGE = 100


def expected_score(elo_a, elo_b):
    """Expected score for team A vs team B (0 to 1)."""
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def elo_to_probabilities(elo_home, elo_away, neutral=False):
    """
    Convert Elo ratings to home/draw/away probabilities.

    Returns (prob_home_win, prob_draw, prob_away_win) summing to 1.0.
    """
    ha = 0 if neutral else HOME_ADVANTAGE
    adj_home = elo_home + ha

    exp_home = expected_score(adj_home, elo_away)

    elo_diff = abs(adj_home - elo_away)
    prob_draw = 0.30 * math.exp(-elo_diff / 800)

    remaining = 1.0 - prob_draw
    prob_home = remaining * exp_home
    prob_away = remaining * (1 - exp_home)

    return prob_home, prob_draw, prob_away


def predict_match(home_team, away_team, dataset, neutral=False):
    """
    Predict match outcome probabilities from team names.

    Args:
        home_team: str, team name
        away_team: str, team name
        dataset: dict from team_dataset.json
        neutral: bool, True for World Cup (no home advantage)

    Returns:
        dict with home, draw, away probabilities
    """
    home_elo = dataset[home_team]["elo"]
    away_elo = dataset[away_team]["elo"]

    if home_elo is None or away_elo is None:
        return {"home": 0.40, "draw": 0.30, "away": 0.30}

    prob_home, prob_draw, prob_away = elo_to_probabilities(home_elo, away_elo, neutral=neutral)

    return {
        "home": round(prob_home, 4),
        "draw": round(prob_draw, 4),
        "away": round(prob_away, 4),
        "elo_home": home_elo,
        "elo_away": away_elo,
    }

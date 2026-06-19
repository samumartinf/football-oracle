"""Ensemble predictor blending Elo, Poisson, decomposed Poisson, and market odds."""

import json
from pathlib import Path
from models.elo import predict_match as elo_predict
from models.poisson import (
    predict_match as poisson_predict,
    compute_strengths,
    match_probabilities_decomposed,
)
from models.xg import (
    load_xg_data,
    compute_xg_strengths,
    xg_match_probabilities,
)

TEAM_ALIASES = {
    "Czech Republic": "Czechia",
    "Bosnia & Herzegovina": "Bosnia",
    "D.R. Congo": "DR Congo",
    "Democratic Republic of Congo": "DR Congo",
    "Turkey": "Türkiye",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "USA": "United States",
    "United States of America": "United States",
}


def normalize_team_name(team_name):
    """Map common football naming variants to dataset keys."""
    return TEAM_ALIASES.get(team_name, team_name)


class EnsemblePredictor:
    """Blend multiple models into a single prediction with configurable weights.
    
    Default weights from backtest grid search on 339 historical matches:
    25% Elo / 0% Poisson (Elo-based) / 75% Decomposed Poisson / 0% Market
    """

    def __init__(self, dataset, weights=None):
        self.dataset = dataset
        self.weights = weights or {
            "elo": 0.25, "poisson": 0.0, "decomposed": 0.75, "xg": 0.0, "market": 0.0,
        }
        # Pre-compute attack/defense strengths (goals-based)
        self.attack, self.defense = compute_strengths(dataset)
        # Pre-compute xG strengths (StatsBomb data)
        self.xg_attack = {}
        self.xg_defense = {}
        try:
            xg_matches = load_xg_data()
            if xg_matches:
                self.xg_attack, self.xg_defense = compute_xg_strengths(xg_matches)
        except (FileNotFoundError, Exception):
            pass  # xG data not available — model will be skipped

    def predict(self, home_team, away_team, neutral=True):
        """Blend all available models into a single prediction.

        When a team lacks goal data (MP < 5), decomposed weight is reduced
        and shifted to Elo, since the decomposed model can't distinguish
        team quality without goal history.
        """
        home_team = normalize_team_name(home_team)
        away_team = normalize_team_name(away_team)

        home_probs = []
        draw_probs = []
        away_probs = []
        models_used = {}
        active_weight = 0.0

        # Per-match weight adjustment: reduce decomposed weight when
        # teams lack goal data (no pre-tournament GF/GA to model from)
        home_mp = self.dataset.get(home_team, {}).get("matches_played", 0)
        away_mp = self.dataset.get(away_team, {}).get("matches_played", 0)
        min_mp = min(home_mp, away_mp)
        goal_trust = min(min_mp / 5, 1.0)  # 0 matches → 0% trust, 5+ → 100%

        base_elo = self.weights.get("elo", 0)
        base_decom = self.weights.get("decomposed", 0)

        # Shift weight from decomposed to Elo based on data scarcity
        adj_elo = base_elo + base_decom * (1 - goal_trust)
        adj_decom = base_decom * goal_trust

        # Elo model
        try:
            result = elo_predict(home_team, away_team, self.dataset, neutral=neutral)
            w = adj_elo
            if w > 0:
                home_probs.append(result["home"] * w)
                draw_probs.append(result["draw"] * w)
                away_probs.append(result["away"] * w)
                models_used["elo"] = result
                active_weight += w
        except (KeyError, TypeError):
            pass

        # Poisson (Elo-based)
        try:
            result = poisson_predict(home_team, away_team, self.dataset, neutral=neutral)
            w = self.weights.get("poisson", 0)
            if w > 0:
                home_probs.append(result["home"] * w)
                draw_probs.append(result["draw"] * w)
                away_probs.append(result["away"] * w)
                models_used["poisson"] = result
                active_weight += w
        except (KeyError, TypeError):
            pass

        # Decomposed Poisson (attack/defense strengths)
        w = adj_decom
        if w > 0:
            att_h = self.attack.get(home_team, 1.0)
            def_h = self.defense.get(home_team, 1.0)
            att_a = self.attack.get(away_team, 1.0)
            def_a = self.defense.get(away_team, 1.0)

            result = match_probabilities_decomposed(
                att_h, def_h, att_a, def_a, neutral=neutral)
            home_probs.append(result["home"] * w)
            draw_probs.append(result["draw"] * w)
            away_probs.append(result["away"] * w)
            active_weight += w
            models_used["decomposed"] = {
                "home": result["home"],
                "draw": result["draw"],
                "away": result["away"],
                "home_lambda": result["home_lambda"],
                "away_lambda": result["away_lambda"],
                "att_h": round(att_h, 2),
                "def_h": round(def_h, 2),
                "att_a": round(att_a, 2),
                "def_a": round(def_a, 2),
            }

        # xG-based Poisson (StatsBomb xG data)
        w = self.weights.get("xg", 0)
        if w > 0 and self.xg_attack:
            att_h = self.xg_attack.get(home_team)
            def_h = self.xg_defense.get(home_team)
            att_a = self.xg_attack.get(away_team)
            def_a = self.xg_defense.get(away_team)

            if all(v is not None for v in [att_h, def_h, att_a, def_a]):
                result = xg_match_probabilities(
                    att_h, def_h, att_a, def_a, neutral=neutral)
                home_probs.append(result["home"] * w)
                draw_probs.append(result["draw"] * w)
                away_probs.append(result["away"] * w)
                active_weight += w
                models_used["xg"] = {
                    "home": result["home"],
                    "draw": result["draw"],
                    "away": result["away"],
                    "home_lambda": result["home_lambda"],
                    "away_lambda": result["away_lambda"],
                    "att_h": round(att_h, 2),
                    "def_h": round(def_h, 2),
                    "att_a": round(att_a, 2),
                    "def_a": round(def_a, 2),
                }

        # Market odds
        home_data = self.dataset.get(home_team, {})
        market = home_data.get("market_prob")
        w = self.weights.get("market", 0)
        if market and w > 0:
            home_probs.append(market["prob_win"] * w)
            draw_probs.append(market["prob_draw"] * w)
            away_probs.append(market["prob_lose"] * w)
            active_weight += w
            models_used["market"] = {
                "home": market["prob_win"],
                "draw": market["prob_draw"],
                "away": market["prob_lose"],
            }

        if not home_probs:
            return {"home": 0.40, "draw": 0.30, "away": 0.30, "models": {}}

        scale = 1.0 / active_weight if active_weight > 0 else 1.0

        return {
            "home": round(sum(home_probs) * scale, 4),
            "draw": round(sum(draw_probs) * scale, 4),
            "away": round(sum(away_probs) * scale, 4),
            "models": models_used,
        }


def load_dataset():
    """Load the team dataset from Phase 2 output."""
    path = Path(__file__).parent.parent / "data" / "historical" / "team_dataset.json"
    with open(path) as f:
        return json.load(f)

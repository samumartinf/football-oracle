"""Ensemble predictor blending Elo, Poisson, and market odds models."""
import json
from pathlib import Path
from models.elo import predict_match as elo_predict
from models.poisson import predict_match as poisson_predict


class EnsemblePredictor:
    """Blend multiple models into a single prediction with configurable weights."""

    def __init__(self, dataset, weights=None):
        self.dataset = dataset
        self.weights = weights or {"elo": 0.3, "poisson": 0.4, "market": 0.3}

    def predict(self, home_team, away_team, neutral=True):
        """Blend all available models into a single prediction."""
        home_probs = []
        draw_probs = []
        away_probs = []
        models_used = {}

        # Elo model
        try:
            result = elo_predict(home_team, away_team, self.dataset, neutral=neutral)
            w = self.weights["elo"]
            home_probs.append(result["home"] * w)
            draw_probs.append(result["draw"] * w)
            away_probs.append(result["away"] * w)
            models_used["elo"] = result
        except (KeyError, TypeError):
            pass

        # Poisson model
        try:
            result = poisson_predict(home_team, away_team, self.dataset, neutral=neutral)
            w = self.weights["poisson"]
            home_probs.append(result["home"] * w)
            draw_probs.append(result["draw"] * w)
            away_probs.append(result["away"] * w)
            models_used["poisson"] = result
        except (KeyError, TypeError):
            pass

        # Market odds
        home_data = self.dataset.get(home_team, {})
        market = home_data.get("market_prob")
        if market:
            w = self.weights["market"]
            home_probs.append(market["prob_win"] * w)
            draw_probs.append(market["prob_draw"] * w)
            away_probs.append(market["prob_lose"] * w)
            models_used["market"] = {
                "home": market["prob_win"],
                "draw": market["prob_draw"],
                "away": market["prob_lose"],
            }

        if not home_probs:
            return {"home": 0.40, "draw": 0.30, "away": 0.30, "models": {}}

        total_weight = sum(self.weights[m] for m in models_used if m in self.weights)
        scale = 1.0 / total_weight if total_weight > 0 else 1.0

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

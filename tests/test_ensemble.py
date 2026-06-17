"""Tests for ensemble prediction model."""
import json
from pathlib import Path
from models.ensemble import EnsemblePredictor

DATASET_PATH = Path(__file__).parent.parent / "data" / "historical" / "team_dataset.json"


def load_dataset():
    with open(DATASET_PATH) as f:
        return json.load(f)


def test_ensemble_predicts():
    """Ensemble should return probabilities for a known matchup."""
    data = load_dataset()
    predictor = EnsemblePredictor(data)
    result = predictor.predict("England", "Croatia")
    assert "home" in result and "draw" in result and "away" in result
    assert abs(result["home"] + result["draw"] + result["away"] - 1.0) < 0.01


def test_ensemble_weights_sum():
    """Model weights should sum to 1."""
    data = load_dataset()
    predictor = EnsemblePredictor(data)
    weights = predictor.weights
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.01


def test_ensemble_fallback_no_elo():
    """Fallback for unknown teams should produce valid probabilities summing to 1."""
    predictor = EnsemblePredictor({})
    result = predictor.predict("Nonexistent", "FakeTeam")
    # Probabilities should sum to 1.0 (valid distribution)
    total = result["home"] + result["draw"] + result["away"]
    assert abs(total - 1.0) < 0.01, f"Probs sum to {total}"
    # All probabilities should be between 0 and 1
    assert 0 < result["home"] < 1
    assert 0 < result["draw"] < 1
    assert 0 < result["away"] < 1


def test_ensemble_england_croatia():
    """England-Croatia: our contrarian pick should show close EV."""
    data = load_dataset()
    predictor = EnsemblePredictor(data)
    result = predictor.predict("England", "Croatia", neutral=True)
    print(f"\nEngland-Croatia: H={result['home']:.3f} D={result['draw']:.3f} A={result['away']:.3f}")
    # Both teams exist in dataset — should have non-trivial probabilities
    assert result["home"] > 0.30
    assert result["away"] > 0.20

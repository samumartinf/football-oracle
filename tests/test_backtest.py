"""Backtest ensemble against 2022 World Cup group stage results."""
import json
from pathlib import Path
from models.ensemble import EnsemblePredictor

WC2022_RESULTS = [
    # Group stage: (home, away, actual_outcome)
    ("Argentina", "Saudi Arabia", "away"),   # Famous upset
    ("France", "Australia", "home"),
    ("Germany", "Japan", "away"),            # Another upset
    ("Spain", "Costa Rica", "home"),
    ("Belgium", "Canada", "home"),
    ("Morocco", "Croatia", "draw"),
    ("Brazil", "Serbia", "home"),
    ("Portugal", "Ghana", "home"),
    ("England", "Iran", "home"),
    ("Netherlands", "Senegal", "home"),
    ("Argentina", "France", "draw"),         # Final
]

DATASET_PATH = Path(__file__).parent.parent / "data" / "historical" / "team_dataset.json"


def load_dataset():
    with open(DATASET_PATH) as f:
        return json.load(f)


def test_backtest_accuracy():
    """Ensemble should predict >45% of outcomes correctly."""
    data = load_dataset()
    predictor = EnsemblePredictor(data)

    correct = 0
    total = 0
    skipped = 0

    for home, away, actual in WC2022_RESULTS:
        if home not in data or away not in data:
            skipped += 1
            continue

        result = predictor.predict(home, away, neutral=True)
        predicted = max(result["home"], result["draw"], result["away"])
        predicted_outcome = (
            "home" if result["home"] == predicted
            else "draw" if result["draw"] == predicted
            else "away"
        )

        if predicted_outcome == actual:
            correct += 1
        total += 1

    accuracy = correct / total if total > 0 else 0
    print(f"\nBacktest: {correct}/{total} correct ({accuracy:.1%}), {skipped} skipped")
    assert accuracy > 0.45, f"Accuracy {accuracy:.1%} below 45% threshold"

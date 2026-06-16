"""Merge data from all sources into a unified team-stats dataset."""
import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "historical"

WC_TEAMS = {
    "France", "Senegal", "Iraq", "Norway",
    "Argentina", "Algeria", "Austria", "Jordan",
    "Portugal", "DR Congo", "England", "Croatia",
    "Ghana", "Panama", "Uzbekistan", "Colombia",
    "Czech Republic", "South Africa", "Switzerland", "Bosnia",
    "Canada", "Qatar",
}


def build_team_dataset():
    """Merge Elo, results, and odds into one JSON dataset."""
    dataset = {team: {
        "name": team,
        "elo": None,
        "recent_form": [],
        "goals_for_5": 0,
        "goals_against_5": 0,
        "market_prob": None,
    } for team in WC_TEAMS}

    elo_path = DATA_DIR / "elo" / "current_elo.csv"
    if elo_path.exists():
        with open(elo_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["team"] in dataset:
                    dataset[row["team"]]["elo"] = int(row["elo"])

    results_path = DATA_DIR / "results" / "recent_matches.csv"
    if results_path.exists():
        with open(results_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                team = row["team"]
                if team not in dataset:
                    continue
                dataset[team]["recent_form"].append(row["result"])
                try:
                    dataset[team]["goals_for_5"] += int(row["gf"])
                    dataset[team]["goals_against_5"] += int(row["ga"])
                except ValueError:
                    pass

    for team in dataset:
        dataset[team]["recent_form"] = dataset[team]["recent_form"][:5]

    odds_path = DATA_DIR / "odds" / "upcoming_odds.csv"
    if odds_path.exists():
        with open(odds_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                home = row["home"]
                away = row["away"]
                if home in dataset:
                    dataset[home]["market_prob"] = {
                        "opponent": away,
                        "prob_win": float(row.get("prob_home", 0)),
                        "prob_draw": float(row.get("prob_draw", 0)),
                        "prob_lose": float(row.get("prob_away", 0)),
                    }

    output = DATA_DIR / "team_dataset.json"
    with open(output, 'w') as f:
        json.dump(dataset, f, indent=2)

    teams_with_elo = sum(1 for t in dataset.values() if t['elo'])
    teams_with_form = sum(1 for t in dataset.values() if t['recent_form'])
    teams_with_odds = sum(1 for t in dataset.values() if t['market_prob'])

    print(f"Team dataset saved to {output}")
    print(f"Teams with Elo: {teams_with_elo}/{len(dataset)}")
    print(f"Teams with form: {teams_with_form}/{len(dataset)}")
    print(f"Teams with odds: {teams_with_odds}/{len(dataset)}")
    return dataset


if __name__ == "__main__":
    build_team_dataset()

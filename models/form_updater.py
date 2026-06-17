"""Apply live tournament results to the team dataset.

Updates Elo ratings, goals_for/goals_against, matches_played, and recent_form
based on completed World Cup matches fetched from the MPP API.

Idempotent — safe to run multiple times. Pre-tournament data is snapshotted
on first run and tournament data is always recomputed fresh.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.elo import expected_score

ELO_K = 32
INITIAL_ELO = 1500
HOME_ADVANTAGE = 100


def _outcome(hg, ag):
    if hg > ag:
        return "home"
    if hg == ag:
        return "draw"
    return "away"


def _form_char(hg, ag):
    if hg > ag:
        return "W"
    if hg == ag:
        return "D"
    return "L"


def _form_char_reverse(hg, ag):
    if ag > hg:
        return "W"
    if ag == hg:
        return "D"
    return "L"


def update_elo(elo_home, elo_away, hg, ag):
    """Update Elo ratings after a match. Returns (new_home, new_away)."""
    exp_home = expected_score(elo_home + HOME_ADVANTAGE, elo_away)

    if hg > ag:
        result = 1.0
    elif hg == ag:
        result = 0.5
    else:
        result = 0.0

    goal_diff = abs(hg - ag)
    k = ELO_K * (1 + goal_diff / 4) if goal_diff <= 3 else ELO_K * 1.75

    new_home = elo_home + k * (result - exp_home)
    new_away = elo_away + k * ((1 - result) - (1 - exp_home))
    return round(new_home), round(new_away)


def _snapshot_pre_data(dataset, team):
    """Snapshot current values as pre-tournament baseline (only once)."""
    if f"_pre_elo_{team}" not in dataset:
        dataset[f"_pre_elo_{team}"] = dataset.get(team, {}).get("elo", INITIAL_ELO)
        dataset[f"_pre_gf_{team}"] = dataset.get(team, {}).get("goals_for", 0)
        dataset[f"_pre_ga_{team}"] = dataset.get(team, {}).get("goals_against", 0)
        dataset[f"_pre_mp_{team}"] = dataset.get(team, {}).get("matches_played", 0)
        dataset[f"_pre_form_{team}"] = list(dataset.get(team, {}).get("recent_form", []))


def apply_results(dataset, results):
    """Apply match results to a team dataset in-place. Idempotent.

    Pre-tournament data is snapshotted on first run.
    Tournament Elo, GF/GA, and form are always recomputed fresh from
    all results and added on top of the pre-tournament baseline.
    """
    # Snapshot pre-tournament data for all teams mentioned in results
    for r in results:
        for team in (r["home"], r["away"]):
            if team not in dataset:
                dataset[team] = {
                    "name": team, "elo": INITIAL_ELO,
                    "goals_for": 0, "goals_against": 0,
                    "matches_played": 0, "recent_form": [],
                }
            _snapshot_pre_data(dataset, team)

    # Build Elo table from pre-tournament baseline
    elo = {}
    for team_key in dataset:
        if team_key.startswith("_"):
            continue
        elo[team_key] = dataset.get(f"_pre_elo_{team_key}", dataset[team_key].get("elo", INITIAL_ELO))

    # Compute tournament stats from all results
    tourney_gf = defaultdict(int)
    tourney_ga = defaultdict(int)
    tourney_mp = defaultdict(int)
    form_map = defaultdict(list)

    for r in results:
        home = r["home"]
        away = r["away"]
        hg = r["hg"]
        ag = r["ag"]

        # Ensure Elo entries exist
        if home not in elo:
            elo[home] = INITIAL_ELO
        if away not in elo:
            elo[away] = INITIAL_ELO

        # Update Elo (chronological — order matters)
        elo[home], elo[away] = update_elo(elo[home], elo[away], hg, ag)

        # Tournament stats
        tourney_gf[home] += hg
        tourney_ga[home] += ag
        tourney_mp[home] += 1
        tourney_gf[away] += ag
        tourney_ga[away] += hg
        tourney_mp[away] += 1

        # Form
        form_map[home].append(_form_char(hg, ag))
        form_map[away].append(_form_char_reverse(hg, ag))

    # Apply: pre + tournament
    for team_key in list(dataset.keys()):
        if team_key.startswith("_"):
            continue

        # Elo
        if team_key in elo:
            dataset[team_key]["elo"] = elo[team_key]

        # GF/GA/MP = pre + tournament
        pre_gf = dataset.get(f"_pre_gf_{team_key}", 0)
        pre_ga = dataset.get(f"_pre_ga_{team_key}", 0)
        pre_mp = dataset.get(f"_pre_mp_{team_key}", 0)

        dataset[team_key]["goals_for"] = pre_gf + tourney_gf.get(team_key, 0)
        dataset[team_key]["goals_against"] = pre_ga + tourney_ga.get(team_key, 0)
        dataset[team_key]["matches_played"] = pre_mp + tourney_mp.get(team_key, 0)

        # Form = pre + tournament (last 10)
        pre_form = dataset.get(f"_pre_form_{team_key}", [])
        combined = list(pre_form) + form_map.get(team_key, [])
        dataset[team_key]["recent_form"] = combined[-10:]

    return dataset


def apply_tournament_form(dataset_path=None, results=None):
    """Fetch live results and update the team dataset JSON."""
    if dataset_path is None:
        dataset_path = (
            Path(__file__).parent.parent / "data" / "historical" / "team_dataset.json"
        )

    with open(dataset_path) as f:
        dataset = json.load(f)

    if results is None:
        from mpp.results import get_completed_matches
        results = get_completed_matches()

    if not results:
        print("No completed matches found.")
        return dataset

    print(f"Applying {len(results)} completed match results...")
    dataset = apply_results(dataset, results)

    with open(dataset_path, "w") as f:
        json.dump(dataset, f, indent=2)

    n_teams = sum(1 for k in dataset if not k.startswith("_"))
    print(f"Updated {n_teams} teams in {dataset_path}")

    print("\nKey Elo changes:")
    changes = []
    for team, data in dataset.items():
        if team.startswith("_"):
            continue
        gf = data.get("goals_for", 0)
        elo_val = data.get("elo", INITIAL_ELO)
        form = " ".join(data.get("recent_form", [])[-3:])
        changes.append((team, elo_val, gf, form))

    changes.sort(key=lambda x: -x[1])
    for team, elo_val, gf, form in changes[:10]:
        print(f"  {team:<20} Elo={elo_val:<5} GF={gf:<3}  recent: {form}")

    return dataset


if __name__ == "__main__":
    apply_tournament_form()

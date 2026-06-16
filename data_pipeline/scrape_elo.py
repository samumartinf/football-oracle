"""Compute Elo ratings from historical international match results."""
import csv
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "historical"

ELO_K = 32
HOME_ADVANTAGE = 100
INITIAL_ELO = 1500

WC_TEAMS = {
    "France", "Senegal", "Iraq", "Norway",
    "Argentina", "Algeria", "Austria", "Jordan",
    "Portugal", "DR Congo", "England", "Croatia",
    "Ghana", "Panama", "Uzbekistan", "Colombia",
    "Czech Republic", "South Africa", "Switzerland", "Bosnia",
    "Canada", "Qatar",
}

XLSX_TEAM_MAP = {
    "D.R. Congo": "DR Congo",
    "Bosnia & Herzegovina": "Bosnia",
}

WC_XLSX_URL = "https://www.football-data.co.uk/WorldCup2026.xlsx"


def expected_score(elo_a, elo_b):
    """Expected score for team A vs team B (0 to 1)."""
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def update_elo(elo_home, elo_away, home_goals, away_goals):
    """Update Elo ratings after a match. Returns new (home_elo, away_elo)."""
    exp_home = expected_score(elo_home + HOME_ADVANTAGE, elo_away)

    if home_goals > away_goals:
        result = 1
    elif home_goals == away_goals:
        result = 0.5
    else:
        result = 0

    goal_diff = abs(home_goals - away_goals)
    k = ELO_K * (1 + goal_diff / 4) if goal_diff <= 3 else ELO_K * 1.75

    new_home = elo_home + k * (result - exp_home)
    new_away = elo_away + k * ((1 - result) - (1 - exp_home))

    return round(new_home), round(new_away)


def fetch_match_data():
    """Fetch match data from the World Cup XLSX file (qualifiers + past WCs)."""
    import pandas as pd

    xlsx_path = DATA_DIR / "worldcup_data.xlsx"

    if not xlsx_path.exists():
        print("  Downloading World Cup data XLSX...")
        resp = requests.get(WC_XLSX_URL, timeout=30)
        resp.raise_for_status()
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        with open(xlsx_path, 'wb') as f:
            f.write(resp.content)
        print(f"  Saved to {xlsx_path}")

    xls = pd.ExcelFile(xlsx_path)
    rows = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        if sheet == "WorldCup2026Qualifiers":
            for _, r in df.iterrows():
                home = XLSX_TEAM_MAP.get(str(r["Home"]).strip(), str(r["Home"]).strip())
                away = XLSX_TEAM_MAP.get(str(r["Away"]).strip(), str(r["Away"]).strip())
                rows.append({
                    "home": home,
                    "away": away,
                    "hg": int(r["HG"]) if pd.notna(r["HG"]) else None,
                    "ag": int(r["AG"]) if pd.notna(r["AG"]) else None,
                })
        elif sheet in ("WorldCup2022", "WorldCup2018", "WorldCup2014"):
            for _, r in df.iterrows():
                home = XLSX_TEAM_MAP.get(str(r["Home"]).strip(), str(r["Home"]).strip())
                away = XLSX_TEAM_MAP.get(str(r["Away"]).strip(), str(r["Away"]).strip())
                rows.append({
                    "home": home,
                    "away": away,
                    "hg": int(r["HGFT"]) if pd.notna(r["HGFT"]) else None,
                    "ag": int(r["AGFT"]) if pd.notna(r["AGFT"]) else None,
                })

    return rows


def compute_elo_ratings(output_path=None):
    """Compute Elo ratings from all historical international matches."""
    print("Fetching match data from WC XLSX...")
    matches = fetch_match_data()
    print(f"  Got {len(matches)} matches")

    all_matches = matches
    elo = {}

    for m in matches:
        home = m["home"]
        away = m["away"]
        hg = m["hg"]
        ag = m["ag"]

        if home is None or away is None or hg is None or ag is None:
            continue

        if home not in WC_TEAMS and away not in WC_TEAMS:
            continue

        if home not in elo:
            elo[home] = INITIAL_ELO
        if away not in elo:
            elo[away] = INITIAL_ELO

        elo[home], elo[away] = update_elo(elo[home], elo[away], hg, ag)

    sorted_elo = sorted(elo.items(), key=lambda x: x[1], reverse=True)

    output = output_path or DATA_DIR / "elo" / "current_elo.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["team", "elo", "matches_played"])
        for team, rating in sorted_elo:
            if team in WC_TEAMS:
                team_matches = sum(1 for m in all_matches
                                   if m["home"] == team or m["away"] == team)
                writer.writerow([team, rating, team_matches])

    print(f"\nElo ratings saved to {output}")
    for team, rating in sorted_elo[:15]:
        if team in WC_TEAMS:
            print(f"  {team}: {rating}")

    return dict(sorted_elo)


if __name__ == "__main__":
    compute_elo_ratings()

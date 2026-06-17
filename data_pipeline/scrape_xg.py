"""Scrape xG data from StatsBomb open data for international competitions.

Downloads match events from GitHub, extracts shot-level xG, and aggregates
per-team xG for each match.

Output: data/historical/xg/matches.csv
Format: date, home_team, away_team, home_xg, away_xg, home_goals, away_goals, competition
"""

import csv
import json
import urllib.request
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "historical" / "xg"
GITHUB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# International competitions with xG data
COMPETITIONS = [
    ("FIFA World Cup 2022", 43, 106),
    ("FIFA World Cup 2018", 43, 3),
    ("UEFA Euro 2024", 55, 282),
    ("UEFA Euro 2020", 55, 43),
    ("Copa America 2024", 223, 282),
]

# Team name normalization to match our canonical names
TEAM_MAP = {
    "United States": "United States",
    "Korea Republic": "South Korea",
    "Korea DPR": "North Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Bosnia and Herzegovina": "Bosnia",
    "DR Congo": "DR Congo",
}


def _norm(team_name):
    """Normalize StatsBomb team names to our canonical form."""
    return TEAM_MAP.get(team_name, team_name)


def fetch_matches(comp_id, season_id):
    """Fetch match list for a competition."""
    url = f"{GITHUB_BASE}/matches/{comp_id}/{season_id}.json"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_events(match_id):
    """Fetch events for a match (shots, passes, etc.)."""
    url = f"{GITHUB_BASE}/events/{match_id}.json"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def extract_xg(events):
    """Extract xG totals per team from match events.

    Returns (home_xg, away_xg, home_goals, away_goals).
    """
    home_xg = 0.0
    away_xg = 0.0
    home_goals = 0
    away_goals = 0

    # Determine which team is home/away from the first event
    home_team = None
    away_team = None

    for event in events:
        team_name = event.get("team", {}).get("name", "")
        if home_team is None:
            # First event with a team is home (StatsBomb convention: first event
            # in the list is from the home team's tactical lineup)
            if event.get("type", {}).get("name") == "Starting XI":
                # Tactical lineup events have the home team
                tactic = event.get("tactics", {})
                if tactic:
                    home_team = team_name
                    continue
        # Fallback: use possession team from first event
        if home_team is None and event.get("possession_team"):
            home_team = event["possession_team"]["name"]
        if away_team is None and home_team and team_name != home_team:
            away_team = team_name

        # Extract shots with xG
        if event.get("type", {}).get("name") == "Shot":
            shot = event.get("shot", {})
            xg = shot.get("statsbomb_xg", 0)

            if team_name == home_team:
                home_xg += xg
                if shot.get("outcome", {}).get("name") == "Goal":
                    home_goals += 1
            elif team_name == away_team:
                away_xg += xg
                if shot.get("outcome", {}).get("name") == "Goal":
                    away_goals += 1
            elif home_team and away_team:
                # Shouldn't happen, but log if it does
                pass

    return round(home_xg, 3), round(away_xg, 3), home_goals, away_goals


def scrape_all_xg():
    """Scrape xG data for all international competitions."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / "matches.csv"
    rows = []
    skipped = 0

    for comp_name, comp_id, season_id in COMPETITIONS:
        print(f"  {comp_name}...")
        try:
            matches = fetch_matches(comp_id, season_id)
        except Exception as e:
            print(f"    ERROR fetching match list: {e}")
            continue

        for match in matches:
            mid = match["match_id"]
            home_name = _norm(match["home_team"]["home_team_name"])
            away_name = _norm(match["away_team"]["away_team_name"])
            match_date = match.get("match_date", "")

            try:
                events = fetch_events(mid)
            except Exception:
                skipped += 1
                continue

            hxg, axg, hg, ag = extract_xg(events)

            rows.append({
                "date": match_date,
                "home_team": home_name,
                "away_team": away_name,
                "home_xg": hxg,
                "away_xg": axg,
                "home_goals": hg,
                "away_goals": ag,
                "competition": comp_name,
            })

        print(f"    {len(matches)} matches scraped")

    # Sort by date
    rows.sort(key=lambda r: r["date"])

    # Write CSV
    fieldnames = ["date", "home_team", "away_team", "home_xg", "away_xg",
                   "home_goals", "away_goals", "competition"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  Saved {len(rows)} matches to {output_path}")
    if skipped:
        print(f"  ({skipped} matches skipped — events not available)")

    return rows


if __name__ == "__main__":
    print("Scraping xG data from StatsBomb open data...")
    scrape_all_xg()

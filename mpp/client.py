"""MPP API client — fetch matches, submit predictions."""
import json
from pathlib import Path
import requests
from mpp.auth import get_headers

API_BASE = "https://api.mpp.football"
CLUB_CACHE = Path(__file__).parent.parent / "data" / "club_names.json"


def _load_club_names():
    """Load club ID → team name mapping, fetching from API if needed."""
    if CLUB_CACHE.exists():
        with open(CLUB_CACHE) as f:
            return json.load(f)

    headers = get_headers()
    # Get club IDs for active championships
    resp = requests.get(f"{API_BASE}/championship-clubs", headers=headers)
    resp.raise_for_status()
    clubs = resp.json().get("championshipClubs", {})

    mapping = {}
    for cid, club in clubs.items():
        name = club.get("name", {})
        mapping[cid] = name.get("en-GB", name.get("fr-FR", cid))

    with open(CLUB_CACHE, "w") as f:
        json.dump(mapping, f, indent=2)

    return mapping


def get_matches():
    """Fetch all scheduled championship matches with point values and crowd stats."""
    headers = get_headers()
    club_names = _load_club_names()

    resp = requests.get(f"{API_BASE}/championships-current-matches", headers=headers)
    resp.raise_for_status()
    data = resp.json()

    matches = []
    for match_id, match in data.items():
        # Filter to World Cup (championship 8) when available
        if match.get("championshipId") and match["championshipId"] != 8:
            continue
        if match.get("period") not in (None, "scheduled"):
            continue

        home_id = match["home"]["clubId"]
        away_id = match["away"]["clubId"]

        matches.append({
            "match_id": match_id,
            "home_team": club_names.get(home_id, home_id),
            "away_team": club_names.get(away_id, away_id),
            "home_points": match["quotations"]["home"],
            "draw_points": match["quotations"]["draw"],
            "away_points": match["quotations"]["away"],
            "crowd_home": match["stats"]["bets"]["home"],
            "crowd_draw": match["stats"]["bets"]["draw"],
            "crowd_away": match["stats"]["bets"]["away"],
            "date": match.get("date"),
        })

    return matches


def get_user():
    """Get current user info."""
    headers = get_headers()
    resp = requests.get(f"{API_BASE}/user", headers=headers)
    resp.raise_for_status()
    return resp.json()


def submit_prediction(match_id, home_score, away_score):
    """Submit a score prediction via PATCH."""
    headers = get_headers()
    body = {"homeScore": home_score, "awayScore": away_score, "originPage": "home"}
    resp = requests.patch(
        f"{API_BASE}/user-match-forecasts/entity/general/match/{match_id}",
        headers=headers,
        json=body,
    )
    resp.raise_for_status()
    return {"status": "ok"}


if __name__ == "__main__":
    print("Fetching matches...")
    matches = get_matches()
    print(f"Found {len(matches)} scheduled matches:")
    for m in matches:
        pts = f"{m['home_points']}/{m['draw_points']}/{m['away_points']}"
        crowd = f"{m['crowd_home']:.0%}/{m['crowd_draw']:.0%}/{m['crowd_away']:.0%}"
        print(f"  {m['home_team']} vs {m['away_team']} — pts={pts} crowd={crowd}")

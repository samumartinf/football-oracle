"""MPP API client — fetch matches, submit predictions."""
import json
from pathlib import Path
import requests
from mpp.auth import get_headers

API_BASE = "https://api.mpp.football"
CLUB_CACHE = Path(__file__).parent.parent / "data" / "club_names.json"


def _load_club_names(championship_id=None):
    """Load club ID → team name mapping, fetching from API if needed.

    Args:
        championship_id: If provided (e.g. 8 for World Cup), also fetches
            national team names from championship-available-predictions.
    """
    if CLUB_CACHE.exists():
        with open(CLUB_CACHE) as f:
            mapping = json.load(f)
    else:
        headers = get_headers()
        resp = requests.get(f"{API_BASE}/championship-clubs", headers=headers)
        resp.raise_for_status()
        clubs = resp.json().get("championshipClubs", {})

        mapping = {}
        for cid, club in clubs.items():
            name = club.get("name", {})
            mapping[cid] = name.get("en-GB", name.get("fr-FR", cid))

        with open(CLUB_CACHE, "w") as f:
            json.dump(mapping, f, indent=2)

    # Supplement with national team names from available-predictions
    if championship_id is not None:
        headers = get_headers()
        resp = requests.get(
            f"{API_BASE}/championship-available-predictions/{championship_id}",
            headers=headers,
        )
        resp.raise_for_status()
        pred_data = resp.json()
        players = pred_data.get("players", {})

        for pid, player in players.items():
            ch_data = player.get("championships", {}).get(str(championship_id), {})
            club_id = ch_data.get("championshipClubId")
            selection = (
                ch_data.get("international", {})
                .get("preSeasonData", {})
                .get("selection")
            )
            if club_id and selection and club_id not in mapping:
                mapping[club_id] = selection

    return mapping


def get_matches(championship_id=8, game_week=None):
    """Fetch scheduled championship matches with point values and crowd stats.

    For World Cup (championship 8): uses championship-calendar to find
    match IDs, then fetches each via championship-match. Falls back to
    championships-current-matches for other championships.

    Args:
        championship_id: Championship ID (default 8 = World Cup)
        game_week: Optional game week number to filter (default: all scheduled)
    """
    headers = get_headers()
    club_names = _load_club_names(championship_id)

    matches = []

    if championship_id == 8:
        # World Cup: use calendar + per-match endpoints
        cal_resp = requests.get(
            f"{API_BASE}/championship-calendar/{championship_id}",
            headers=headers,
        )
        cal_resp.raise_for_status()
        calendar = cal_resp.json()

        game_weeks = calendar.get("gameWeeks", {})
        weeks_to_fetch = (
            [str(game_week)] if game_week
            else sorted(game_weeks.keys(), key=int)
        )

        for gw in weeks_to_fetch:
            gw_data = game_weeks.get(gw)
            if not gw_data:
                continue
            for match_id in gw_data.get("matchesIds", []):
                match_resp = requests.get(
                    f"{API_BASE}/championship-match/{match_id}",
                    headers=headers,
                )
                if match_resp.status_code != 200:
                    continue
                m = match_resp.json()

                # Skip matches without quotations (future game weeks)
                if "quotations" not in m:
                    continue

                # Only include scheduled (not yet played) matches
                period = m.get("period")
                if period and period != "scheduled":
                    continue

                home_id = m["home"]["clubId"]
                away_id = m["away"]["clubId"]

                matches.append({
                    "match_id": match_id,
                    "home_team": club_names.get(home_id, home_id),
                    "away_team": club_names.get(away_id, away_id),
                    "home_points": m["quotations"]["home"],
                    "draw_points": m["quotations"]["draw"],
                    "away_points": m["quotations"]["away"],
                    "crowd_home": m["stats"]["bets"]["home"],
                    "crowd_draw": m["stats"]["bets"]["draw"],
                    "crowd_away": m["stats"]["bets"]["away"],
                    "date": m.get("date"),
                })
    else:
        # Original flow for non-WC championships
        resp = requests.get(
            f"{API_BASE}/championships-current-matches",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        for match_id, match in data.items():
            if match.get("championshipId") != championship_id:
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
    matches = get_matches(championship_id=8, game_week=2)
    print(f"Found {len(matches)} scheduled matches:")
    for m in matches:
        pts = f"{m['home_points']}/{m['draw_points']}/{m['away_points']}"
        crowd = f"{m['crowd_home']:.0%}/{m['crowd_draw']:.0%}/{m['crowd_away']:.0%}"
        print(f"  {m['home_team']} vs {m['away_team']} — pts={pts} crowd={crowd}")

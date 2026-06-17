"""Fetch completed World Cup match results from the MPP API."""

import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from mpp.auth import get_headers
from mpp.client import _load_club_names

API_BASE = "https://api.mpp.football"


def get_completed_matches(championship_id=8, game_weeks=None):
    """Fetch all completed WC matches with final scores.

    Walks the championship calendar, filters to matches where
    period=="fullTime", and extracts scores from the event timeline.

    Args:
        championship_id: Championship ID (default 8 = World Cup)
        game_weeks: List of game week numbers, or None for all

    Returns:
        List of {home, away, hg, ag, date, match_id} dicts
    """
    headers = get_headers()
    club_names = _load_club_names(championship_id)

    # Get calendar
    cal_resp = requests.get(
        f"{API_BASE}/championship-calendar/{championship_id}",
        headers=headers,
    )
    cal_resp.raise_for_status()
    calendar = cal_resp.json()
    game_weeks_data = calendar.get("gameWeeks", {})

    weeks_to_fetch = (
        [str(gw) for gw in game_weeks]
        if game_weeks
        else sorted(game_weeks_data.keys(), key=int)
    )

    results = []
    for gw in weeks_to_fetch:
        gw_data = game_weeks_data.get(gw)
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

            if m.get("period") != "fullTime":
                continue

            # Extract score from event timeline
            hg, ag = _extract_score(m.get("eventsTimeline", []))

            home_id = m["home"]["clubId"]
            away_id = m["away"]["clubId"]

            results.append({
                "home": club_names.get(home_id, home_id),
                "away": club_names.get(away_id, away_id),
                "hg": hg,
                "ag": ag,
                "date": m.get("date", ""),
                "match_id": match_id,
                "game_week": int(gw),
            })

    return results


def _extract_score(events):
    """Extract final score from event timeline.

    Uses the cumulative score field from the last goal event,
    falling back to counting goal events by side.
    """
    hg = ag = 0

    for event in events:
        if event.get("eventType") != "goal":
            continue

        score_str = event.get("score", "")
        try:
            parts = score_str.replace(" ", "").split("-")
            if len(parts) == 2:
                hg = int(parts[0])
                ag = int(parts[1])
        except (ValueError, IndexError):
            pass

    # Fallback: count goals by side
    if hg == 0 and ag == 0 and events:
        for event in events:
            if event.get("eventType") == "goal":
                side = event.get("side", "")
                if side == "home":
                    hg += 1
                elif side == "away":
                    ag += 1

    return hg, ag


if __name__ == "__main__":
    print("Fetching completed WC matches...")
    results = get_completed_matches()
    print(f"Found {len(results)} completed matches:\n")
    for r in results:
        gw = r["game_week"]
        print(f"  GW{gw}: {r['home']} {r['hg']}-{r['ag']} {r['away']}  ({r['date'][:10]})")

"""News-based prediction adjuster.

Scrapes recent headlines for teams in upcoming matches and applies
adjustments to ensemble probabilities based on disruptive events
(injuries, suspensions, etc.).

Architecture: post-model adjustment, not an in-model signal.
The ensemble runs first, then this module flags overrides.
"""
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta

# Keywords that indicate a significant disruption
# Keywords that indicate a significant disruption (injury/suspension, not snubs/tributes)
DISRUPTION_KEYWORDS = [
    "ruled out", "out of world cup", "injury blow", "major doubt",
    "suspended", "red card", "ban", "suspension",
    "injured", "out for", "will miss", "set to miss",
    "doubtful", "a doubt for", "fitness test",
    "broken", "fracture", "torn", "acl",
    "hamstring", "ankle injury", "knee injury",
]

# Keywords that look like disruptions but are NOT (false positive filter)
FALSE_POSITIVE_PHRASES = [
    "snub", "snubbed", "honour", "tribute", "wristband",
    "remember", "memorial", "retrospective", "throwback",
    "rumour", "rumor", "gossip", "speculation",
]

# Star players whose absence significantly impacts team strength
# Format: (team_name, player_name)
STAR_PLAYERS = {
    "France": ["Mbappe", "Griezmann", "Tchouameni"],
    "Argentina": ["Messi", "Alvarez", "Martinez"],
    "Norway": ["Haaland", "Odegaard"],
    "England": ["Bellingham", "Kane", "Foden", "Saka"],
    "Croatia": ["Modric", "Gvardiol"],
    "Portugal": ["Ronaldo", "Fernandes", "Leao", "Silva"],
    "Colombia": ["Diaz"],
    "Senegal": ["Mane"],
    "Canada": ["Davies"],
    "Qatar": ["Afif"],
}


def fetch_news(team_name, max_articles=10):
    """Fetch recent news headlines for a team from Google News RSS."""
    query = urllib.parse.quote(f"{team_name} football national team")
    url = f"https://news.google.com/rss/search?q={query}&hl=en&ceid=US:en"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []

    headlines = []
    for item in root.findall(".//item")[:max_articles]:
        title = item.findtext("title", "")
        pub_date = item.findtext("pubDate", "")
        headlines.append({"title": title, "date": pub_date})

    return headlines


def analyze_headlines(team, headlines):
    """Analyze headlines for disruption signals using keyword heuristics.

    Returns (has_disruption, details) where details is a list of findings.
    """
    findings = []
    stars = STAR_PLAYERS.get(team, [])

    for article in headlines:
        title_lower = article["title"].lower()

        # Check if the article mentions this team
        if team.lower() not in title_lower:
            continue

        for keyword in DISRUPTION_KEYWORDS:
            if keyword in title_lower:
                # Filter false positives
                if any(fp in title_lower for fp in FALSE_POSITIVE_PHRASES):
                    continue
                # Check if it involves a star player
                for star in stars:
                    if star.lower() in title_lower:
                        findings.append({
                            "team": team,
                            "player": star,
                            "keyword": keyword,
                            "headline": article["title"],
                            "severity": "high" if keyword in ("ruled out", "out of", "will miss", "acl") else "medium",
                        })
                        break
                else:
                    # Generic disruption mention
                    findings.append({
                        "team": team,
                        "player": "unknown",
                        "keyword": keyword,
                        "headline": article["title"],
                        "severity": "low",
                    })

    return len(findings) > 0, findings


def get_adjustments(matches):
    """Check news for all teams in upcoming matches and return adjustments.

    Args:
        matches: list of {"home": str, "away": str} dicts

    Returns:
        dict of {team_name: {"downgrade": float, "reason": str, "findings": list}}
        where downgrade is a multiplier (0.85 = 15% reduction in win probability)
    """
    all_teams = set()
    for m in matches:
        all_teams.add(m["home"])
        all_teams.add(m["away"])

    adjustments = {}

    for team in sorted(all_teams):
        print(f"  Checking news for {team}...")
        headlines = fetch_news(team)
        has_disruption, findings = analyze_headlines(team, headlines)

        if findings:
            # Calculate severity-based downgrade
            max_severity = max(
                0.15 if f["severity"] == "high" else 0.08 if f["severity"] == "medium" else 0.03
                for f in findings
            )
            reasons = [f"{f['player']}: {f['headline'][:80]}" for f in findings]

            adjustments[team] = {
                "downgrade": round(max_severity, 2),
                "reason": "; ".join(reasons),
                "findings": findings,
            }
            print(f"    ⚠️  {team}: {max_severity:.0%} downgrade — {reasons[0]}")
        else:
            print(f"    ✓  {team}: no disruptions")

    return adjustments


def apply_adjustments(probs, home_team, away_team, adjustments):
    """Apply news-based adjustments to ensemble probabilities.

    A downgrade of 0.15 means the team's win probability is reduced by 15%
    (multiplied by 0.85), with the lost probability redistributed to the
    other outcomes proportionally.
    """
    home_adj = adjustments.get(home_team, {}).get("downgrade", 0)
    away_adj = adjustments.get(away_team, {}).get("downgrade", 0)

    if home_adj == 0 and away_adj == 0:
        return probs, None

    # Apply downgrades
    adj_home = probs["home"] * (1 - home_adj)
    adj_away = probs["away"] * (1 - away_adj)

    # Redistribute lost probability to draw and the other side
    lost_home = probs["home"] - adj_home
    lost_away = probs["away"] - adj_away

    # Draw gets half the lost probability from both sides
    adj_draw = probs["draw"] + lost_home * 0.5 + lost_away * 0.5
    adj_home += lost_away * 0.25  # home also benefits from away downgrade
    adj_away += lost_home * 0.25  # away also benefits from home downgrade

    # Normalize
    total = adj_home + adj_draw + adj_away
    adj_home /= total
    adj_draw /= total
    adj_away /= total

    adjusted = {
        "home": round(adj_home, 4),
        "draw": round(adj_draw, 4),
        "away": round(adj_away, 4),
    }

    # Preserve lambdas from original
    for k in ["home_lambda", "away_lambda"]:
        if k in probs:
            adjusted[k] = probs[k]

    notes = []
    if home_adj > 0:
        notes.append(f"{home_team} -{home_adj:.0%}: {adjustments[home_team]['reason']}")
    if away_adj > 0:
        notes.append(f"{away_team} -{away_adj:.0%}: {adjustments[away_team]['reason']}")

    return adjusted, "; ".join(notes) if notes else None

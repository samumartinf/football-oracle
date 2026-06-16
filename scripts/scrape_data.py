"""Scrape Elo ratings, FIFA rankings, and match data for World Cup teams."""
import json
import re
import urllib.request
from pathlib import Path
from datetime import datetime

OUTPUT = Path(__file__).parent.parent / "data"
OUTPUT.mkdir(parents=True, exist_ok=True)

def fetch_url(url, headers=None):
    """Fetch a URL and return text."""
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return None

# 1. FIFA Rankings (current)
print("=== FIFA RANKINGS ===")
fifa_html = fetch_url("https://www.fifa.com/en/fifa-world-ranking/men")
if fifa_html:
    # Try to extract ranking data from embedded JSON
    json_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', fifa_html)
    if json_match:
        data = json.loads(json_match.group(1))
        rankings = data.get("props", {}).get("pageProps", {}).get("rankings", [])
        for team in rankings[:50]:
            print(f"  #{team.get('rank')}: {team.get('teamName')} — {team.get('totalPoints')} pts")
    else:
        # Try alternate approach
        print(f"  Page length: {len(fifa_html)} chars")
        # Search for country names in the HTML
        countries = re.findall(r'[">]([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s*</', fifa_html)
        print(f"  Found {len(countries)} country-like strings")

# 2. World Football Elo Ratings
print("\n=== ELO RATINGS ===")
elo_html = fetch_url("http://eloratings.net/")
if not elo_html:
    # Try HTTPS
    elo_html = fetch_url("https://eloratings.net/")
if elo_html:
    print(f"  Fetched {len(elo_html)} chars")
    # Extract ranking lines - typical format: rank country rating
    lines = elo_html.split('\n')
    for line in lines[:80]:
        if re.search(r'\b(19|20|21)\d{2}\b', line):  # Elo ratings are 1800-2200+
            clean = re.sub(r'<[^>]+>', '', line).strip()
            if clean:
                print(f"  {clean[:120]}")

# 3. Football-data.co.uk (historical international results)
print("\n=== FOOTBALL-DATA.CO.UK ===")
# They have international data
intl_csv = fetch_url("https://www.football-data.co.uk/new/INT.csv")
if intl_csv:
    lines = intl_csv.strip().split('\n')
    print(f"  Got {len(lines)} lines of international match data")
    print(f"  Headers: {lines[0]}")
    print(f"  Last 5 matches:")
    for line in lines[-5:]:
        print(f"    {line}")

# 4. Try to get betting odds for specific matches
print("\n=== ODDS CHECKER ===")
# Try Odds API or similar
odds_html = fetch_url("https://www.oddschecker.com/football/world-cup")
if odds_html:
    print(f"  Fetched {len(odds_html)} chars")

print("\n=== TEAMS TO ANALYZE ===")
teams = [
    "France", "Senegal", "Iraq", "Norway",
    "Argentina", "Algeria", "Austria", "Jordan",
    "Portugal", "DR Congo", "England", "Croatia",
    "Ghana", "Panama", "Uzbekistan", "Colombia",
    "Czech Republic", "South Africa", "Switzerland", "Bosnia",
    "Canada", "Qatar"
]
print(f"  {len(teams)} teams in upcoming MPP matches")

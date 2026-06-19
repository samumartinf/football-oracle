#!/usr/bin/env python3
"""Scrape WC2026 xG data from fbref.com using Playwright.

fbref.com has Cloudflare anti-bot protection that blocks headless browsers
and curl. Playwright with a real browser installation handles this.

Usage:
    cd ~/src/football-oracle
    .venv/bin/python data_pipeline/scrape_xg_wc2026.py

Output: data/historical/xg/matches.csv

Requires: playwright (pip install playwright && playwright install chromium)
"""

import csv
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


FBREF_URL = "https://fbref.com/en/comps/1/2026/schedule/2026-World-Cup-Scores-and-Fixtures"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "historical" / "xg"
OUTPUT_PATH = OUTPUT_DIR / "matches.csv"

# Map fbref team names to our dataset names
TEAM_NAME_MAP = {
    "Argentina": "Argentina",
    "Algeria": "Algeria",
    "Austria": "Austria",
    "Jordan": "Jordan",
    "Portugal": "Portugal",
    "DR Congo": "DR Congo",
    "England": "England",
    "Croatia": "Croatia",
    "Ghana": "Ghana",
    "Panama": "Panama",
    "Uzbekistan": "Uzbekistan",
    "Colombia": "Colombia",
    "Czech Republic": "Czechia",
    "South Africa": "South Africa",
    "Switzerland": "Switzerland",
    "Bosnia": "Bosnia",
    "Canada": "Canada",
    "Qatar": "Qatar",
    "Spain": "Spain",
    "France": "France",
    "Germany": "Germany",
    "Brazil": "Brazil",
    "Netherlands": "Netherlands",
    "Norway": "Norway",
    "Japan": "Japan",
    "Ecuador": "Ecuador",
    "Mexico": "Mexico",
    "Belgium": "Belgium",
    "Uruguay": "Uruguay",
    "Turkey": "Türkiye",
    "Morocco": "Morocco",
    "Australia": "Australia",
    "Senegal": "Senegal",
    "South Korea": "South Korea",
    "Paraguay": "Paraguay",
    "United States": "United States",
    "Iran": "Iran",
    "Sweden": "Sweden",
    "Ivory Coast": "Ivory Coast",
    "Egypt": "Egypt",
    "Saudi Arabia": "Saudi Arabia",
    "Iraq": "Iraq",
    "Tunisia": "Tunisia",
    "New Zealand": "New Zealand",
    "Haiti": "Haiti",
    "Cape Verde": "Cape Verde",
    "Curaçao": "Curaçao",
}


def normalize_team(name):
    """Map fbref team name to our dataset name."""
    name = name.strip()
    return TEAM_NAME_MAP.get(name, name)


def parse_xg_table(page):
    """Extract xG data from the fbref schedule table.

    fbref's match table has columns: Date, Home, Score, Away, Attendance,
    Venue, Referee, Match Report, Notes, and then xG columns:
    xG (home), xG (away) — these are in the last two columns.
    """
    # Wait for the table to load
    try:
        page.wait_for_selector("table.stats_table", timeout=15000)
    except PlaywrightTimeout:
        print("Could not find stats table on page.")
        print("Page title:", page.title())
        return []

    # Try to find xG columns — they have data-stat="xg_a" or similar
    rows = page.query_selector_all("table.stats_table tbody tr")
    if not rows:
        # Try the newer fbref layout
        rows = page.query_selector_all("table#sched_2026_1 tbody tr")

    matches = []
    for row in rows:
        # Skip spacer rows
        if row.get_attribute("class") and "spacer" in row.get_attribute("class"):
            continue

        cells = row.query_selector_all("td")
        if len(cells) < 10:
            continue

        # fbref columns vary — find xG by data-stat attribute
        home_xg = away_xg = home_goals = away_goals = home_team = away_team = date = None

        for cell in cells:
            stat = cell.get_attribute("data-stat")
            text = cell.inner_text().strip()

            if stat == "date":
                date = text
            elif stat == "home_team":
                home_team = normalize_team(text)
            elif stat == "away_team":
                away_team = normalize_team(text)
            elif stat == "home_xg":
                try:
                    home_xg = float(text)
                except ValueError:
                    home_xg = None
            elif stat == "away_xg":
                try:
                    away_xg = float(text)
                except ValueError:
                    away_xg = None
            elif stat == "goals_home":
                try:
                    home_goals = int(text)
                except ValueError:
                    home_goals = 0
            elif stat == "goals_away":
                try:
                    away_goals = int(text)
                except ValueError:
                    away_goals = 0

        if home_xg is not None and away_xg is not None and home_team and away_team:
            matches.append({
                "date": date or "",
                "home_team": home_team,
                "away_team": away_team,
                "home_xg": home_xg,
                "away_xg": away_xg,
                "home_goals": home_goals or 0,
                "away_goals": away_goals or 0,
                "competition": "WC2026",
            })

    return matches


def main():
    print("Launching browser to scrape fbref.com WC2026 xG data...")
    print("(this opens a real Chrome window — don't close it)")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Headful to bypass Cloudflare
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            print(f"Navigating to {FBREF_URL}...")
            page.goto(FBREF_URL, timeout=30000, wait_until="domcontentloaded")

            # Cloudflare challenge — wait for the real page to load
            print("Waiting for Cloudflare challenge to resolve...")
            time.sleep(3)

            # Check if we're still on the challenge page
            if "Just a moment" in page.title():
                print("Cloudflare challenge detected. Waiting up to 15 seconds...")
                try:
                    page.wait_for_selector("table.stats_table", timeout=15000)
                except PlaywrightTimeout:
                    print("Challenge did not resolve in time.")
                    print("Try running the script again, or open fbref.com in your")
                    print("browser first to pass the challenge manually.")
                    browser.close()
                    sys.exit(1)

            print("Page loaded. Extracting xG data...")
            matches = parse_xg_table(page)

            if not matches:
                print("No matches with xG data found. The table structure may have changed.")
                print("Taking a screenshot for debugging...")
                page.screenshot(path=str(OUTPUT_DIR / "fbref_debug.png"))
                browser.close()
                sys.exit(1)

            print(f"Found {len(matches)} matches with xG data.")

            # Save
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            fieldnames = ["date", "home_team", "away_team", "home_xg", "away_xg",
                          "home_goals", "away_goals", "competition"]
            with open(OUTPUT_PATH, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for m in matches:
                    writer.writerow(m)

            print(f"Saved to {OUTPUT_PATH}")
            print()
            print("Sample:")
            for m in matches[:5]:
                print(f"  {m['date']} {m['home_team']} {m['home_goals']}-{m['away_goals']} "
                      f"{m['away_team']}  xG: {m['home_xg']}-{m['away_xg']}")

        except Exception as e:
            print(f"Error: {e}")
            raise
        finally:
            browser.close()

    print("\nDone. To use xG in predictions, set xg weight in ensemble.py.")
    print("Currently: xg weight = 0.0 (no data). After scrape: change to 0.05-0.10.")


if __name__ == "__main__":
    main()

"""Scrape betting odds for upcoming World Cup matches."""
import csv
import json
import time
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "historical"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}

UPCOMING_MATCHES = [
    ("2026-06-17", "Argentina", "Algeria"),
    ("2026-06-17", "Austria", "Jordan"),
    ("2026-06-17", "Portugal", "DR Congo"),
    ("2026-06-17", "England", "Croatia"),
    ("2026-06-18", "Ghana", "Panama"),
    ("2026-06-18", "Uzbekistan", "Colombia"),
    ("2026-06-18", "Czech Republic", "South Africa"),
    ("2026-06-18", "Switzerland", "Bosnia"),
    ("2026-06-18", "Canada", "Qatar"),
]


def scrape_odds_for_match(home, away):
    """Scrape 1X2 odds from OddsPortal for a specific match."""
    slug = f"{home.lower().replace(' ', '-')}-{away.lower().replace(' ', '-')}"
    url = f"https://www.oddsportal.com/football/world/world-championship-2026/{slug}/"

    print(f"  {home} vs {away}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"    Error: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    avg_home = avg_draw = avg_away = None

    table = soup.find("table", class_=lambda c: c and "odds" in str(c).lower())
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3:
                try:
                    avg_home = float(cells[0].text.strip())
                    avg_draw = float(cells[1].text.strip())
                    avg_away = float(cells[2].text.strip())
                    break
                except ValueError:
                    continue

    if avg_home:
        total = 1/avg_home + 1/avg_draw + 1/avg_away
        prob_home = (1/avg_home) / total
        prob_draw = (1/avg_draw) / total
        prob_away = (1/avg_away) / total

        return {
            "home": home,
            "away": away,
            "odds_home": avg_home,
            "odds_draw": avg_draw,
            "odds_away": avg_away,
            "prob_home": round(prob_home, 4),
            "prob_draw": round(prob_draw, 4),
            "prob_away": round(prob_away, 4),
            "scraped_at": datetime.now().isoformat(),
        }

    return None


def extract_odds_from_xlsx():
    """Extract betting odds from the cached World Cup XLSX as fallback."""
    import pandas as pd
    xlsx_path = DATA_DIR / "worldcup_data.xlsx"
    if not xlsx_path.exists():
        return []

    xls = pd.ExcelFile(xlsx_path)
    odds_data = []

    df = pd.read_excel(xls, sheet_name="WorldCup2026Qualifiers")
    XLSX_TEAM_MAP = {
        "D.R. Congo": "DR Congo",
        "Bosnia & Herzegovina": "Bosnia",
    }

    for _, r in df.iterrows():
        home = XLSX_TEAM_MAP.get(str(r["Home"]).strip(), str(r["Home"]).strip())
        away = XLSX_TEAM_MAP.get(str(r["Away"]).strip(), str(r["Away"]).strip())
        h_avg = r.get("H_Avg")
        d_avg = r.get("D_Avg")
        a_avg = r.get("A_Avg")
        date = r.get("Date")

        try:
            h_avg = float(h_avg)
            d_avg = float(d_avg)
            a_avg = float(a_avg)
            if h_avg <= 0 or d_avg <= 0 or a_avg <= 0:
                continue
        except (ValueError, TypeError):
            continue

        total = 1/h_avg + 1/d_avg + 1/a_avg

        odds_data.append({
            "date": str(date),
            "home": home,
            "away": away,
            "odds_home": h_avg,
            "odds_draw": d_avg,
            "odds_away": a_avg,
            "prob_home": round((1/h_avg) / total, 4),
            "prob_draw": round((1/d_avg) / total, 4),
            "prob_away": round((1/a_avg) / total, 4),
        })

    return odds_data


def scrape_all_odds():
    """Scrape odds for all upcoming matches, with XLSX fallback."""
    results = []

    for date_str, home, away in UPCOMING_MATCHES:
        odds = scrape_odds_for_match(home, away)
        if odds:
            odds["date"] = date_str
            results.append(odds)
        time.sleep(5)

    output = DATA_DIR / "odds" / "upcoming_odds.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    if results:
        with open(output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"\nSaved {len(results)} odds entries to {output}")
    else:
        print("\nOddsPortal requires JS — trying XLSX fallback...")
        xlsx_odds = extract_odds_from_xlsx()
        if xlsx_odds:
            with open(output, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=xlsx_odds[0].keys())
                writer.writeheader()
                writer.writerows(xlsx_odds)
            print(f"Saved {len(xlsx_odds)} historical odds entries from XLSX to {output}")
        else:
            output.write_text(
                "# Odds require JS rendering (Playwright) or XLSX data.\n"
                "# Enter odds manually or use a different source.\n"
                "# Format: home,away,odds_home,odds_draw,odds_away\n"
            )
            print("No odds available from either source.")

    return results


if __name__ == "__main__":
    scrape_all_odds()

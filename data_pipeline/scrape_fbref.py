"""Extract match results for WC teams from cached World Cup XLSX data."""
import csv
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "historical"

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


def fetch_recent_matches_from_xlsx():
    """Extract recent match results for all WC teams from the cached XLSX."""
    xlsx_path = DATA_DIR / "worldcup_data.xlsx"
    if not xlsx_path.exists():
        print("ERROR: No cached XLSX found. Run scrape_elo.py first.")
        return []

    xls = pd.ExcelFile(xlsx_path)
    all_rows = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        if sheet == "WorldCup2026Qualifiers":
            for _, r in df.iterrows():
                home = XLSX_TEAM_MAP.get(str(r["Home"]).strip(), str(r["Home"]).strip())
                away = XLSX_TEAM_MAP.get(str(r["Away"]).strip(), str(r["Away"]).strip())
                hg = r["HG"]
                ag = r["AG"]
                date = r["Date"]
                if pd.isna(hg) or pd.isna(ag):
                    continue
                # Home team result
                if home in WC_TEAMS:
                    result = "W" if hg > ag else ("D" if hg == ag else "L")
                    all_rows.append({
                        "date": str(date),
                        "team": home,
                        "opponent": away,
                        "competition": "WC Qualifiers",
                        "venue": "home",
                        "result": result,
                        "gf": int(hg),
                        "ga": int(ag),
                    })
                # Away team result
                if away in WC_TEAMS:
                    result = "W" if ag > hg else ("D" if hg == ag else "L")
                    all_rows.append({
                        "date": str(date),
                        "team": away,
                        "opponent": home,
                        "competition": "WC Qualifiers",
                        "venue": "away",
                        "result": result,
                        "gf": int(ag),
                        "ga": int(hg),
                    })
        elif sheet in ("WorldCup2022", "WorldCup2018", "WorldCup2014"):
            for _, r in df.iterrows():
                home = str(r["Home"]).strip()
                away = str(r["Away"]).strip()
                hg = r["HGFT"]
                ag = r["AGFT"]
                date = r["Date"]
                if pd.isna(hg) or pd.isna(ag):
                    continue
                if home in WC_TEAMS:
                    result = "W" if hg > ag else ("D" if hg == ag else "L")
                    all_rows.append({
                        "date": str(date),
                        "team": home,
                        "opponent": away,
                        "competition": sheet,
                        "venue": "neutral",
                        "result": result,
                        "gf": int(hg),
                        "ga": int(ag),
                    })
                if away in WC_TEAMS:
                    result = "W" if ag > hg else ("D" if hg == ag else "L")
                    all_rows.append({
                        "date": str(date),
                        "team": away,
                        "opponent": home,
                        "competition": sheet,
                        "venue": "neutral",
                        "result": result,
                        "gf": int(ag),
                        "ga": int(hg),
                    })

    return all_rows


def scrape_all_teams():
    """Extract recent matches for all WC teams from XLSX data."""
    all_matches = fetch_recent_matches_from_xlsx()

    output = DATA_DIR / "results" / "recent_matches.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["date", "team", "opponent", "competition", "venue", "result", "gf", "ga"]
    with open(output, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_matches)

    print(f"Saved {len(all_matches)} matches to {output}")
    return all_matches


if __name__ == "__main__":
    scrape_all_teams()

#!/usr/bin/env python3
"""Run the full data pipeline: scrape all sources and build dataset."""
import importlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    print("=" * 50)
    print("Football Oracle - Data Pipeline Runner")
    print("=" * 50)

    steps = [
        ("Elo Ratings", ".scrape_elo", "compute_elo_ratings"),
        ("Match Results", ".scrape_fbref", "scrape_all_teams"),
        ("Betting Odds", ".scrape_odds", "scrape_all_odds"),
        ("Build Dataset", ".coordinator", "build_team_dataset"),
    ]

    for name, module, func in steps:
        print(f"\n  {name}...")
        start = time.time()
        try:
            mod = importlib.import_module(module, package="data_pipeline")
            getattr(mod, func)()
            elapsed = time.time() - start
            print(f"   Done in {elapsed:.1f}s")
        except Exception as e:
            print(f"   Failed: {e}")
            print(f"   Continuing with remaining steps...")

    print("\n" + "=" * 50)
    print("Pipeline complete!")
    print("Output: data/historical/team_dataset.json")
    print("=" * 50)


if __name__ == "__main__":
    main()

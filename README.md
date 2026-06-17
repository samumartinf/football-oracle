# football-oracle

Automated MPP (Mon Petit Prono) prediction engine for the World Cup. Combines
three statistical models into an ensemble, then optimizes picks against MPP's
full scoring system — base points, rarity bonuses, exact-score bonuses, and
double-points.

## How it works

```
                    ┌─────────────┐
                    │  MPP API    │  live points + crowd %
                    └──────┬──────┘
                           │
   ┌──────────┐   ┌───────▼──────┐   ┌───────────┐
   │   Elo    │   │   Poisson    │   │  Market   │
   │ (30%)    │   │    (40%)     │   │  (30%)    │
   └────┬─────┘   └──────┬───────┘   └─────┬─────┘
        │                │                 │
        └────────────────▼─────────────────┘
                         │
               ┌─────────▼─────────┐
               │    Ensemble       │
               │  blended probs    │
               └─────────┬─────────┘
                         │
               ┌─────────▼─────────┐
               │  News Adjuster    │  injury/suspension signals
               │  (optional)       │
               └─────────┬─────────┘
                         │
               ┌─────────▼─────────┐
               │  EV Optimizer     │  base + rarity + exact + double
               └─────────┬─────────┘
                         │
               ┌─────────▼─────────┐
               │  Auto-submit      │  PATCH to MPP API
               └───────────────────┘
```

## The models

### Elo
Standard expected-score formula with home advantage. Draw probability derived
from the closeness of the matchup (exponential decay with Elo difference).

### Poisson
Goals modeled as Poisson random variables. Lambda derived from Elo ratings.
Full score probability matrix (0–10 goals each side) with Dixon-Coles
adjustment for low-scoring draws. Pure Python — no scipy needed.

### Market
Betting market implied probabilities from historical odds data. Extracted via
the data pipeline from odds scraping.

### Ensemble
Weighted blend: **60% Elo · 40% Poisson · 0% Market** (by default).

> Weights were optimized via grid search on 339 historical matches (WC 2014/2018/2022
> + 2026 qualifiers). The backtest found Elo is better calibrated, so the default
> weights favor it. Run `python models/backtest.py` to re-run the analysis.

### News Adjuster (optional)
Scrapes Google News RSS for each team in upcoming matches. Looks for
injury/suspension keywords, cross-references against a star-player database,
and applies a probability downgrade:

| Severity | Effect | Example |
|----------|--------|---------|
| High | -15% win prob | "ruled out", "will miss", "ACL" |
| Medium | -8% win prob | "doubtful", "fitness test" |
| Low | -3% win prob | Generic disruption mention |

False positives filtered: snubs, tributes, rumours, throwback articles.

## Strategies

The optimizer models MPP's full scoring system:

| Component | How it works |
|-----------|-------------|
| **Base points** | Quotation × probability of correct outcome |
| **Rarity bonus** | +200 (mega, <2% crowd) · +100 (ultra, <5%) · +50 (rare, <10%) · +25 (very rare, <15%) |
| **Exact score** | +25 bonus for nailing the scoreline |
| **Double points** | 2× all points on one match per matchday |

### Normal mode (default)
Maximizes expected value: `EV = P(outcome) × (base_points + rarity_bonus)`.
Picks the outcome with the highest EV for each match.

### Catch-up mode (`--catch-up <pts>`)
When >200 points behind the leader: among outcomes within **15% of the best EV**,
picks the one with the **highest total possible points** (high-risk, high-reward).
This means favoring contrarian away-win picks and rare outcomes.

### Double-points (`--double`)
Recommends which match to apply your multiplier to. Picks the match where
doubling creates the largest EV boost — usually a toss-up match where the
crowd is split.

## Setup

### 1. Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

Create `.env` in the project root:

```
MPP_EMAIL=your-email@example.com
MPP_PASSWORD=your-password
```

### 3. Build the dataset

You need Elo ratings and market odds for the teams:

```bash
python data_pipeline/run_all.py
```

This scrapes Elo ratings, FBref stats, and betting odds, then builds
`data/historical/team_dataset.json`.

### 4. Run backtest (optional)

Verify model accuracy and find optimal weights:

```bash
python models/backtest.py          # Full report: baselines + grid search
python models/backtest.py --quick  # Grid search only
```

The backtest walks 1,081 matches chronologically (WC 2014/2018/2022 + qualifiers),
building Elo ratings step-by-step to avoid look-ahead bias. It tests every weight
combination from 0% to 100% Elo and reports accuracy, log-loss, and Brier score.

### 5. Run predictions

```bash
# Preview picks (offline, uses hardcoded fallback data)
python predict.py

# Live data + auto-submit
python predict.py --submit

# Everything: live data + news check + double recommendation + submit
python predict.py --submit --news --double

# Catch-up mode (800 points behind)
python predict.py --submit --catch-up 800

# Single match
python predict.py --match England Croatia
```

## Project structure

```
football-oracle/
├── predict.py              # CLI entry point
├── models/
│   ├── elo.py              # Elo → probabilities
│   ├── poisson.py          # Poisson goal model
│   ├── ensemble.py         # Weighted blend
│   ├── optimizer.py        # EV + rarity + catch-up + double
│   ├── backtest.py         # Historical backtest + weight grid search
│   └── news_adjuster.py    # Google News injury scraper
├── mpp/
│   ├── auth.py             # Playwright OAuth → Bearer token
│   └── client.py           # API client (matches, submit)
├── data_pipeline/
│   ├── run_all.py          # Builds team_dataset.json
│   ├── scrape_elo.py       # Elo ratings scraper
│   ├── scrape_fbref.py     # FBref stats scraper
│   └── scrape_odds.py      # Betting odds scraper
├── data/                   # Cache: club_names.json, token.json
├── tests/
│   ├── test_elo.py
│   ├── test_poisson.py
│   ├── test_ensemble.py
│   ├── test_optimizer.py
│   └── test_mpp_client.py
└── scripts/                # One-off exploration scripts
```

## Flags

| Flag | What it does |
|------|-------------|
| `--submit` | Fetch live MPP data + auto-submit picks via API |
| `--news` | Check Google News for injury disruptions |
| `--double` | Recommend which match to apply double-points on |
| `--catch-up N` | Catch-up mode (prefer high-reward contrarian picks) |
| `--match A B` | Predict only `A vs B` instead of all matches |

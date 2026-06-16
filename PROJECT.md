# Football Oracle — Beat MPP with Data

A prediction engine for [Mon Petit Prono](https://mpp.football/) (MPP), the official
French Professional Football League prediction game. Built to win a private World Cup
2026 league against colleagues at a tech hedge fund.

## How MPP Works

### Game Mechanics
- **Exact score predictions**: you predict the final score for each match
- **Risk-reward point system**: each outcome (home/draw/away) has a point value
  inversely proportional to crowd popularity
- **Crowd percentages**: shown on dashboard, derived from all MPP users' predictions
- **Bonuses**: "Activate MPP bonus" gives double points on one match (per user)

### Point System Example (France vs Sénégal, June 16)
| Outcome | Points | Crowd % |
|---------|--------|---------|
| France win | 46 pts | 88% |
| Draw | 128 pts | 9% |
| Sénégal win | 153 pts | 3% |

The crowd flocks to favorites (safe, low reward). You catch up by finding
matches where the crowd is *wrong* — where the true probability of an upset 
is higher than the crowd thinks, making the expected value favor the underdog.

### Scoring Tiers (from `forecast/fr.json` locale)
```
exact: "Exact +{extraPoints}pts"
megaRare: "Mega rare +{extraPoints}pts"
rare: "Rare +{extraPoints}pts"
ultraRare: "Ultra rare +{extraPoints}pts"
veryRare: "Très rare +{extraPoints}pts"
```
Bonus points are awarded for rare correct predictions (e.g., picking an
underdog that few others picked).

## MPP API Reference

### Base URL & Auth
```
Base: https://api.mpp.football
Auth: Bearer token via Ligue1 Connect OAuth (PKCE flow)
      Login URL: https://connect.ligue1.fr/u/login
      Token URL: https://connect.ligue1.fr/oauth/token
```

### Endpoints

#### Get All Current Matches
```
GET /championships-current-matches
```
Returns all matches with point values and crowd stats:
```json
{
  "mpp_championship_match_2608260": {
    "matchId": "mpp_championship_match_2608260",
    "championshipId": 8,
    "gameWeekNumber": 2,
    "date": "2026-06-17T18:00:00.000Z",
    "period": "scheduled",
    "quotations": {"home": 46, "draw": 128, "away": 153},
    "stats": {"bets": {"home": 0.88, "draw": 0.09, "away": 0.03}},
    "home": {
      "clubId": "mpp_championship_club_118",
      "name": {"fr-FR": "France"},
      "shortName": "FRA",
      "score": null
    },
    "away": {
      "clubId": "mpp_championship_club_368",
      "name": {"fr-FR": "Sénégal"},
      "shortName": "SEN",
      "score": null
    }
  }
}
```

#### Get Match Calendar
```
GET /championship-calendar/8
```
Returns full tournament schedule. Championship ID 8 = World Cup 2026.
Structure: `{"gameWeeks": {"1": {"gameWeekNumber": 1, "matchesIds": [...]}}}`

#### Get Active Championships
```
GET /championships-settings/active
```
Returns competition metadata (logo URLs, competition type, codes).

#### Get Available Teams
```
GET /championship-available-predictions/8
```
Returns club IDs and metadata for all teams in the tournament.

#### Get Team Details
```
GET /championship-clubs
```
Full club database with names, short names, jersey URLs.

#### Get User Info
```
GET /user
```
Returns user profile: `{"id": "user_12121320", "email": "...", "firstName": "...", "username": "..."}`

#### Get User Bonuses
```
GET /user-bonuses
```
Returns available double-points bonuses: `{"championships": {"8": {"doublePoints": 1}}}`

#### Submit Prediction
```
PATCH /user-match-forecasts/entity/general/match/{matchId}
Content-Type: application/json
Body: {"homeScore": 2, "awayScore": 0, "originPage": "home"}
```
This is the key endpoint. Scores auto-save; no separate "submit" step.

### Auth Flow (OAuth PKCE)
1. Generate PKCE code verifier + challenge
2. POST credentials to `connect.ligue1.fr/u/login`
3. Follow redirects through Ligue1 Connect
4. Exchange authorization code for token at `/oauth/token`
5. Use Bearer token for all `api.mpp.football` calls

## EV-Based Strategy

### Expected Value Formula
```
EV(outcome) = P(outcome) × points(outcome)
```
Pick the outcome with highest EV. But in a catch-up scenario (800 pts behind),
variance is your friend — consider picks where EV is *close* to the favorite
but the point swing vs the crowd is large.

### Key Insights from June 16-19 Matches

| Match | Best EV Pick | EV | Crowd Pick | Crowd EV | Delta |
|-------|-------------|-----|-----------|---------|-------|
| France-Sénégal | France (46×0.75=34.5) | 34.5 | France | 40.5¹ | - |
| Norway-Iraq | Norway (30×0.85=25.5) | 25.5 | Norway | 27.3¹ | - |
| **England-Croatia** | **Draw (119×0.27=32.1)** | 32.1 | England (59×0.55=32.5) | 32.5 | **Contrarian** |
| **Czech-SA** | **Draw (112×0.28=31.4)** | 31.4 | Czech (58×0.52=30.2) | 30.2 | **Higher EV!** |
| Switzerland-Bosnia | Switzerland (76×0.68=51.7) | 51.7 | Switzerland | 51.7 | Safe |

¹ Crowd EV uses MPP crowd probabilities, which are slightly inflated for favorites.

## Project Architecture

```
football-oracle/
├── .env.example              # MPP_EMAIL, MPP_PASSWORD (no real values)
├── PROJECT.md                # This document
├── data/
│   ├── api_calls.json        # Captured API traffic (reference)
│   ├── forecast_api.json     # Prediction submission capture
│   ├── token.json            # OAuth token storage (gitignored)
│   └── historical/           # Cached match results for backtesting
├── scripts/
│   ├── verify_login.py       # Test MPP credentials
│   ├── explore_mpp.py        # DOM exploration
│   ├── sniff_api.py          # API traffic capture
│   ├── sniff_forecast.py     # Forecast endpoint capture
│   ├── sniff_forecast2.py    # Shorter timeout version
│   └── submit_picks.py       # Playwright-based submission
├── models/
│   ├── poisson.py            # Dixon-Coles Poisson model
│   ├── elo.py                # Elo rating system
│   ├── ensemble.py           # Model blending + EV optimization
│   └── market.py             # Betting odds integration
├── mpp/
│   ├── client.py             # MPP API client (auth + endpoints)
│   ├── predictor.py          # Auto-submit predictions via API
│   └── cli.py                # CLI: "predict --matchday 2"
├── data_pipeline/
│   ├── scrape_fbref.py       # FBref xG data scraper
│   ├── scrape_eloratings.py  # Elo ratings scraper
│   └── scrape_odds.py        # Betting odds scraper
└── dashboard/
    └── streamlit_app.py       # EV visualization + backtesting
```

## Phases (for OpenCode)

### Phase 1: API Client ✅ (discovered)
- Auth flow (OAuth PKCE with Ligue1 Connect)
- GET matches with point values
- PATCH predictions
- GET user/bonuses

### Phase 2: Data Pipeline
- Scrape international match results (football-data.co.uk, FBref)
- Build Elo rating database for all World Cup teams
- Fetch xG data where available
- Cache betting odds from OddsPortal/other sources

### Phase 3: Prediction Models
- Dixon-Coles Poisson model (attack/defense parameters)
- Elo-based win probability model
- Ensemble: weighted blend of Poisson + Elo + market odds
- EV optimizer: convert probabilities to optimal score predictions

### Phase 4: Automation
- Cron job: run before each matchday deadline
- Auto-submit via PATCH endpoint
- Discord notification with picks + EV reasoning
- Optional: manual approval gate

### Phase 5: Backtesting & Monitoring
- Backtest against previous World Cups (2018, 2022)
- Track prediction accuracy vs actual results
- Leaderboard scraper to monitor league position

## Technical Notes

- MPP is a React Native (Expo) web app, API is REST/JSON
- Championship ID 8 = World Cup 2026
- Match IDs follow pattern: `mpp_championship_match_{id}`
- User ID format: `user_{id}`
- Ligue1 Connect is the auth provider (not a custom MPP auth)
- Locale files at `mpg-front-assets.s3.eu-west-3.amazonaws.com/locales_mpp_prod/{section}/fr.json`
- Team images at `s3.eu-west-1.amazonaws.com/image.mpg/{clubId}.png`
- The `quotations` field = point values; `stats.bets` = crowd percentages (0-1)
- Scores auto-save on input; no explicit "submit" button
- Double points bonus ("Activer mon bonus MPP") available per championship

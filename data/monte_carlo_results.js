window.MONTE_CARLO_RESULTS = {
  "source": "python",
  "sims": 5000,
  "seed": 3,
  "matches": 9,
  "rows": [
    {
      "match": "Argentina v Algeria",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 53.07,
      "swing": true
    },
    {
      "match": "Austria v Jordan",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 46.05,
      "swing": true
    },
    {
      "match": "Portugal v DR Congo",
      "oracle": "draw 1-1",
      "crowd": "home 1-0",
      "ev": 47.26,
      "swing": true
    },
    {
      "match": "England v Croatia",
      "oracle": "away 0-1",
      "crowd": "home 1-0",
      "ev": 46.56,
      "swing": true
    },
    {
      "match": "Ghana v Panama",
      "oracle": "away 0-1",
      "crowd": "home 1-0",
      "ev": 100.0,
      "swing": true
    },
    {
      "match": "Uzbekistan v Colombia",
      "oracle": "home 1-0",
      "crowd": "away 0-1",
      "ev": 35.54,
      "swing": true
    },
    {
      "match": "Czech Republic v South Africa",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 62.09,
      "swing": true
    },
    {
      "match": "Switzerland v Bosnia",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 77.04,
      "swing": true
    },
    {
      "match": "Canada v Qatar",
      "oracle": "away 0-1",
      "crowd": "home 1-0",
      "ev": 90.01,
      "swing": true
    }
  ],
  "oracle": {
    "mean": 574.877,
    "p10": 198,
    "p50": 572,
    "p75": 771,
    "p90": 949,
    "p95": 1053
  },
  "crowd": {
    "mean": 231.792,
    "p10": 116,
    "p50": 230,
    "p75": 291,
    "p90": 349,
    "p95": 381
  },
  "delta": {
    "mean": 343.085,
    "p10": -83,
    "p50": 330,
    "p75": 572,
    "p90": 802,
    "p95": 908
  },
  "beatRate": 0.8512,
  "bigSwingRate": 0.694,
  "downsideRate": 0.0926,
  "histogram": [
    {
      "label": "< -200",
      "count": 224
    },
    {
      "label": "-200..-101",
      "count": 238
    },
    {
      "label": "-100..-1",
      "count": 280
    },
    {
      "label": "0..149",
      "count": 788
    },
    {
      "label": "150..299",
      "count": 766
    },
    {
      "label": "300..499",
      "count": 1131
    },
    {
      "label": "500+",
      "count": 1573
    }
  ],
  "actuals": {
    "matched": 2,
    "oraclePoints": 0,
    "crowdPoints": 81,
    "delta": -81,
    "deltaPercentile": 0.2906,
    "deltaSummary": {
      "mean": 51.4532,
      "p10": -81,
      "p50": -38,
      "p75": 195,
      "p90": 234,
      "p95": 288
    },
    "rows": [
      {
        "match": "Argentina v Algeria",
        "actual": "3-0",
        "oracle": "away 1-2",
        "oraclePoints": 0,
        "crowd": "home 2-1",
        "crowdPoints": 43
      },
      {
        "match": "Austria v Jordan",
        "actual": "3-1",
        "oracle": "away 1-2",
        "oraclePoints": 0,
        "crowd": "home 2-1",
        "crowdPoints": 38
      }
    ]
  }
};

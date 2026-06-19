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
      "ev": 50.77,
      "swing": true
    },
    {
      "match": "Austria v Jordan",
      "oracle": "home 2-1",
      "crowd": "home 2-1",
      "ev": 22.31,
      "swing": false
    },
    {
      "match": "Portugal v DR Congo",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 53.8,
      "swing": true
    },
    {
      "match": "England v Croatia",
      "oracle": "home 2-1",
      "crowd": "home 2-1",
      "ev": 30.6,
      "swing": false
    },
    {
      "match": "Ghana v Panama",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 80.91,
      "swing": true
    },
    {
      "match": "Uzbekistan v Colombia",
      "oracle": "away 1-2",
      "crowd": "away 1-2",
      "ev": 27.94,
      "swing": false
    },
    {
      "match": "Czech Republic v South Africa",
      "oracle": "away 1-2",
      "crowd": "home 2-1",
      "ev": 57.8,
      "swing": true
    },
    {
      "match": "Switzerland v Bosnia",
      "oracle": "home 2-1",
      "crowd": "home 2-1",
      "ev": 33.57,
      "swing": false
    },
    {
      "match": "Canada v Qatar",
      "oracle": "home 2-1",
      "crowd": "home 2-1",
      "ev": 37.74,
      "swing": false
    }
  ],
  "oracle": {
    "mean": 405.7772,
    "p10": 158,
    "p50": 378,
    "p75": 533,
    "p90": 689,
    "p95": 786
  },
  "crowd": {
    "mean": 260.0114,
    "p10": 142,
    "p50": 259,
    "p75": 321,
    "p90": 378,
    "p95": 417
  },
  "delta": {
    "mean": 145.7658,
    "p10": -139,
    "p50": 104,
    "p75": 290,
    "p90": 481,
    "p95": 544
  },
  "beatRate": 0.763,
  "bigSwingRate": 0.4084,
  "downsideRate": 0.1638,
  "histogram": [
    {
      "label": "< -200",
      "count": 210
    },
    {
      "label": "-200..-101",
      "count": 609
    },
    {
      "label": "-100..-1",
      "count": 340
    },
    {
      "label": "0..149",
      "count": 1799
    },
    {
      "label": "150..299",
      "count": 903
    },
    {
      "label": "300..499",
      "count": 700
    },
    {
      "label": "500+",
      "count": 439
    }
  ],
  "actuals": {
    "matched": 9,
    "oraclePoints": 288,
    "crowdPoints": 404,
    "delta": -116,
    "deltaPercentile": 0.1432,
    "deltaSummary": {
      "mean": 145.7658,
      "p10": -139,
      "p50": 104,
      "p75": 290,
      "p90": 481,
      "p95": 544
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
        "oracle": "home 2-1",
        "oraclePoints": 38,
        "crowd": "home 2-1",
        "crowdPoints": 38
      },
      {
        "match": "Portugal v DR Congo",
        "actual": "1-1",
        "oracle": "away 1-2",
        "oraclePoints": 0,
        "crowd": "home 2-1",
        "crowdPoints": 0
      },
      {
        "match": "England v Croatia",
        "actual": "4-2",
        "oracle": "home 2-1",
        "oraclePoints": 59,
        "crowd": "home 2-1",
        "crowdPoints": 59
      },
      {
        "match": "Ghana v Panama",
        "actual": "1-0",
        "oracle": "away 1-2",
        "oraclePoints": 0,
        "crowd": "home 2-1",
        "crowdPoints": 73
      },
      {
        "match": "Uzbekistan v Colombia",
        "actual": "1-3",
        "oracle": "away 1-2",
        "oraclePoints": 44,
        "crowd": "away 1-2",
        "crowdPoints": 44
      },
      {
        "match": "Czech Republic v South Africa",
        "actual": "1-1",
        "oracle": "away 1-2",
        "oraclePoints": 0,
        "crowd": "home 2-1",
        "crowdPoints": 0
      },
      {
        "match": "Switzerland v Bosnia",
        "actual": "4-1",
        "oracle": "home 2-1",
        "oraclePoints": 76,
        "crowd": "home 2-1",
        "crowdPoints": 76
      },
      {
        "match": "Canada v Qatar",
        "actual": "6-0",
        "oracle": "home 2-1",
        "oraclePoints": 71,
        "crowd": "home 2-1",
        "crowdPoints": 71
      }
    ]
  }
};

"""Expected Value optimizer for MPP predictions.

Models the full MPP scoring system: base quotations + rarity bonuses + double points.
"""
import math

CATCH_UP_THRESHOLD = 200

# Rarity bonus tiers (estimated from locale file and crowd data)
# Format: (max_crowd_pct, bonus_name, bonus_points)
RARITY_TIERS = [
    (0.02, "megaRare", 200),
    (0.05, "ultraRare", 100),
    (0.10, "rare", 50),
    (0.15, "veryRare", 25),
]

EXACT_SCORE_BONUS = 25  # Bonus for predicting the exact score


def estimate_bonus(crowd_pct):
    """Estimate rarity bonus points based on how few people picked this outcome.

    Args:
        crowd_pct: float 0-1, fraction of crowd that picked this outcome

    Returns:
        (bonus_name, bonus_points)
    """
    for threshold, name, points in RARITY_TIERS:
        if crowd_pct <= threshold:
            return name, points
    return None, 0


def expected_value(probs, points, crowd_pcts=None):
    """Compute EV including base points + estimated rarity bonus.

    Args:
        probs: {"home": P, "draw": P, "away": P}
        points: {"home": pts, "draw": pts, "away": pts}
        crowd_pcts: {"home": pct, "draw": pct, "away": pct} from MPP stats.bets
    """
    ev = {}
    for outcome in ["home", "draw", "away"]:
        base = probs[outcome] * points[outcome]
        bonus = 0
        if crowd_pcts and outcome in crowd_pcts:
            _, pts = estimate_bonus(crowd_pcts[outcome])
            bonus = probs[outcome] * pts
        ev[outcome] = base + bonus
    return ev


def _total_points(outcome, points, crowd_pcts, doubled=False):
    """Calculate total possible points for an outcome (base + bonus) × double."""
    total = points[outcome]
    if crowd_pcts and outcome in crowd_pcts:
        _, bonus = estimate_bonus(crowd_pcts[outcome])
        total += bonus
    # Exact score bonus (always attainable if you nail the score)
    total += EXACT_SCORE_BONUS
    if doubled:
        total *= 2
    return total


def recommend_pick(probs, points, points_behind=0, crowd_pcts=None, double_match=False):
    """Recommend the optimal MPP pick accounting for full scoring.

    Args:
        probs: {"home": P, "draw": P, "away": P} from ensemble
        points: {"home": pts, "draw": pts, "away": pts} from MPP API
        points_behind: how far behind the leader you are
        crowd_pcts: {"home": pct, "draw": pct, "away": pct} from MPP stats.bets
        double_match: True if this match has the double-points bonus active

    Returns:
        dict with outcome, ev, score, bonus info
    """
    ev = expected_value(probs, points, crowd_pcts)

    # Apply double-points multiplier
    if double_match:
        ev = {k: v * 2 for k, v in ev.items()}

    best = max(ev, key=ev.get)
    best_ev = ev[best]

    # Catch-up mode: prefer highest total-points candidate among close-EV options
    if points_behind > CATCH_UP_THRESHOLD:
        threshold = best_ev * 0.85
        # Rank by total possible points (reward) among candidates within 15% EV
        candidates = {}
        for k, v in ev.items():
            if v >= threshold:
                candidates[k] = _total_points(k, points, crowd_pcts, double_match)
        best = max(candidates, key=candidates.get)

    home_lambda = probs.get("home_lambda", 1.4)
    away_lambda = probs.get("away_lambda", 1.1)
    score = outcome_to_score(best, home_lambda, away_lambda)

    bonus_name, bonus_pts = estimate_bonus(crowd_pcts[best]) if crowd_pcts else (None, 0)
    total_possible = _total_points(best, points, crowd_pcts, double_match)

    return {
        "outcome": best,
        "ev": round(ev[best], 2),
        "all_ev": {k: round(v, 2) for k, v in ev.items()},
        "score": score,
        "base_points": points[best],
        "bonus_name": bonus_name,
        "bonus_points": bonus_pts,
        "total_possible": total_possible,
        "doubled": double_match,
        "reasoning": _reasoning(best, ev, points, points_behind, crowd_pcts, double_match),
    }


def recommend_double_match(matches, dataset, predictor, points_behind=0):
    """Recommend which match to apply the double-points bonus to.

    Args:
        matches: list of {"home": str, "away": str, "points": dict, "crowd": dict}
        dataset: team dataset
        predictor: EnsemblePredictor instance
        points_behind: points behind leader

    Returns:
        dict with match, pick, and expected boost
    """
    best_boost = 0
    best_match = None
    best_pick = None

    for match in matches:
        home = match["home"]
        away = match["away"]
        points = match["points"]
        crowd = match.get("crowd", {})

        result = predictor.predict(home, away, neutral=True)
        probs = {k: result[k] for k in ["home", "draw", "away"]}
        if "poisson" in result.get("models", {}):
            p = result["models"]["poisson"]
            probs["home_lambda"] = p.get("home_lambda", 1.4)
            probs["away_lambda"] = p.get("away_lambda", 1.1)

        # EV without double
        base_pick = recommend_pick(probs, points, points_behind, crowd, double_match=False)
        # EV with double
        double_pick = recommend_pick(probs, points, points_behind, crowd, double_match=True)

        boost = double_pick["ev"] - base_pick["ev"]

        if boost > best_boost:
            best_boost = boost
            best_match = match
            best_pick = double_pick

    return {
        "match": f"{best_match['home']} vs {best_match['away']}" if best_match else None,
        "pick": best_pick,
        "ev_boost": round(best_boost, 2),
    }


def outcome_to_score(outcome, home_lambda, away_lambda):
    """Convert an outcome pick to a realistic score prediction."""
    if outcome == "home":
        h = max(1, round(home_lambda))
        a = max(0, round(away_lambda * 0.7))
        if h <= a:
            h = a + 1
    elif outcome == "draw":
        avg = round((home_lambda + away_lambda) / 2)
        h = a = max(1, min(avg, 3))
    else:
        h = max(0, round(home_lambda * 0.7))
        a = max(1, round(away_lambda))
        if a <= h:
            a = h + 1
    return f"{h}-{a}"


def _reasoning(best, ev, points, behind, crowd_pcts=None, doubled=False):
    """Generate human-readable reasoning."""
    best_ev = ev[best]
    lines = [f"Best EV: {best} ({best_ev:.1f} pts expected)"]

    diffs = []
    for outcome in ["home", "draw", "away"]:
        if outcome != best:
            diffs.append(f"{outcome}: {ev[outcome]:.1f}")
    lines.append("vs " + ", ".join(diffs))

    if crowd_pcts and best in crowd_pcts:
        pct = crowd_pcts[best]
        _, bonus = estimate_bonus(pct)
        if bonus > 0:
            lines.append(f"crowd={pct:.0%} → +{bonus} rarity bonus")

    if doubled:
        lines.append("DOUBLED (2× points)")

    if behind > CATCH_UP_THRESHOLD:
        lines.append(f"Catch-up ({behind}pts behind)")

    return " | ".join(lines)

"""Expected Value optimizer for MPP predictions.

Given model probabilities and MPP point values, compute the optimal
pick that maximizes expected points. Includes catch-up mode.
"""
import math

CATCH_UP_THRESHOLD = 200


def expected_value(probs, points):
    """Compute EV for each outcome: EV = P(outcome) × points(outcome)."""
    return {
        "home": probs["home"] * points["home"],
        "draw": probs["draw"] * points["draw"],
        "away": probs["away"] * points["away"],
    }


def recommend_pick(probs, points, points_behind=0):
    """Recommend the optimal MPP pick.

    Args:
        probs: {"home": P, "draw": P, "away": P} from ensemble
        points: {"home": pts, "draw": pts, "away": pts} from MPP API
        points_behind: how far behind the leader you are

    Returns:
        dict with outcome, ev, reasoning, and suggested_score
    """
    ev = expected_value(probs, points)

    best = max(ev, key=ev.get)
    best_ev = ev[best]

    # Catch-up mode: prefer highest point value among close-EV options
    if points_behind > CATCH_UP_THRESHOLD:
        threshold = best_ev * 0.85
        candidates = {k: v for k, v in ev.items() if v >= threshold}
        best = max(candidates, key=lambda k: points[k])

    home_lambda = probs.get("home_lambda", 1.4)
    away_lambda = probs.get("away_lambda", 1.1)
    score = outcome_to_score(best, home_lambda, away_lambda)

    return {
        "outcome": best,
        "ev": round(ev[best], 2),
        "all_ev": {k: round(v, 2) for k, v in ev.items()},
        "score": score,
        "points": points[best],
        "reasoning": _reasoning(best, ev, points, points_behind),
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


def _reasoning(best, ev, points, behind):
    """Generate human-readable reasoning."""
    lines = [f"Best EV: {best} ({ev[best]:.1f} pts expected)"]
    diffs = []
    for outcome in ["home", "draw", "away"]:
        if outcome != best:
            diffs.append(f"{outcome}: {ev[outcome]:.1f}")
    lines.append("vs " + ", ".join(diffs))
    if behind > CATCH_UP_THRESHOLD:
        lines.append(f"Catch-up ({behind}pts behind): favoring high-reward")
    return " | ".join(lines)

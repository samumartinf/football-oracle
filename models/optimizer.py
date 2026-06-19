"""Expected Value optimizer for MPP predictions.

Models the full MPP scoring system: base quotations + rarity bonuses + double points.
"""
import math

CATCH_UP_THRESHOLD = 200
MIN_CONTRARIAN_EV_DELTA = 5.0  # Minimum EV advantage to justify a contrarian pick

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

    # Contrarian guard: require meaningful EV advantage over crowd favorite
    if crowd_pcts:
        crowd_fav = max(crowd_pcts, key=crowd_pcts.get)
        if best != crowd_fav:
            crowd_ev = ev[crowd_fav]
            if best_ev - crowd_ev < MIN_CONTRARIAN_EV_DELTA:
                best = crowd_fav
                best_ev = crowd_ev

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
    """Find the most likely scoreline for a given outcome using the full
    Poisson probability matrix (Dixon-Coles adjusted).

    Falls back to the old heuristic if the Poisson model is unavailable.
    """
    from models.poisson import most_likely_score, dixon_coles_adjust, score_probability

    probs = score_probability(home_lambda, away_lambda)
    probs = dixon_coles_adjust(probs, home_lambda, away_lambda)

    best_i, best_j, best_p = 0, 0, -1.0
    for i in range(len(probs)):
        for j in range(len(probs[0])):
            if outcome == "home" and i <= j:
                continue
            if outcome == "draw" and i != j:
                continue
            if outcome == "away" and i >= j:
                continue
            if probs[i][j] > best_p:
                best_p = probs[i][j]
                best_i, best_j = i, j

    if best_p > 0:
        return f"{best_i}-{best_j}"

    # Fallback heuristic
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
    contrarian_guard_note = ""
    if crowd_pcts:
        crowd_fav = max(crowd_pcts, key=crowd_pcts.get)
        if best == crowd_fav:
            # Check if we switched from contrarian
            orig_best = max(ev, key=ev.get)
            if orig_best != best:
                delta = ev[orig_best] - ev[best]
                if delta < MIN_CONTRARIAN_EV_DELTA:
                    contrarian_guard_note = f" | EV delta {delta:.1f} < {MIN_CONTRARIAN_EV_DELTA:.0f}, stayed safe"

    lines = [f"Best EV: {best} ({best_ev:.1f} pts expected)" + contrarian_guard_note]

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


# --- Risk-constrained batch optimization ---


def _is_contrarian(outcome, crowd_pcts):
    """An outcome is contrarian if it's not the crowd favorite."""
    if not crowd_pcts:
        return False
    favorite = max(crowd_pcts, key=crowd_pcts.get)
    return outcome != favorite


def _contrarian_boost(outcome, ev, crowd_pcts, points):
    """How much EV does the contrarian pick gain over the safe pick?"""
    if not crowd_pcts:
        return 0
    safe_outcome = max(crowd_pcts, key=crowd_pcts.get)
    safe_ev = ev.get(safe_outcome, 0)
    return ev.get(outcome, 0) - safe_ev


def recommend_batch(all_predictions, points_behind=0, max_contrarian=3, double_match_idx=None):
    """Optimize picks across all matches with a contrarian budget.

    Args:
        all_predictions: list of (match_info, probs, points, crowd_pcts) tuples
        points_behind: points behind leader (triggers catch-up mode)
        max_contrarian: max number of contrarian picks allowed
        double_match_idx: index of match to apply double points (or None)

    Returns:
        list of pick dicts (same shape as recommend_pick), matching input order
    """
    n = len(all_predictions)

    # Step 1: compute EV for all outcomes across all matches
    all_evs = []
    for match_info, probs, points, crowd in all_predictions:
        ev = expected_value(probs, points, crowd)
        all_evs.append(ev)

    # Step 2: for each match, determine the unconstrained best pick
    # and whether it's contrarian
    picks = []
    contrarian_matches = []  # (idx, contrarian_boost)

    for i, (ev, (match_info, probs, points, crowd)) in enumerate(zip(all_evs, all_predictions)):
        doubled = (double_match_idx is not None and i == double_match_idx)
        ev_copy = dict(ev)
        if doubled:
            ev_copy = {k: v * 2 for k, v in ev_copy.items()}

        best = max(ev_copy, key=ev_copy.get)

        # Catch-up logic (per-match, same as before)
        if points_behind > CATCH_UP_THRESHOLD:
            threshold = ev_copy[best] * 0.85
            candidates = {}
            for k, v in ev_copy.items():
                if v >= threshold:
                    candidates[k] = _total_points(k, points, crowd, doubled)
            best = max(candidates, key=candidates.get)

        contrarian = _is_contrarian(best, crowd)
        boost = _contrarian_boost(best, ev_copy, crowd, points)

        if contrarian:
            contrarian_matches.append((i, boost))

        # Compute score
        home_lambda = probs.get("home_lambda", 1.4)
        away_lambda = probs.get("away_lambda", 1.1)
        score = outcome_to_score(best, home_lambda, away_lambda)

        bonus_name, bonus_pts = estimate_bonus(crowd[best]) if crowd else (None, 0)
        total_possible = _total_points(best, points, crowd, doubled)

        picks.append({
            "outcome": best,
            "ev": round(ev_copy[best], 2),
            "score": score,
            "base_points": points[best],
            "bonus_name": bonus_name,
            "bonus_points": bonus_pts,
            "total_possible": total_possible,
            "doubled": doubled,
            "contrarian": contrarian,
            "reasoning": _reasoning(best, ev_copy, points, points_behind, crowd, doubled),
        })

    # Step 3: if we have too many contrarian picks, switch the weakest ones to safe
    if len(contrarian_matches) > max_contrarian:
        # Sort by contrarian boost (keep the highest-boost ones)
        contrarian_matches.sort(key=lambda x: x[1], reverse=True)
        keep_indices = {idx for idx, _ in contrarian_matches[:max_contrarian]}
        switch_indices = {idx for idx, _ in contrarian_matches[max_contrarian:]}

        for idx in switch_indices:
            match_info, probs, points, crowd = all_predictions[idx]
            doubled = (double_match_idx is not None and idx == double_match_idx)

            # Switch to the safe pick (crowd favorite)
            safe_outcome = max(crowd, key=crowd.get) if crowd else "home"
            ev = all_evs[idx]
            ev_copy = dict(ev)
            if doubled:
                ev_copy = {k: v * 2 for k, v in ev_copy.items()}

            home_lambda = probs.get("home_lambda", 1.4)
            away_lambda = probs.get("away_lambda", 1.1)
            score = outcome_to_score(safe_outcome, home_lambda, away_lambda)
            bonus_name, bonus_pts = estimate_bonus(crowd[safe_outcome]) if crowd else (None, 0)
            total_possible = _total_points(safe_outcome, points, crowd, doubled)

            picks[idx] = {
                "outcome": safe_outcome,
                "ev": round(ev_copy[safe_outcome], 2),
                "score": score,
                "base_points": points[safe_outcome],
                "bonus_name": bonus_name,
                "bonus_points": bonus_pts,
                "total_possible": total_possible,
                "doubled": doubled,
                "contrarian": False,
                "switched_from_contrarian": True,
                "reasoning": f"Risk cap: switched to safe {safe_outcome} "
                             f"(was {picks[idx]['outcome']}, "
                             f"lost {picks[idx]['ev'] - ev_copy[safe_outcome]:.1f} EV)",
            }

    return picks

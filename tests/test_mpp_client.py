"""Smoke tests for MPP API client (requires .env credentials)."""
import os
from pathlib import Path

import pytest

from mpp.auth import get_token
from mpp.client import get_matches, get_user

ENV_PATH = Path(__file__).parent.parent / ".env"
pytestmark = pytest.mark.skipif(
    not ENV_PATH.exists() or os.environ.get("RUN_MPP_LIVE_TESTS") != "1",
    reason="set RUN_MPP_LIVE_TESTS=1 with MPP credentials to run live API smoke tests",
)


def test_auth_gets_token():
    """Auth should return a non-empty token."""
    token = get_token()
    assert token
    assert len(token) > 50


def test_get_user():
    """Should return user profile with email."""
    user = get_user()
    assert "email" in user or "id" in user


def test_get_matches_returns_list():
    """Should return a list (may be empty between matchdays)."""
    matches = get_matches()
    assert isinstance(matches, list)
    if matches:
        m = matches[0]
        for key in ["match_id", "home_team", "away_team", "home_points"]:
            assert key in m, f"Missing {key}"

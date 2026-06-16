"""OAuth authentication for MPP using Playwright to handle JS challenges.

Extracts the Bearer token after login and caches it for API use.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

TOKEN_CACHE = Path(__file__).parent.parent / "data" / "token.json"


def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _capture_token(page):
    """Extract Bearer token from API requests made by the app after login."""
    # Wait for the app to make API calls after login
    token = None

    def on_request(request):
        nonlocal token
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and "api.mpp.football" in request.url:
            token = auth.split(" ")[1]

    page.on("request", on_request)

    # Wait for API calls to happen (the app loads data after login)
    page.wait_for_timeout(5000)

    # If token not captured from requests, try localStorage
    if not token:
        token = page.evaluate("() => localStorage.getItem('access_token') || "
                              "localStorage.getItem('auth_token') || "
                              "JSON.parse(localStorage.getItem('okta-token-storage') || '{}')?.accessToken?.accessToken || ''")

    return token


def get_token():
    """Get a Bearer token for MPP API access, using Playwright for auth.

    Caches the token and reuses it until expiry.
    """
    # Check cache
    if TOKEN_CACHE.exists():
        with open(TOKEN_CACHE) as f:
            cached = json.load(f)
        if cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]

    env = _load_env()
    email = env.get("MPP_EMAIL")
    password = env.get("MPP_PASSWORD")
    if not email or not password:
        raise RuntimeError("MPP_EMAIL/MPP_PASSWORD not found in .env")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})

        # Login flow (same as submit scripts)
        page.goto("https://mpp.football/", wait_until="networkidle", timeout=15000)
        page.get_by_text("Se connecter").first.click()
        page.wait_for_timeout(1500)
        page.get_by_role("textbox", name="Adresse e-mail").first.fill(email)
        page.locator('input[type="password"]').first.fill(password)
        page.get_by_role("button", name="Se connecter").first.click()

        token = _capture_token(page)
        browser.close()

    if not token:
        raise RuntimeError("Failed to extract auth token from MPP session")

    # Cache with 1-hour expiry
    with open(TOKEN_CACHE, "w") as f:
        json.dump({"access_token": token, "expires_at": time.time() + 3500}, f)

    return token


def get_headers():
    """Get Authorization headers for MPP API calls."""
    token = get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


if __name__ == "__main__":
    token = get_token()
    print(f"Token: {token[:40]}...")
    print("Auth OK")

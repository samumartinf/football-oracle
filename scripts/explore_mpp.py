"""Explore MPP prediction interface to understand scoring."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

env_path = Path(__file__).parent.parent / ".env"
env = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

EMAIL = env["MPP_EMAIL"]
PASSWORD = env["MPP_PASSWORD"]

OUTPUT_DIR = Path.home() / ".hermes" / "cache" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    # Login
    page.goto("https://mpp.football/", wait_until="networkidle")
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(1500)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(5000)
    
    print(f"Logged in. URL: {page.url}")
    print(f"Title: {page.title()}")
    
    # Dump the full page content
    page.screenshot(path=str(OUTPUT_DIR / "mpp_dashboard.png"), full_page=False)
    
    # Get all text content
    body = page.locator("body").inner_text()
    print("\n=== PAGE CONTENT ===")
    print(body[:3000])
    
    # Look for match cards or prediction elements
    print("\n=== CLICKABLE ELEMENTS ===")
    buttons = page.locator("button, a, [role='button']").all()
    for i, btn in enumerate(buttons[:30]):
        try:
            text = btn.inner_text().strip()[:80]
            if text:
                print(f"  [{i}] {text}")
        except:
            pass
    
    # Try to find and click on a match to see prediction form
    print("\n=== LOOKING FOR MATCHES ===")
    # Look for text containing team names
    france = page.locator("text=France").first
    if france.is_visible():
        print("Found 'France' element - clicking...")
        france.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUTPUT_DIR / "mpp_match_detail.png"), full_page=False)
        
        detail = page.locator("body").inner_text()
        print("\n=== MATCH DETAIL ===")
        print(detail[:2000])
    
    browser.close()

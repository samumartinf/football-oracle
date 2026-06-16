"""Verify MPP login credentials via Playwright."""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Load .env manually to avoid python-dotenv dependency
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
    
    # Step 1: Landing page
    print("1. Navigating to MPP...")
    page.goto("https://mpp.football/", wait_until="networkidle")
    page.screenshot(path=str(OUTPUT_DIR / "mpp_step1_landing.png"))
    print("   ✓ Landing page loaded")
    
    # Step 2: Click "Se connecter"
    print("2. Clicking 'Se connecter'...")
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUTPUT_DIR / "mpp_step2_login_form.png"))
    print("   ✓ Login form appeared")
    
    # Step 3: Fill credentials
    print("3. Filling credentials...")
    # Find inputs - the login form has email and password fields
    email_input = page.locator('input[type="email"], input[name="email"], input[aria-label*="mail" i], input[placeholder*="mail" i]').first
    if not email_input.is_visible():
        # Try by role
        email_input = page.get_by_role("textbox", name="Adresse e-mail").first
    email_input.fill(EMAIL)
    
    password_input = page.locator('input[type="password"]').first
    password_input.fill(PASSWORD)
    print("   ✓ Credentials filled")
    
    # Step 4: Submit
    print("4. Clicking submit...")
    # Wait for button to become enabled (it's disabled until fields are filled)
    page.wait_for_timeout(500)
    submit_btn = page.get_by_role("button", name="Se connecter").first
    page.screenshot(path=str(OUTPUT_DIR / "mpp_step3_before_submit.png"))
    
    submit_btn.click()
    page.wait_for_timeout(5000)  # Wait for auth + redirect
    
    # Step 5: Check result
    print("5. Checking result...")
    page.screenshot(path=str(OUTPUT_DIR / "mpp_step4_after_login.png"))
    
    current_url = page.url
    page_title = page.title()
    
    print(f"   URL: {current_url}")
    print(f"   Title: {page_title}")
    
    # Check for success indicators
    if "login" in current_url.lower() or "auth" in current_url.lower():
        print("\n❌ LOGIN FAILED - still on auth page")
        # Check for error messages
        error = page.locator('[role="alert"], .error, .text-red').first
        if error.is_visible():
            print(f"   Error message: {error.text_content()}")
        sys.exit(1)
    else:
        print("\n✅ LOGIN SUCCESSFUL!")
        # Print page content summary
        body_text = page.locator("body").inner_text()[:500]
        print(f"   Page preview: {body_text[:200]}...")
    
    browser.close()

print("\nScreenshots saved to:", OUTPUT_DIR)

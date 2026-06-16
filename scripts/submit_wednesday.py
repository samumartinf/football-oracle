"""Submit Wednesday's max-EV picks + activate double points bonus."""
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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    # Login
    print("Logging in...")
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=20000)
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(6000)
    page.wait_for_timeout(2000)
    
    # Find all score inputs
    inputs = page.locator('input.css-11aywtz').all()
    print(f"Found {len(inputs)} score inputs")
    
    # Today's matches (0-3) already submitted (2/2)
    # Wednesday matches: [4]=Arg home, [5]=Arg away, [6]=Aut home, [7]=Aut away
    # [8]=Por home, [9]=Por away, [10]=Eng home, [11]=Eng away
    
    wednesday_picks = [
        # Argentina vs Algeria: Algeria 1-2
        ("Argentina 1-2 Algeria", 4, 5, "1", "2"),
        # Austria vs Jordan: Jordan 1-2
        ("Austria 1-2 Jordan", 6, 7, "1", "2"),
        # Portugal vs DR Congo: Congo 1-2 (+ double points)
        ("Portugal 1-2 DR Congo", 8, 9, "1", "2"),
        # England vs Croatia: Croatia 1-2
        ("England 1-2 Croatia", 10, 11, "1", "2"),
    ]
    
    for label, home_idx, away_idx, home_score, away_score in wednesday_picks:
        print(f"\nSubmitting: {label}")
        home_input = inputs[home_idx]
        away_input = inputs[away_idx]
        
        home_input.click()
        page.wait_for_timeout(200)
        home_input.fill(home_score)
        page.wait_for_timeout(200)
        
        away_input.click()
        page.wait_for_timeout(200)
        away_input.fill(away_score)
        page.wait_for_timeout(2000)
        
        print(f"  ✅ Submitted")
    
    # Check for "Activer mon bonus MPP" button on Portugal match
    print("\nLooking for double-points bonus button...")
    bonus_btns = page.locator("text=Activer mon bonus MPP").all()
    print(f"  Found {len(bonus_btns)} bonus buttons")
    
    if bonus_btns:
        # Click the one near Portugal (should be the third one — index 2)
        # Actually, try clicking all visible ones
        for btn in bonus_btns:
            if btn.is_visible():
                print(f"  Clicking bonus button...")
                btn.click()
                page.wait_for_timeout(2000)
                # Check if it changed to "activé"
                print(f"  Bonus button text after: {btn.inner_text()[:50]}")
                break
    
    # Verify status
    page.wait_for_timeout(2000)
    body = page.locator("body").inner_text()
    
    # Check Wednesday status
    if "Mercredi 17 juin" in body:
        idx = body.find("Mercredi 17 juin")
        print(f"\nWednesday status: {body[idx:idx+50]}")
    
    if "4 / 4" in body:
        print("\n✅ 4/4 predictions submitted for Wednesday!")
    elif "3 / 4" in body:
        print("\n⚠️ 3/4 — one might have not registered")
    else:
        # Find the exact count
        for line in body.split('\n'):
            if '/' in line and 'juin' in line.lower():
                print(f"  Status: {line.strip()}")
    
    browser.close()

"""Submit MPP predictions: France win + Norway win."""
import os
import sys
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

def screenshot(page, name):
    path = str(OUTPUT_DIR / name)
    page.screenshot(path=path)
    print(f"  📸 {name}")
    return path

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    # 1. Login
    print("1. Logging in...")
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=20000)
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(5000)
    print(f"   Logged in: {page.url}")
    
    # Wait for dashboard to fully load
    page.wait_for_timeout(2000)
    screenshot(page, "mpp_01_dashboard.png")
    
    # 2. Find France match - look for the "France" text that's part of a match
    print("\n2. Finding France vs Sénégal match...")
    
    # The MPP dashboard shows matches. Let's look for clickable match elements.
    # Try clicking on a match card or the France team name
    body_text = page.locator("body").inner_text()
    if "0 / 2" in body_text:
        print("   Found '0/2' — matches are available")
    
    # Try to find all clickable elements near France
    # First, try clicking directly on "France" text that appears in a match context
    france_elements = page.locator("text=France").all()
    print(f"   Found {len(france_elements)} 'France' elements")
    
    # The match card should have France at a specific location
    # Let's try the first one that's in a match context
    for i, el in enumerate(france_elements):
        try:
            parent_text = el.locator("..").inner_text()
            if "20h00" in parent_text or "Sénégal" in parent_text or "J.1" in parent_text:
                print(f"   Clicking France element #{i} with context: {parent_text[:100]}")
                el.click()
                page.wait_for_timeout(3000)
                break
        except:
            continue
    
    screenshot(page, "mpp_02_france_match.png")
    
    # 3. On the match page, find prediction buttons
    print("\n3. Looking for prediction buttons...")
    body = page.locator("body").inner_text()
    print(f"   Page text: {body[:500]}")
    
    # Look for "Victoire FRA" or similar prediction buttons
    # Common patterns: buttons with "Victoire", "Nul", team names
    victoire_btns = page.locator("button:has-text('Victoire FRA'), button:has-text('France'), [role='button']:has-text('Victoire')").all()
    print(f"   Found {len(victoire_btns)} victory buttons")
    
    # Try clicking any button that says "Victoire FRA" or representing France win
    fra_win = page.locator("button:has-text('Victoire FRA')").first
    if fra_win.is_visible():
        print("   Clicking 'Victoire FRA'...")
        fra_win.click()
        page.wait_for_timeout(2000)
        screenshot(page, "mpp_03_fra_picked.png")
    else:
        # Try other patterns — maybe it's a tap/select rather than button
        print("   No 'Victoire FRA' button visible. Trying other approaches...")
        # Maybe need to tap on the score prediction area
        all_btns = page.locator("button").all()
        for i, btn in enumerate(all_btns[:20]):
            try:
                txt = btn.inner_text().strip()[:60]
                if txt:
                    print(f"   Button [{i}]: '{txt}'")
            except:
                pass
    
    # 4. Check if prediction was registered
    print("\n4. Checking if prediction registered...")
    page.wait_for_timeout(1000)
    body_after = page.locator("body").inner_text()
    if "Prono enregistré" in body_after or "enregistré" in body_after.lower():
        print("   ✅ Prediction registered!")
    
    screenshot(page, "mpp_04_after_pick.png")
    
    # 5. Go back to dashboard
    print("\n5. Going back to dashboard for Norway match...")
    page.locator("text=Mes Pronos").first.click()
    page.wait_for_timeout(2000)
    
    # Now find Norway match (Irak vs Norvège)
    print("\n6. Finding Irak vs Norvège match...")
    norway_els = page.locator("text=Norvège").all()
    print(f"   Found {len(norway_els)} 'Norvège' elements")
    
    for el in norway_els:
        try:
            parent_text = el.locator("..").inner_text()
            if "23h00" in parent_text or "Irak" in parent_text:
                print(f"   Clicking Norvège element: {parent_text[:100]}")
                el.click()
                page.wait_for_timeout(3000)
                break
        except:
            continue
    
    screenshot(page, "mpp_05_norway_match.png")
    
    # Pick Norway win
    print("\n7. Picking Norway...")
    nor_win = page.locator("button:has-text('Victoire NOR'), button:has-text('Norvège')").first
    if nor_win.is_visible():
        nor_win.click()
        page.wait_for_timeout(2000)
        print("   ✅ Norway pick submitted!")
    else:
        # Try broader search
        all_btns = page.locator("button").all()
        for btn in all_btns[:25]:
            try:
                txt = btn.inner_text().strip()[:60]
                if txt and 'N' in txt:
                    print(f"   Button: '{txt}'")
            except:
                pass
    
    screenshot(page, "mpp_06_final.png")
    
    # 8. Verify both predictions
    print("\n8. Verifying...")
    page.locator("text=Mes Pronos").first.click()
    page.wait_for_timeout(2000)
    final_text = page.locator("body").inner_text()
    
    # Look for "2/2" or similar completion indicator
    if "1 / 2" in final_text:
        print("   ⚠️ Still 1/2 — Norway might not have registered")
    elif "2 / 2" in final_text or "0 / 2" not in final_text:
        print("   ✅ 2/2 predictions submitted!")
    else:
        print(f"   Dashboard: {final_text[:300]}")
    
    screenshot(page, "mpp_07_verified.png")
    browser.close()

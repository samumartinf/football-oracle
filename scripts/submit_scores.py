"""Submit exact score predictions: France 2-0 Senegal, Norway 3-0 Iraq."""
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
    page.wait_for_timeout(5000)
    
    # Wait for dashboard
    page.wait_for_timeout(2000)
    
    # Find all INPUT elements on the page
    inputs = page.locator('input').all()
    print(f"Found {len(inputs)} input elements")
    
    for i, inp in enumerate(inputs):
        box = inp.bounding_box()
        val = inp.input_value()
        placeholder = inp.get_attribute('placeholder') or ''
        name = inp.get_attribute('name') or ''
        cls = inp.get_attribute('class') or ''
        print(f"  Input[{i}]: pos=({box['x']:.0f},{box['y']:.0f}) val='{val}' placeholder='{placeholder}' name='{name}' class='{cls[:60]}'")
    
    # The match rows: France is first, Iraq/Norway is second
    # Each match has 2 inputs: home score then away score
    # France inputs: [0] and [1], Iraq/Norway: [2] and [3]
    
    # Predict France 2-0 Senegal
    print("\n=== FRANCE vs SENEGAL: predicting 2-0 ===")
    france_home = inputs[0]
    france_away = inputs[1]
    
    france_home.click()
    page.wait_for_timeout(300)
    france_home.fill("2")
    page.wait_for_timeout(500)
    
    france_away.click()
    page.wait_for_timeout(300)
    france_away.fill("0")
    page.wait_for_timeout(500)
    
    print("  Filled: France 2-0")
    
    # Check if any submit/save button appeared
    body = page.locator("body").inner_text()
    if "Valider" in body or "Enregistrer" in body:
        print(f"  Submit button appeared! Body: {body[:500]}")
    
    # Predict Norway 3-0 Iraq
    print("\n=== IRAK vs NORVEGE: predicting 0-3 ===")
    iraq_home = inputs[2]
    norway_away = inputs[3]
    
    iraq_home.click()
    page.wait_for_timeout(300)
    iraq_home.fill("0")
    page.wait_for_timeout(500)
    
    norway_away.click()
    page.wait_for_timeout(300)
    norway_away.fill("3")
    page.wait_for_timeout(500)
    
    print("  Filled: Iraq 0-3 Norway")
    
    # Wait and check for auto-save or confirmation
    page.wait_for_timeout(3000)
    
    body = page.locator("body").inner_text()
    print(f"\nPage after predictions: {body[:600]}")
    
    # Look for "Valider" button
    valider = page.locator("button:has-text('Valider'), div:has-text('Valider')").first
    if valider.is_visible():
        print("\n  Found 'Valider' button — clicking!")
        valider.click()
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text()
        print(f"  After validate: {body[:400]}")
    
    # Also check for text like "Pronos enregistrés" or checkmark
    if "enregistré" in body.lower():
        print("\n✅ Predictions saved!")
    
    # Verify: check if "0/2" changed
    if "1 / 2" in body or "2 / 2" in body:
        print(f"  Status updated: {body[body.find('/ 2')-5:body.find('/ 2')+10]}")
    
    browser.close()

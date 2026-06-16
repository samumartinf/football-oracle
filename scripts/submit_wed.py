"""Submit Wednesday picks — max EV underdog sweep."""
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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    print("Logging in...")
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=15000)
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(1500)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(env["MPP_EMAIL"])
    page.locator('input[type="password"]').first.fill(env["MPP_PASSWORD"])
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(5000)
    
    inputs = page.locator('input.css-11aywtz').all()
    print(f"Found {len(inputs)} inputs")
    
    picks = [
        ("Arg 1-2 Alg", 4, 5, "1", "2"),
        ("Aut 1-2 Jor", 6, 7, "1", "2"),
        ("Por 1-2 Con", 8, 9, "1", "2"),
        ("Eng 1-2 Cro", 10, 11, "1", "2"),
    ]
    
    for name, hi, ai, hs, aws in picks:
        print(f"  {name}...")
        inputs[hi].click()
        page.wait_for_timeout(150)
        inputs[hi].fill(hs)
        page.wait_for_timeout(150)
        inputs[ai].click()
        page.wait_for_timeout(150)
        inputs[ai].fill(aws)
        page.wait_for_timeout(1000)
    
    # Verify
    page.wait_for_timeout(1000)
    body = page.locator("body").inner_text()
    if "4 / 4" in body:
        print("\n✅ 4/4 submitted!")
    else:
        for line in body.split('\n'):
            if 'Mercredi' in line or '/ 4' in line:
                print(f"  {line.strip()}")
    
    browser.close()

"""Deep-dive into MPP DOM structure to find prediction submission mechanism."""
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
    print(f"URL: {page.url}")
    
    # Extract all interactive elements with their attributes
    print("\n=== ALL INTERACTIVE ELEMENTS ===")
    elements = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('*');
        all.forEach(el => {
            const role = el.getAttribute('role');
            const ariaLabel = el.getAttribute('aria-label');
            const onClick = el.onclick !== null || el.getAttribute('onclick');
            const text = (el.textContent || '').trim().slice(0, 60);
            const tag = el.tagName;
            const classes = (el.className || '').toString().slice(0, 80);
            const dataAttrs = Array.from(el.attributes)
                .filter(a => a.name.startsWith('data-'))
                .map(a => `${a.name}=${a.value.slice(0,40)}`)
                .join(', ');
            
            if (tag === 'BUTTON' || tag === 'A' || role === 'button' || onClick || ariaLabel || dataAttrs) {
                results.push({
                    tag, role, ariaLabel, text, classes, dataAttrs,
                    rect: el.getBoundingClientRect()
                });
            }
        });
        return results;
    }""")
    
    for i, el in enumerate(elements):
        rect = el['rect']
        if rect['width'] > 0 and rect['height'] > 0:
            print(f"[{i}] <{el['tag']}> role={el['role']} aria={el['ariaLabel']} "
                  f"pos=({rect['x']:.0f},{rect['y']:.0f}) size=({rect['width']:.0f}x{rect['height']:.0f}) "
                  f"classes='{el['classes'][:60]}' data='{el['dataAttrs'][:60]}' text='{el['text'][:60]}'")
    
    # Look specifically for the point values (46, 128, 153)
    print("\n=== ELEMENTS CONTAINING '46', '128', or '153' ===")
    for el in elements:
        text = el['text']
        if text in ['46', '128', '153', '30', '178', '144', '59', '119', '133']:
            rect = el['rect']
            print(f"  <{el['tag']}> text='{text}' pos=({rect['x']:.0f},{rect['y']:.0f}) "
                  f"size=({rect['width']:.0f}x{rect['height']:.0f}) "
                  f"data='{el['dataAttrs']}' classes='{el['classes'][:80]}'")
    
    # Now try clicking on "46" (France win points) to submit prediction
    print("\n=== ATTEMPTING TO CLICK '46' ===")
    # Try to find element with exact text "46" that's clickable
    forty_six = page.locator("text=46").first
    if forty_six.is_visible():
        box = forty_six.bounding_box()
        print(f"  '46' element at ({box['x']:.0f}, {box['y']:.0f}), clicking...")
        forty_six.click()
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text()
        print(f"  After click: {body[:400]}")
        
        # Check if prediction UI changed
        if "Prono" in body or "enregistré" in body.lower() or "Valider" in body:
            print("  ✅ Prediction UI appeared!")
    
    # Try clicking on the match row area
    print("\n=== TRYING ALTERNATIVE CLICK TARGETS ===")
    body = page.locator("body").inner_text()
    print(f"Full body text: {body[:800]}")
    
    browser.close()

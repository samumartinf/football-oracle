"""Get a fresh MPP API token and try the forecast endpoint."""
import json
import urllib.request
import urllib.parse
from pathlib import Path

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

# Step 1: Get auth code by logging in via the Ligue1 Connect flow
# This is OAuth with PKCE - we need to simulate the flow

# Actually, let's use Playwright to capture the actual API calls during prediction submission
# with fewer timeouts
from playwright.sync_api import sync_playwright

forecast_calls = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    def log_request(request):
        url = request.url
        method = request.method
        if method in ['POST', 'PUT', 'PATCH', 'DELETE'] and ('mpp.football' in url or 'mpg' in url):
            forecast_calls.append({
                'method': method,
                'url': url,
                'post_data': str(request.post_data)[:1000] if request.post_data else None,
                'headers': dict(request.headers),
            })
    
    page.on('request', log_request)
    
    # Login
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=15000)
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(1000)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(6000)
    
    # Wait for dashboard and inputs
    page.wait_for_timeout(1000)
    inputs = page.locator('input.css-11aywtz').all()
    print(f"Score inputs found: {len(inputs)}")
    
    if len(inputs) >= 6:
        # Predict Austria vs Jordan: 2-0 (inputs[6]=home, [7]=away)
        print("Setting Austria 2-0...")
        inputs[6].click()
        page.wait_for_timeout(200)
        inputs[6].fill("2")
        page.wait_for_timeout(200)
        inputs[7].click()
        page.wait_for_timeout(200)
        inputs[7].fill("0")
        page.wait_for_timeout(3000)
        
        print(f"Captured {len(forecast_calls)} POST/PUT/PATCH calls")
        for c in forecast_calls:
            print(f"\n  {c['method']} {c['url']}")
            print(f"  Headers: {json.dumps({k:v for k,v in c['headers'].items() if k in ['authorization', 'content-type', 'accept']}, indent=2)}")
            if c['post_data']:
                print(f"  Body: {c['post_data']}")
        
        # Clear it
        inputs[6].click()
        page.wait_for_timeout(200)
        inputs[6].fill("")
        page.wait_for_timeout(200)
        inputs[7].click()
        page.wait_for_timeout(200)
        inputs[7].fill("")
        page.wait_for_timeout(2000)
    
    browser.close()

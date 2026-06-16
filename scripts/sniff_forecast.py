"""Sniff the MPP API during prediction submission to find the forecast endpoint."""
import json
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

api_calls = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    
    def log_request(request):
        url = request.url
        if 'api.mpp.football' in url or 'mpg' in url:
            api_calls.append({
                'method': request.method,
                'url': url.split('?')[0],
                'full_url': url,
                'post_data': str(request.post_data)[:500] if request.post_data else None,
            })
    
    def log_response(response):
        url = response.url
        if 'api.mpp.football' in url or 'mpg' in url:
            for call in api_calls:
                if call['full_url'] == url and 'status' not in call:
                    call['status'] = response.status
                    try:
                        body = response.text()
                        call['response'] = body[:800]
                    except:
                        call['response'] = '[binary]'
                    break
    
    page.on('request', log_request)
    page.on('response', log_response)
    
    # Login
    print("Logging in...")
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=20000)
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(8000)
    
    # Wait for dashboard
    print("Waiting for dashboard...")
    page.wait_for_timeout(3000)
    
    # Find the Argentina match inputs (Wednesday, first match - currently 0/4)
    # Input order: [0]=France home, [1]=France away, [2]=Iraq home, [3]=Norway away
    # [4]=Argentina home (first Wednesday match), [5]=Argentina away
    inputs = page.locator('input').all()
    print(f"Found {len(inputs)} inputs")
    
    # Scroll down to see Wednesday matches
    print("Scrolling to Wednesday matches...")
    page.evaluate("window.scrollBy(0, 300)")
    page.wait_for_timeout(1000)
    
    # Submit a test prediction: Argentina 3-1 Algeria
    print("Submitting Argentina 3-1 as test...")
    arg_home = inputs[4]
    arg_away = inputs[5]
    
    arg_home.click()
    page.wait_for_timeout(300)
    arg_home.fill("3")
    page.wait_for_timeout(300)
    
    arg_away.click()
    page.wait_for_timeout(300)
    arg_away.fill("1")
    page.wait_for_timeout(2000)
    
    print("Waiting for API call to register...")
    page.wait_for_timeout(3000)
    
    # Print API calls related to submission
    print(f"\n=== {len(api_calls)} API CALLS TO MPP/MPG ===")
    for i, call in enumerate(api_calls):
        if call.get('post_data') or 'forecast' in call['url'].lower() or 'predict' in call['url'].lower() or call['method'] in ['POST', 'PUT', 'PATCH']:
            print(f"\n[{i}] {call['method']} {call['status']} {call['url']}")
            if call.get('post_data'):
                print(f"    POST DATA: {call['post_data']}")
            if call.get('response'):
                print(f"    RESPONSE: {call['response']}")
    
    # Now clear the prediction by setting it back to empty
    print("\nClearing test prediction...")
    arg_home.click()
    page.wait_for_timeout(300)
    arg_home.fill("")
    page.wait_for_timeout(300)
    arg_away.click()
    page.wait_for_timeout(300)
    arg_away.fill("")
    page.wait_for_timeout(2000)
    
    page.wait_for_timeout(2000)
    
    # Check for any new API calls
    print(f"\n=== POST-CLEAR API CALLS ===")
    for i, call in enumerate(api_calls):
        if call.get('post_data') or call['method'] in ['POST', 'PUT', 'PATCH', 'DELETE']:
            if i >= len(api_calls) - 10:  # Last 10
                print(f"[{i}] {call['method']} {call['status']} {call['url']}")
                if call.get('post_data'):
                    print(f"    POST: {call['post_data']}")
                if call.get('response'):
                    print(f"    RESP: {call['response']}")
    
    # Save
    output = Path(__file__).parent.parent / "data" / "forecast_api.json"
    with open(output, 'w') as f:
        json.dump(api_calls, f, indent=2)
    print(f"\nSaved to {output}")
    
    browser.close()

"""Sniff MPP API calls by logging network requests during login and browsing."""
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
    
    # Capture ALL network requests
    def log_request(request):
        url = request.url
        method = request.method
        headers = dict(request.headers)
        post_data = request.post_data
        # Filter noise
        if any(x in url for x in ['adjust', 'sentry', 'google', 'facebook', 'apple', 'cdn']):
            return
        api_calls.append({
            'method': method,
            'url': url,
            'headers': {k: v for k, v in headers.items() if k in ['content-type', 'authorization', 'x-csrf', 'cookie']},
            'post_data': str(post_data)[:200] if post_data else None
        })
    
    def log_response(response):
        url = response.url
        if any(x in url for x in ['adjust', 'sentry', 'google', 'facebook', 'apple', 'cdn']):
            return
        # Find matching request and add response info
        for call in api_calls:
            if call['url'] == url and 'status' not in call:
                call['status'] = response.status
                try:
                    body = response.text()
                    call['response_body'] = body[:500]
                except:
                    call['response_body'] = '[binary/cannot read]'
                break
    
    page.on('request', log_request)
    page.on('response', log_response)
    
    # Login flow
    print("Navigating to MPP...")
    page.goto("https://mpp.football/", wait_until="networkidle", timeout=20000)
    page.wait_for_timeout(2000)
    
    print("Clicking login...")
    page.get_by_text("Se connecter").first.click()
    page.wait_for_timeout(2000)
    
    print("Filling credentials...")
    page.get_by_role("textbox", name="Adresse e-mail").first.fill(EMAIL)
    page.locator('input[type="password"]').first.fill(PASSWORD)
    
    print("Submitting...")
    page.get_by_role("button", name="Se connecter").first.click()
    page.wait_for_timeout(8000)
    
    # Navigate around to trigger more API calls
    print("Browsing around...")
    page.wait_for_timeout(2000)
    
    # Print API calls
    print(f"\n=== {len(api_calls)} API CALLS CAPTURED ===\n")
    for i, call in enumerate(api_calls):
        status = call.get('status', '?')
        print(f"[{i}] {call['method']} {status} {call['url']}")
        if call['post_data']:
            print(f"    POST: {call['post_data'][:150]}")
        if call.get('response_body'):
            body = call['response_body'][:300]
            print(f"    RESP: {body}")
        print()
    
    # Save to file for analysis
    output_path = Path(__file__).parent.parent / "data" / "api_calls.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(api_calls, f, indent=2)
    print(f"Saved to {output_path}")
    
    browser.close()

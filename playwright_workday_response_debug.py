from playwright.sync_api import sync_playwright

url = 'https://hl.wd1.myworkdayjobs.com/Campus?locations=979d930e2eac0100f4fbe3fe6bb20000'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    responses = []

    def capture_response(response):
        if '/jobs' in response.url and response.request.method == 'POST':
            try:
                text = response.text()
            except Exception as e:
                text = f'<error reading response: {e}>'
            responses.append((response.url, response.status, text[:2000]))

    page.on('response', capture_response)

    page.goto(url, wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(10000)

    print('Captured responses:')
    for url, status, snippet in responses:
        print('---')
        print('URL:', url)
        print('Status:', status)
        print('Snippet:', snippet)

    browser.close()

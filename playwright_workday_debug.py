from playwright.sync_api import sync_playwright

url = 'https://hl.wd1.myworkdayjobs.com/Campus?locations=979d930e2eac0100f4fbe3fe6bb20000'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = context.new_page()

    requests = []

    def log_request(request):
        url = request.url
        if 'workdayjobs' in url and request.resource_type in ['xhr', 'fetch', 'document']:
            requests.append((request.method, url))

    page.on('request', log_request)

    print('Navigating to page...')
    page.goto(url, wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(10000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)

    print(f'Loaded content length: {len(page.content())}')
    print('Requests captured:')
    for method, req_url in requests:
        print(method, req_url)

    try:
        print('Checking job list elements...')
        job_count = page.evaluate("document.querySelectorAll('[data-automation-id=jobTile], .jobTitle, .job-listing, .WDJobListing').length")
        print('Job tile count:', job_count)
    except Exception as e:
        print('Job selector check failed:', str(e))

    print('Page title:', page.title())
    print('HTML snippet:')
    snippet = page.content()[:4000]
    print(snippet)

    browser.close()

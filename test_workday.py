#!/usr/bin/env python3
from playwright.sync_api import sync_playwright

url = 'https://hl.wd1.myworkdayjobs.com/Campus?locations=979d930e2eac0100f4fbe3fe6bb20000'

print('Checking Workday page content...')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(8000)
    content = page.content()
    browser.close()

    # Simple checks
    has_intern = 'intern' in content.lower()
    has_praktikum = 'praktikum' in content.lower()
    has_job = 'job' in content.lower()
    has_position = 'position' in content.lower()
    has_career = 'career' in content.lower()

    print(f'Content length: {len(content)}')
    print(f'Has intern keywords: {has_intern}')
    print(f'Has praktikum: {has_praktikum}')
    print(f'Has job: {has_job}')
    print(f'Has position: {has_position}')
    print(f'Has career: {has_career}')

    # Extract some sample content around job-related words
    import re
    job_context = re.findall(r'.{50}(?:intern|praktikum|student|graduate).{50}', content, re.IGNORECASE)
    if job_context:
        print(f'\nSample job contexts found: {len(job_context)}')
        for i, ctx in enumerate(job_context[:3]):
            print(f'{i+1}: ...{ctx}...')
    else:
        print('\nNo job contexts found in content')
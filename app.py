"""Flask-Anwendung für Internship Tracker"""
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import json
import os
import re
import requests
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from tracker import InternshipTracker
from claude_api import InternshipExtractor

app = Flask(__name__)
app.config.from_object(Config)

tracker = InternshipTracker()
extractor = InternshipExtractor()


def send_email(to_address: str, subject: str, body: str) -> dict:
    if not Config.BREVO_API_KEY:
        return {'success': False, 'error': 'Brevo API Key nicht gesetzt'}
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = Config.BREVO_API_KEY
        api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        mail = sib_api_v3_sdk.SendSmtpEmail(
            sender={'name': Config.EMAIL_FROM_NAME, 'email': Config.EMAIL_FROM},
            to=[{'email': to_address}],
            subject=subject,
            text_content=body
        )
        api.send_transac_email(mail)
        return {'success': True}
    except ApiException as e:
        return {'success': False, 'error': str(e)}


def period_sort_key(period: str) -> tuple:
    """Gibt einen sortierbaren Schlüssel für Quartalszeiträume zurück."""
    if not period:
        return (9999, 9999)
    first = period.split(',')[0].strip()
    m = re.match(r'Q([1-4])[/\s](\d{2,4})', first)
    if m:
        q = int(m.group(1))
        y = int(m.group(2))
        if y < 100:
            y += 2000
        return (y, q)
    m = re.match(r'^(\d{4})$', first)
    if m:
        return (int(m.group(1)), 0)
    return (9998, 9998)


def extract_period(title: str) -> str:
    """Extrahiert Quartal/Zeitraum aus einem Stellentitel, z.B. 'Q3/26'."""
    if not title:
        return ''
    # Q1 2027, Q2/27, Q4 26, Q3/2026 etc.
    m = re.search(r'Q([1-4])\s*[/\s]\s*(?:20)?(\d{2})\b', title, re.IGNORECASE)
    if m:
        return f'Q{m.group(1)}/{m.group(2)[-2:]}'
    # Nur Q4 ohne Jahr
    m = re.search(r'\bQ([1-4])\b', title, re.IGNORECASE)
    if m:
        return f'Q{m.group(1)}'
    return ''


def load_source_config() -> list:
    config_path = os.path.join(os.path.dirname(__file__), 'config_sources.json')
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def get_new_company_notice() -> list:
    history = tracker.load_history()
    for scan in reversed(history):
        companies = scan.get('new_companies')
        if companies:
            return companies
    return []


def notify_subscribers(new_jobs: list) -> dict:
    if not new_jobs:
        return {'success': True, 'sent': 0}

    subscriptions = tracker.get_all_subscriptions()
    if not subscriptions:
        return {'success': True, 'sent': 0}

    jobs_by_company = {}
    for job in new_jobs:
        company = (job.get('company') or 'Unbekannt').strip()
        jobs_by_company.setdefault(company.lower(), []).append(job)

    sent_count = 0
    errors = []

    for sub in subscriptions:
        selected_companies = [c.strip().lower() for c in sub.get('companies', []) if c.strip()]
        relevant_jobs = []
        for company_key, jobs in jobs_by_company.items():
            if company_key in selected_companies:
                relevant_jobs.extend(jobs)

        if not relevant_jobs:
            continue

        company_names = sorted({job.get('company') or 'Unbekannt' for job in relevant_jobs})
        subject = f"Neue Internship-Positionen: {', '.join(company_names)}"
        first_name = sub.get('first_name', '').strip()
        greeting = f"Hallo {first_name}," if first_name else "Hallo,"
        lines = [greeting, "", "Es wurden neue Internship-Stellen veröffentlicht, die zu deinen Abonnements passen:", ""]
        for job in relevant_jobs:
            lines.append(f"• {job.get('title', 'Unbenannter Internship')} bei {job.get('company', 'Unbekannt')}")
            if job.get('location'):
                lines.append(f"  Standort: {job.get('location')}")
            if job.get('published_date'):
                lines.append(f"  Veröffentlicht: {job.get('published_date')}")
            if job.get('link'):
                lines.append(f"  Link: {job.get('link')}")
            lines.append("")
        lines.append("Viele Grüße,\nDein Internship Tracker")

        body = '\n'.join(lines)
        result = send_email(sub.get('email'), subject, body)
        if result['success']:
            sent_count += 1
        else:
            errors.append({'email': sub.get('email'), 'error': result.get('error')})

    return {'success': len(errors) == 0, 'sent': sent_count, 'errors': errors}


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    """Zeigt das Dashboard mit allen Stellen"""
    all_jobs = tracker.get_all_jobs()
    jobs = all_jobs
    company_options = sorted({job.get('company', 'Unbekannt') or 'Unbekannt' for job in all_jobs})

    subscribe_message = None
    subscribe_error = None
    selected_companies = []

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        selected_companies = request.form.getlist('companies')
        if not first_name or not last_name:
            subscribe_error = 'Bitte gib deinen Vor- und Nachnamen ein.'
        elif not email:
            subscribe_error = 'Bitte gib eine gültige E-Mail-Adresse ein.'
        elif not selected_companies:
            subscribe_error = 'Wähle mindestens ein Unternehmen aus.'
        else:
            tracker.add_subscription(email, selected_companies, first_name=first_name, last_name=last_name)
            subscribe_message = f'Danke, {first_name}! Deine E-Mail-Benachrichtigungen wurden gespeichert.'
            selected_companies = []

    history = tracker.load_history()
    source_config = load_source_config()
    new_companies = get_new_company_notice()
    tracked_sources = [source.get('name') or source.get('url') for source in source_config if source.get('enabled', True)]

    jobs_by_company = {}
    for job in jobs:
        company = job.get('company') or 'Unbekannt'
        # Fallback: regex-Extraktion wenn kein gespeichertes period-Feld
        if not job.get('period'):
            job['period'] = extract_period(job.get('title', ''))
        jobs_by_company.setdefault(company, []).append(job)
    jobs_by_company = {
        company: sorted(company_jobs, key=lambda j: period_sort_key(j.get('period', '')))
        for company, company_jobs in sorted(jobs_by_company.items())
    }

    return render_template('dashboard.html',
                         jobs=jobs,
                         jobs_by_company=jobs_by_company,
                         company_options=company_options,
                         total_jobs=len(jobs),
                         history=history[-5:] if history else [],
                         tracked_sources=tracked_sources,
                         new_companies=new_companies,
                         subscribe_message=subscribe_message,
                         subscribe_error=subscribe_error,
                         selected_companies=selected_companies)

@app.route('/add', methods=['GET', 'POST'])
def add_source():
    """Fügt eine neue Karriereseite hinzu und scanned diese"""
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        
        if not url:
            return render_template('add_job.html', error="URL ist erforderlich")
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            screenshot_result = extractor.capture_screenshot_via_api(url)
            if not screenshot_result.get('success'):
                return render_template('add_job.html', error=f"Fehler beim Screenshot: {screenshot_result.get('error')}")
            screenshot_data = screenshot_result.get('screenshot')
            result = extractor.extract_from_screenshot(screenshot_data, url)
            
            if not result['success']:
                return render_template('add_job.html', error=f"Fehler beim Extrahieren: {result.get('error')}")
            
            # Verarbeite die neuen Jobs
            new_jobs = result.get('jobs', [])
            processed_jobs, summary = tracker.process_new_jobs(new_jobs, url)

            # Titel bereinigen (Städte/Länder entfernen)
            processed_jobs = extractor.clean_job_titles(processed_jobs)

            # Zeiträume normalisieren (Q1/26, Q3/27 etc.)
            processed_jobs = extractor.normalize_job_periods(processed_jobs)

            # Merge mit bestehenden Jobs
            tracker.merge_jobs(processed_jobs)

            # Detail-Links via Playwright + Claude extrahieren und speichern
            link_map = extractor.extract_detail_links(url, processed_jobs)
            tracker.update_job_links(link_map)

            # Fallback: Source-URL für Jobs ohne Link
            tracker.apply_source_url_fallback(url, processed_jobs)

            # Füge zur Geschichte hinzu
            tracker.add_to_history(summary)

            # Sende E-Mail-Benachrichtigungen für neue Jobs
            new_jobs_for_notifications = [job for job in processed_jobs if job.get('first_seen') == datetime.now().strftime('%Y-%m-%d')]
            notification_result = notify_subscribers(new_jobs_for_notifications)

            return render_template('add_job.html',
                                 success=True,
                                 summary=summary,
                                 jobs_found=len(processed_jobs),
                                 notification_result=notification_result)
        
        except requests.RequestException as e:
            return render_template('add_job.html', error=f"Netzwerkfehler: {str(e)}")
        except Exception as e:
            return render_template('add_job.html', error=f"Fehler: {str(e)}")
    
    return render_template('add_job.html')

@app.route('/api/jobs')
def api_jobs():
    """API-Endpoint für alle Jobs als JSON"""
    jobs = tracker.get_all_jobs()
    return jsonify(jobs)

@app.route('/api/jobs/<company>')
def api_jobs_by_company(company):
    """API-Endpoint für Jobs eines Unternehmens"""
    jobs = tracker.get_jobs_by_company(company)
    return jsonify(jobs)

@app.route('/stats')
def stats():
    """Zeigt Statistiken"""
    jobs = tracker.load_current_jobs()
    history = tracker.load_history()
    
    stats_data = {
        'total_jobs': len(jobs),
        'total_scans': len(history),
        'companies': len(set(job.get('company') for job in jobs)),
        'today_new': len([j for j in jobs if j.get('first_seen') == datetime.now().strftime('%Y-%m-%d')]),
    }
    
    return render_template('stats.html', 
                         stats=stats_data,
                         history=history[-10:] if history else [])

@app.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    companies = sorted({job.get('company', 'Unbekannt') or 'Unbekannt' for job in tracker.get_all_jobs()})
    message = None
    error = None
    selected_companies = []

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        selected_companies = request.form.getlist('companies')

        if not email:
            error = 'Bitte gib eine gültige E-Mail-Adresse ein.'
        elif not selected_companies:
            error = 'Wähle mindestens ein Unternehmen aus, für das du Benachrichtigungen erhalten möchtest.'
        else:
            tracker.add_subscription(email, selected_companies)
            message = 'Danke! Deine E-Mail-Benachrichtigungen wurden gespeichert.'

    return render_template('subscribe.html', companies=companies, message=message, error=error, selected_companies=selected_companies)

@app.route('/impressum')
def imprint():
    return render_template('imprint.html')

@app.route('/datenschutz')
def privacy():
    return render_template('privacy.html')

@app.route('/agb')
def terms():
    return render_template('terms.html')

def scan_all_sources() -> dict:
    """
    Scannt alle aktivierten Quellen aus config_sources.json,
    sammelt neue Stellen und sendet eine konsolidierte E-Mail an Abonnenten.
    """
    sources = load_source_config()
    enabled = [s for s in sources if s.get('enabled', True)]
    today = datetime.now().strftime('%Y-%m-%d')
    all_new_jobs = []

    for source in enabled:
        url = source.get('url', '')
        if not url:
            continue
        try:
            screenshot_result = extractor.capture_screenshot_via_api(url)
            if not screenshot_result.get('success'):
                continue
            result = extractor.extract_from_screenshot(screenshot_result['screenshot'], url)
            if not result.get('success'):
                continue

            new_jobs = result.get('jobs', [])
            processed_jobs, summary = tracker.process_new_jobs(new_jobs, url)
            processed_jobs = extractor.clean_job_titles(processed_jobs)
            processed_jobs = extractor.normalize_job_periods(processed_jobs)
            tracker.merge_jobs(processed_jobs)
            link_map = extractor.extract_detail_links(url, processed_jobs)
            tracker.update_job_links(link_map)
            tracker.apply_source_url_fallback(url, processed_jobs)
            tracker.add_to_history(summary)

            # Nur wirklich neue Stellen (first_seen = heute und noch nicht benachrichtigt)
            for job in processed_jobs:
                if job.get('first_seen') == today and not job.get('notified'):
                    all_new_jobs.append(job)
        except Exception:
            continue

    # Neue Jobs als benachrichtigt markieren
    if all_new_jobs:
        notified_ids = {j.get('job_id') for j in all_new_jobs}
        all_jobs = tracker.load_current_jobs()
        for job in all_jobs:
            if job.get('job_id') in notified_ids:
                job['notified'] = True
        with open(tracker.jobs_file, 'w', encoding='utf-8') as f:
            json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    notification_result = notify_subscribers(all_new_jobs)
    return {'sources_scanned': len(enabled), 'new_jobs': len(all_new_jobs), 'notifications': notification_result}


@app.route('/test-email')
def test_email():
    """Sendet eine Test-E-Mail mit allen heutigen neuen Stellen an alle Abonnenten."""
    today = datetime.now().strftime('%Y-%m-%d')
    subs = tracker.get_all_subscriptions()
    if not subs:
        return jsonify({'error': 'Keine Abonnenten vorhanden'})

    # Alle abonnierten Unternehmen ermitteln
    all_companies = {c.lower() for sub in subs for c in sub.get('companies', [])}

    # Heutige Jobs dieser Unternehmen als Test-Jobs verwenden
    test_jobs = [
        j for j in tracker.get_all_jobs()
        if (j.get('company') or '').lower() in all_companies
    ][:5]  # Max 5 für den Test

    if not test_jobs:
        # Fallback: einen Dummy-Job
        test_jobs = [{
            'title': 'Test: Investment Banking Internship',
            'company': list(all_companies)[0].title(),
            'location': 'Frankfurt',
            'published_date': today,
            'link': 'https://example.com/test-job',
        }]

    result = notify_subscribers(test_jobs)
    return jsonify({'jobs_sent': len(test_jobs), 'result': result})


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Seite nicht gefunden"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Interner Fehler"), 500

if __name__ == '__main__':
    scheduler = BackgroundScheduler(timezone='Europe/Berlin')
    scheduler.add_job(scan_all_sources, 'cron', hour=20, minute=0)
    scheduler.start()
    app.run(debug=False, host='127.0.0.1', port=8000)

"""Flask-Anwendung für Internship Tracker"""
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
from email.message import EmailMessage
import json
import os
import smtplib
import ssl
import requests
from config import Config
from tracker import InternshipTracker
from claude_api import InternshipExtractor

app = Flask(__name__)
app.config.from_object(Config)

tracker = InternshipTracker()
extractor = InternshipExtractor()


def send_email(to_address: str, subject: str, body: str) -> dict:
    if not app.config['EMAIL_ENABLED']:
        return {'success': False, 'error': 'E-Mail-Versand deaktiviert'}

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = app.config['EMAIL_FROM']
    msg['To'] = to_address
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'], timeout=20) as server:
            server.starttls(context=context)
            if app.config['SMTP_USER'] and app.config['SMTP_PASSWORD']:
                server.login(app.config['SMTP_USER'], app.config['SMTP_PASSWORD'])
            server.send_message(msg)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


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
        lines = [f"Hallo,", "", "Es wurden neue Internship-Stellen veröffentlicht, die zu deinen Abonnements passen:", ""]
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


@app.route('/')
def dashboard():
    """Zeigt das Dashboard mit allen Stellen"""
    all_jobs = tracker.get_all_jobs()
    
    jobs = all_jobs
    company_options = sorted({job.get('company', 'Unbekannt') or 'Unbekannt' for job in all_jobs})

    # Lade auch die Historie für Statistiken
    history = tracker.load_history()
    source_config = load_source_config()
    new_companies = get_new_company_notice()
    tracked_sources = [source.get('name') or source.get('url') for source in source_config if source.get('enabled', True)]
    
    return render_template('dashboard.html',
                         jobs=jobs,
                         company_options=company_options,
                         total_jobs=len(jobs),
                         history=history[-5:] if history else [],
                         tracked_sources=tracked_sources,
                         new_companies=new_companies)

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
            
            # Merge mit bestehenden Jobs
            tracker.merge_jobs(processed_jobs)
            
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

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Seite nicht gefunden"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Interner Fehler"), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8000)

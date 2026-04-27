import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Flask-Konfiguration"""
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Anthropic Claude API
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

    # Screenshot API
    SCREENSHOT_API_KEY = os.getenv('SCREENSHOT_API_KEY')
    SCREENSHOT_API_BASE = os.getenv('SCREENSHOT_API_BASE', 'https://shot.screenshotapi.net/v3/screenshot')

    # SMTP / E-Mail
    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    EMAIL_FROM = os.getenv('EMAIL_FROM', 'no-reply@example.com')
    EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'

    # Datenspeicherung
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    JOBS_FILE = os.path.join(DATA_DIR, 'internships.json')
    HISTORY_FILE = os.path.join(DATA_DIR, 'history.json')
    SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, 'subscriptions.json')
    
    # Sicherstellen, dass data Verzeichnis existiert
    os.makedirs(DATA_DIR, exist_ok=True)

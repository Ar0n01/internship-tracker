"""Claude API Integration für die Extraktion von Stelleninformationen"""
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urljoin
from anthropic import Anthropic
from playwright.sync_api import sync_playwright, TimeoutError
from config import Config

class InternshipExtractor:
    """Extrahiert Stelleninformationen von Webseiten mittels Claude API"""
    
    def __init__(self):
        self.client = Anthropic()
        self.model = "claude-haiku-4-5-20251001"
    
    def extract_from_url(self, url: str) -> dict:
        """
        Extrahiert Stelleninformationen von einer URL mittels Claude Vision
        
        Args:
            url: URL der Karriereseite
            
        Returns:
            Dictionary mit extrahierten Informationen
        """
        prompt = """
Analysiere diese Karriereseite und extrahiere alle Praktikumsstellen als JSON.
Für jede Stelle extrahiere:
- title: Stellenbezeichnung
- company: Unternehmen
- location: Standort
- description: Kurze Beschreibung
- link: Link zur Stelle (falls vorhanden)
- posted_date: Veröffentlichungsdatum (falls angegeben, sonst null)

WICHTIG: Antworte NUR mit einem gültigen JSON-Array. Kein zusätzlicher Text, keine Erklärungen, nur das JSON-Array.

Beispiel Format:
[{"title": "Data Science Internship", "company": "TechCorp", "location": "Berlin", "description": "Arbeite an ML Projekten...", "link": "https://...", "posted_date": "2025-01-15"}]
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"URL: {url}\n\n{prompt}"
                            }
                        ]
                    }
                ]
            )
            
            # Extrahiere JSON aus der Antwort
            response_text = message.content[0].text.strip()
            
            # Versuche, JSON direkt zu parsen
            try:
                jobs = json.loads(response_text)
                return {"success": True, "jobs": jobs, "url": url}
            except json.JSONDecodeError:
                # Fallback: Suche nach JSON in der Antwort
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    try:
                        jobs = json.loads(json_str)
                        return {"success": True, "jobs": jobs, "url": url}
                    except json.JSONDecodeError as e:
                        return {"success": False, "error": f"JSON-Parse-Fehler nach Extraktion: {str(e)}", "url": url}
                else:
                    return {"success": False, "error": f"Kein JSON-Array in der Antwort gefunden. Antwort: {response_text[:200]}...", "url": url}
                
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON-Parse-Fehler: {str(e)}", "url": url}
        except Exception as e:
            return {"success": False, "error": f"API-Fehler: {str(e)}", "url": url}
    
    def extract_from_url_with_browser(self, url: str, wait_time: int = 5000) -> dict:
        """
        Extrahiert Stelleninformationen von einer URL mittels Browser-Automation oder Screenshot für Workday
        
        Args:
            url: URL der Karriereseite
            wait_time: Wartezeit in ms für JavaScript-Loading
            
        Returns:
            Dictionary mit extrahierten Informationen
        """
        # Für Workday-Seiten Screenshot-API verwenden, falls verfügbar
        if ('workday' in url.lower() or 'wd1.myworkdayjobs.com' in url or 'wd3.myworkdayjobs.com' in url) and Config.SCREENSHOT_API_KEY:
            screenshot_result = self.capture_screenshot_via_api(url, wait_time)
            if screenshot_result['success']:
                return self.extract_from_screenshot(screenshot_result['screenshot'], url)
            else:
                # Fallback zu Browser-Automation
                pass
        
        # Browser-Automation für Workday oder andere Seiten
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Setze einen realistischen User-Agent
                page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
                
                print(f"Loading page: {url}")
                workday_response = None

                def capture_jobs_response(response):
                    if "/jobs" in response.url and response.request.method == "POST":
                        nonlocal workday_response
                        workday_response = response

                page.on("response", capture_jobs_response)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Warte auf JavaScript-Loading und eventuelle /jobs-Requests
                page.wait_for_timeout(wait_time)

                # Scrolle nach unten um lazy-loading zu triggern
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                html_content = page.content()
                
                if workday_response is not None:
                    try:
                        data = workday_response.json()
                        jobs = self._parse_workday_jobs(data, url)
                        browser.close()
                        if jobs:
                            return {"success": True, "jobs": jobs, "url": url}
                    except Exception:
                        pass

                browser.close()
                print(f"Page loaded successfully. Content length: {len(html_content)}")
                
                # Jetzt Claude mit dem vollständigen HTML füttern
                return self.extract_from_html_content(html_content, url)
                
        except Exception as e:
            return {"success": False, "error": f"Browser-Automation-Fehler: {str(e)}", "url": url}

    def capture_screenshot_via_api(self, url: str, wait_time: int = 5000) -> dict:
        """Erstellt einen Screenshot der Seite mit screenshotapi.net."""
        if not Config.SCREENSHOT_API_KEY:
            return {"success": False, "error": "Screenshot API key nicht gesetzt", "url": url}

        params = {
            'token': Config.SCREENSHOT_API_KEY,
            'url': url,
            'output': 'image',
            'file_type': 'png',
            'full_page': 'true',
            'fresh': 'true',
            'lazy_load': 'true',
            'wait_for_event': 'networkidle',
            'delay': str(wait_time),
        }

        try:
            response = requests.get(Config.SCREENSHOT_API_BASE, params=params, timeout=60)
            response.raise_for_status()
            
            # Base64 encode the image
            screenshot_b64 = base64.b64encode(response.content).decode('utf-8')
            return {"success": True, "screenshot": screenshot_b64, "url": url}
        except Exception as e:
            return {"success": False, "error": f"Screenshot API-Fehler: {str(e)}", "url": url}

    def extract_from_screenshot(self, screenshot_b64: str, url: str = None) -> dict:
        """
        Extrahiert Stelleninformationen aus einem Screenshot mittels Claude Vision
        
        Args:
            screenshot_b64: Base64-encoded screenshot
            url: Optional: URL für Kontext
            
        Returns:
            Dictionary mit extrahierten Informationen
        """
        prompt = """
Analysiere diesen Screenshot einer Karriereseite und extrahiere alle Praktikumsstellen als JSON.
Für jede Stelle extrahiere:
- title: Stellenbezeichnung
- company: Unternehmen (falls nicht offensichtlich, versuche aus der Seite zu extrahieren)
- location: Standort
- description: Kurze Beschreibung oder Anforderungen
- link: Link zur Stelle (falls vorhanden)
- posted_date: Veröffentlichungsdatum (falls angegeben, sonst null)

WICHTIG: Antworte NUR mit einem gültigen JSON-Array. Kein zusätzlicher Text, keine Erklärungen, nur das JSON-Array.

Beispiel Format:
[{"title": "Data Science Internship", "company": "TechCorp", "location": "Berlin", "description": "Arbeite an ML Projekten...", "link": "https://...", "posted_date": "2025-01-15"}]
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Screenshot-Analyse für: {url or 'unbekannte Seite'}\n\n{prompt}"
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64
                                }
                            }
                        ]
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            # Versuche, JSON direkt zu parsen
            try:
                jobs = json.loads(response_text)
                return {"success": True, "jobs": jobs, "url": url}
            except json.JSONDecodeError:
                # Fallback: Suche nach JSON in der Antwort
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    try:
                        jobs = json.loads(json_str)
                        return {"success": True, "jobs": jobs, "url": url}
                    except json.JSONDecodeError as e:
                        return {"success": False, "error": f"JSON-Parse-Fehler nach Extraktion: {str(e)}", "url": url}
                else:
                    return {"success": False, "error": f"Kein JSON-Array in der Antwort gefunden. Antwort: {response_text[:200]}...", "url": url}
                
        except Exception as e:
            return {"success": False, "error": f"API-Fehler: {str(e)}", "url": url}

    def _parse_workday_jobs(self, data: dict, url: str) -> list:
        """Parsed Workday job postings aus dem /jobs-Response."""
        job_postings = []

        # Workday API structures vary; suche nach bekannten Feldern
        if isinstance(data, dict):
            if 'jobPostings' in data:
                job_postings = data.get('jobPostings') or []
            elif 'jobs' in data:
                job_postings = data.get('jobs') or []
            elif 'jobPostings' in data.get('data', {}):
                job_postings = data.get('data', {}).get('jobPostings') or []
            else:
                # Fallback: prüfe auf ein tiefer verschachteltes Array
                for value in data.values():
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        job_postings = value
                        break

        parsed = []
        for item in job_postings:
            title = item.get('title') or item.get('jobTitle') or item.get('positionTitle')
            location = item.get('locationsText') or item.get('location') or item.get('locations')
            posted = item.get('postedOn') or item.get('posted_date') or item.get('posted') or item.get('publishDate')
            external_path = item.get('externalPath') or item.get('external_path') or item.get('jobPostingUrl') or ''
            link = urljoin(url, external_path) if external_path else url
            parsed.append({
                'title': title,
                'company': item.get('company') or 'Workday Employer',
                'location': location,
                'description': item.get('description') or item.get('summary') or '',
                'link': link,
                'posted_date': posted,
            })
        return parsed

    def extract_from_html_content(self, html_content: str, url: str = None) -> dict:
        """
        Extrahiert Stelleninformationen aus HTML-Inhalt
        
        Args:
            html_content: HTML-Inhalt der Seite
            url: Optional: URL für Kontext
            
        Returns:
            Dictionary mit extrahierten Informationen
        """
        prompt = """
Analysiere diesen HTML-Inhalt einer Karriereseite und extrahiere alle Praktikumsstellen als JSON.
Für jede Stelle extrahiere:
- title: Stellenbezeichnung
- company: Unternehmen (falls nicht offensichtlich, versuche aus der Seite zu extrahieren)
- location: Standort
- description: Kurze Beschreibung oder Anforderungen
- link: Link zur Stelle (falls vorhanden)
- posted_date: Veröffentlichungsdatum (falls angegeben, sonst null)

WICHTIG: Antworte NUR mit einem gültigen JSON-Array. Kein zusätzlicher Text, keine Erklärungen, nur das JSON-Array.

Beispiel Format:
[{"title": "Data Science Internship", "company": "TechCorp", "location": "Berlin", "description": "Arbeite an ML Projekten...", "link": "https://...", "posted_date": "2025-01-15"}]
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"HTML-Inhaltsanalyse für: {url or 'unbekannte Seite'}\n\n{prompt}\n\nHTML:\n{html_content[:8000]}"
                            }
                        ]
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            try:
                jobs = json.loads(response_text)
                return {"success": True, "jobs": jobs, "url": url}
            except json.JSONDecodeError:
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    try:
                        jobs = json.loads(json_str)
                        return {"success": True, "jobs": jobs, "url": url}
                    except json.JSONDecodeError as e:
                        return {"success": False, "error": f"JSON-Parse-Fehler nach Extraktion: {str(e)}", "url": url}
                else:
                    return {"success": False, "error": f"Kein JSON-Array in der Antwort gefunden. Antwort: {response_text[:200]}...", "url": url}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON-Parse-Fehler: {str(e)}", "url": url}
        except Exception as e:
            return {"success": False, "error": f"API-Fehler: {str(e)}", "url": url}

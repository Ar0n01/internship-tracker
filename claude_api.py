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

    def _fetch_rendered(self, url: str, expected_terms: list = None) -> str:
        """Fetcht eine Seite; fällt auf Playwright zurück wenn JS-Rendering nötig ist."""
        try:
            r = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            html = r.text
            if expected_terms and not any(t.lower() in html.lower() for t in expected_terms):
                raise ValueError("Seite benötigt JS-Rendering")
            return html[:15000]
        except Exception:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(3000)
                    html = page.content()
                    browser.close()
                    return html[:15000]
            except Exception as e:
                return f"Fehler beim Abrufen: {e}"

    def _intercept_xhr_jobs(self, url: str) -> list:
        """
        Lädt die Seite mit Playwright und fängt XHR-Responses ab,
        die Job-Daten mit IDs enthalten. Gibt eine Liste von
        {title, detail_url} zurück.
        """
        captured = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                def on_response(response):
                    ct = response.headers.get('content-type', '')
                    if 'json' not in ct:
                        return
                    try:
                        data = response.json()
                        # Taleo-Struktur: requisitionList mit jobId
                        items = None
                        if isinstance(data, dict):
                            items = data.get('requisitionList') or data.get('jobs') or data.get('jobPostings')
                        if not items:
                            return
                        base_detail = url.split('jobsearch')[0] if 'jobsearch' in url else url.rsplit('/', 1)[0] + '/'
                        for item in items:
                            job_id = str(item.get('jobId') or item.get('id') or '')
                            cols = item.get('column', [])
                            title = cols[0] if cols else item.get('title', '')
                            if job_id and title:
                                # Taleo detail URL pattern
                                if 'taleo' in url:
                                    detail = url.replace('jobsearch.ftl', 'jobdetail.ftl').split('?')[0] + f'?job={job_id}&lang=en'
                                else:
                                    detail = urljoin(url, f'jobdetail?id={job_id}')
                                captured.append({'title': title.strip(), 'detail_url': detail})
                    except Exception:
                        pass

                page.on('response', on_response)
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(4000)
                browser.close()
        except Exception:
            pass
        return captured

    def extract_detail_links(self, url: str, jobs: list) -> dict:
        """
        Extrahiert individuelle Job-Detail-Links.
        Strategie 1: XHR-Interceptor (für SPAs wie Taleo).
        Strategie 2: Claude Tool-Use mit gerenderten HTML-Inhalten.
        Returns: {job_id: detail_url}
        """
        if not jobs:
            return {}

        titles = [j.get('title', '') for j in jobs if j.get('title')]

        # Strategie 1: XHR-Interceptor
        xhr_results = self._intercept_xhr_jobs(url)
        if xhr_results:
            result = {}
            for job in jobs:
                job_title = job.get('title', '').strip()
                job_id = job.get('job_id', '')
                for xhr in xhr_results:
                    if xhr['title'].lower() == job_title.lower():
                        result[job_id] = xhr['detail_url']
                        break
            if result:
                return result

        # Strategie 2: Claude Tool-Use mit fetch_page
        tools = [
            {
                "name": "fetch_page",
                "description": "Ruft den HTML-Inhalt einer Webseite ab.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Die URL der abzurufenden Seite"}
                    },
                    "required": ["url"]
                }
            }
        ]

        messages = [
            {
                "role": "user",
                "content": (
                    f"Extrahiere die direkten Detail-Links für folgende Stellenangebote "
                    f"von der Karriereseite {url}:\n{json.dumps(titles, ensure_ascii=False)}\n\n"
                    f"Nutze das fetch_page-Tool um die Seite abzurufen. "
                    f"Antworte danach NUR mit einem JSON-Objekt {{\"Stellentitel\": \"https://...\"}}. "
                    f"Nicht gefundene Links auf null setzen. URLs müssen absolut und vollständig sein."
                )
            }
        ]

        try:
            for _ in range(5):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    tools=tools,
                    messages=messages
                )

                if response.stop_reason == 'tool_use':
                    tool_block = next(b for b in response.content if b.type == 'tool_use')
                    fetch_url = tool_block.input.get('url', url)
                    page_content = self._fetch_rendered(fetch_url, titles)
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_block.id, "content": page_content}]
                    })
                else:
                    text = next((b.text for b in response.content if hasattr(b, 'text')), '')
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start != -1 and end > start:
                        link_map_by_title = json.loads(text[start:end])
                        result = {}
                        for job in jobs:
                            title = job.get('title', '')
                            job_id = job.get('job_id', '')
                            if title in link_map_by_title and link_map_by_title[title]:
                                result[job_id] = link_map_by_title[title]
                        return result
                    break
        except Exception:
            pass
        return {}

    def normalize_job_periods(self, jobs: list) -> list:
        """
        Normalisiert Zeitangaben in Stellentiteln zu standardisierten Quartalsformaten.
        Monatsmapping: Jan-Mar=Q1, Apr-Jun=Q2, Jul-Sep=Q3, Oct-Dec=Q4.
        Speichert das Ergebnis als 'period'-Feld direkt am Job.
        """
        if not jobs:
            return jobs

        titles = [j.get('title', '') for j in jobs]

        prompt = f"""Extrahiere den Praktikumszeitraum aus jedem Stellentitel und konvertiere ihn in das Format "Q[1-4]/[JJ]".

Regeln:
- Monate → Quartal: Jan/Feb/Mar=Q1, Apr/Mai/Jun=Q2, Jul/Aug/Sep=Q3, Okt/Nov/Dez=Q4
- Englische Monate: Jan/Feb/Mar=Q1, Apr/May/Jun=Q2, Jul/Aug/Sep=Q3, Oct/Nov/Dec=Q4
- Jahreszeiten: Spring=Q1/Q2, Summer=Q2/Q3, Autumn/Fall=Q3/Q4, Winter=Q4/Q1
- H1=Q1/Q2, H2=Q3/Q4
- Zeitraum-Ranges (z.B. "July - September"): nehme das Startquartal
- Nur Jahr ohne Monat: einfach das Jahr zurückgeben (z.B. "2026")
- Mehrere Quartale als kommagetrennte Liste: "Q3/26, Q4/26"
- Kein Zeitraum erkennbar: leerer String ""
- Jahreszahl immer zweistellig: 2026→26, 2027→27

Antworte NUR mit JSON-Array:
[{{"title": "...", "period": "Q3/26"}}]

Titel:
{json.dumps(titles, ensure_ascii=False)}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = message.content[0].text.strip()
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                pairs = json.loads(text[start:end])
                period_map = {p['title']: p.get('period', '') for p in pairs}
                for job in jobs:
                    title = job.get('title', '')
                    if title in period_map:
                        job['period'] = period_map[title]
        except Exception:
            pass

        return jobs

    def clean_job_titles(self, jobs: list) -> list:
        """
        Bereinigt Job-Titel: Entfernt Städte- und Ländernamen die bereits
        im Standort-Feld stehen. Gibt die Jobs mit bereinigten Titeln zurück.
        """
        if not jobs:
            return jobs

        pairs = [{"title": j.get("title", ""), "location": j.get("location", "")} for j in jobs]

        prompt = f"""Bereinige diese Stellentitel: Entferne alle Städte- und Ländernamen aus dem Titel,
da der Standort bereits separat gespeichert wird. Alles andere bleibt unverändert.

Typische Muster die entfernt werden sollen:
- Führende Präfixe wie "Germany - Frankfurt - " oder "Germany - "
- Klammern mit Städten am Ende: "(Munich)", "(Frankfurt)"
- Städtenamen nach Komma am Ende: "- Consumer, Munich" → "- Consumer"
- Städtenamen nach Bindestrich: "- Frankfurt, Equity Capital Markets" → "- Equity Capital Markets"
- Städtenamen nach Em-Dash: "– Frankfurt, M&A" → "– M&A"

Antworte NUR mit einem JSON-Array im Format:
[{{"original": "...", "cleaned": "..."}}]

Titel und Standorte:
{json.dumps(pairs, ensure_ascii=False)}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = message.content[0].text.strip()
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                cleaned_pairs = json.loads(text[start:end])
                title_map = {p["original"]: p["cleaned"] for p in cleaned_pairs if p.get("cleaned")}
                for job in jobs:
                    original = job.get("title", "")
                    if original in title_map:
                        job["title"] = title_map[original]
        except Exception:
            pass

        return jobs

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

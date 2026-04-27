#!/usr/bin/env python3
"""
Automatisches Scan-Script für Cron-Jobs
Scanned alle konfigurierten Karriereseiten und speichert neue Stellen
"""
import sys
import os
import json
from datetime import datetime

# Füge das Parent-Verzeichnis zum Pythonpath hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import InternshipTracker
from claude_api import InternshipExtractor
import requests

def load_sources_config():
    """Lädt die Liste der zu scannenden Seiten"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config_sources.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sources_config(sources):
    """Speichert die Liste der zu scannenden Seiten"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config_sources.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)

def scan_sources():
    """Scanned alle konfigurierten Quellen"""
    tracker = InternshipTracker()
    extractor = InternshipExtractor()
    sources = load_sources_config()
    
    print(f"[{datetime.now()}] Starte Scan mit {len(sources)} Quelle(n)")
    
    if not sources:
        print("Keine Quellen konfiguriert. Benutzen Sie die Web-App um Quellen hinzuzufügen.")
        return
    
    for source in sources:
        url = source.get('url')
        enabled = source.get('enabled', True)
        
        if not enabled:
            print(f"[SKIP] {url} (deaktiviert)")
            continue
        
        print(f"[SCAN] {url}")
        
        try:
            # Fetch HTML-Inhalt
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            # Extrahiere Jobs
            result = extractor.extract_from_html_content(response.text, url)
            
            if not result['success']:
                print(f"  ❌ Fehler: {result.get('error')}")
                continue
            
            # Verarbeite neue Jobs
            new_jobs = result.get('jobs', [])
            processed_jobs, summary = tracker.process_new_jobs(new_jobs, url)
            
            # Merge mit bestehenden Jobs
            tracker.merge_jobs(processed_jobs)
            
            # Speichere in Historie
            tracker.add_to_history(summary)
            
            print(f"  ✅ {summary['processed']} Stellen verarbeitet (neu: {summary['new']}, unverändert: {summary['unchanged']})")
        
        except requests.RequestException as e:
            print(f"  ❌ Netzwerkfehler: {str(e)}")
        except Exception as e:
            print(f"  ❌ Fehler: {str(e)}")
    
    print(f"[{datetime.now()}] Scan abgeschlossen")

if __name__ == '__main__':
    scan_sources()

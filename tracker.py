"""Tracking und Versionierung von Stelleninformationen"""
import json
import os
from datetime import datetime
from typing import List, Dict, Tuple
from config import Config

class InternshipTracker:
    """Verwaltet Internships und deren Versionierung mit Publikationsdatum-Tracking"""
    
    def __init__(self):
        self.jobs_file = Config.JOBS_FILE
        self.history_file = Config.HISTORY_FILE
        self.subscriptions_file = Config.SUBSCRIPTIONS_FILE
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Erstellt JSON-Dateien, falls nicht vorhanden"""
        for file in [self.jobs_file, self.history_file, self.subscriptions_file]:
            if not os.path.exists(file):
                with open(file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
    
    def load_current_jobs(self) -> List[Dict]:
        """Lädt alle aktuellen Stellen"""
        try:
            with open(self.jobs_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    
    def load_history(self) -> List[Dict]:
        """Lädt die Scan-Historie"""
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def load_subscriptions(self) -> List[Dict]:
        """Lädt alle Newsletter-Abonnements"""
        try:
            with open(self.subscriptions_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def save_subscriptions(self, subscriptions: List[Dict]):
        """Speichert Newsletter-Abonnements"""
        with open(self.subscriptions_file, 'w', encoding='utf-8') as f:
            json.dump(subscriptions, f, ensure_ascii=False, indent=2)

    def add_subscription(self, email: str, companies: List[str]):
        """Legt ein neues Abonnement an oder aktualisiert das bestehende"""
        email = email.strip().lower()
        companies = sorted({company.strip() for company in companies if company.strip()})
        today = datetime.now().strftime('%Y-%m-%d')

        subscriptions = self.load_subscriptions()
        existing = next((item for item in subscriptions if item.get('email') == email), None)

        if existing:
            existing['companies'] = companies
            existing['updated_at'] = today
        else:
            subscriptions.append({
                'email': email,
                'companies': companies,
                'subscribed_at': today,
                'updated_at': today
            })

        self.save_subscriptions(subscriptions)

    def get_all_subscriptions(self) -> List[Dict]:
        """Gibt alle Abonnements zurück"""
        return self.load_subscriptions()

    def get_subscribers_for_company(self, company: str) -> List[Dict]:
        """Gibt alle Abonnenten zurück, die für ein bestimmtes Unternehmen benachrichtigt werden wollen"""
        company_key = (company or '').strip().lower()
        return [sub for sub in self.load_subscriptions() if any(c.strip().lower() == company_key for c in sub.get('companies', []))]

    def _create_job_id(self, job: Dict) -> str:
        """Erzeugt eine eindeutige ID für eine Stelle basierend auf Titel, Unternehmen und Location"""
        key = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('location', '')}"
        return key.lower().replace(' ', '_').replace('.', '')
    
    def _find_existing_job(self, job: Dict, existing_jobs: List[Dict]) -> Tuple[bool, Dict]:
        """
        Sucht eine gleiche Stelle in der bestehenden Liste
        
        Args:
            job: Neue Stelle
            existing_jobs: Bestehende Stellen
            
        Returns:
            (exists: bool, existing_job: dict)
        """
        job_id = self._create_job_id(job)
        for existing in existing_jobs:
            if self._create_job_id(existing) == job_id:
                return True, existing
        return False, {}
    
    def process_new_jobs(self, new_jobs: List[Dict], source_url: str) -> Tuple[List[Dict], Dict]:
        """
        Verarbeitet neue Jobs und wendet Versionierungs-Logik an
        
        LOGIK:
        1. Wenn Datum in neuer Stelle → verwende dieses Datum
        2. Wenn kein Datum und Stelle existiert noch nicht → setze heutiges Datum
        3. Wenn kein Datum und Stelle existiert → behalte altes Datum
        
        Args:
            new_jobs: Liste mit neuen Stellen
            source_url: URL der Quelle
            
        Returns:
            (processed_jobs, summary)
        """
        existing_jobs = self.load_current_jobs()
        history = self.load_history()
        
        today = datetime.now().strftime('%Y-%m-%d')
        processed_jobs = []
        summary = {
            'processed': 0,
            'new': 0,
            'updated': 0,
            'unchanged': 0,
            'source': source_url,
            'scan_date': today
        }
        
        for new_job in new_jobs:
            exists, existing_job = self._find_existing_job(new_job, existing_jobs)
            
            if exists:
                # Stelle existiert schon
                # Behalte das ursprüngliche Datum bei
                new_job['published_date'] = existing_job.get('published_date')
                new_job['first_seen'] = existing_job.get('first_seen')
                summary['unchanged'] += 1
            else:
                # Neue Stelle
                # Verwende das Datum aus der API, oder setze heutiges Datum
                new_job['published_date'] = new_job.get('posted_date') or today
                new_job['first_seen'] = today
                summary['new'] += 1
            
            # Füge Metadaten hinzu
            new_job['last_updated'] = today
            new_job['source'] = source_url
            new_job['job_id'] = self._create_job_id(new_job)
            
            processed_jobs.append(new_job)
            summary['processed'] += 1
        
        return processed_jobs, summary
    
    def merge_jobs(self, new_jobs: List[Dict], keep_unmatched: bool = True) -> Dict:
        """
        Merged neue Jobs mit bestehenden Jobs
        
        Args:
            new_jobs: Neu verarbeitete Jobs
            keep_unmatched: Behalte bestehende Jobs, die nicht in neuer Liste sind
            
        Returns:
            Dictionary mit Merge-Statistiken
        """
        existing_jobs = self.load_current_jobs()
        
        # Erstelle ein Dictionary für einfache Lookups
        new_jobs_dict = {job['job_id']: job for job in new_jobs}
        merged_jobs = []
        
        # Update existierende Jobs oder behalte sie
        for existing in existing_jobs:
            job_id = existing.get('job_id')
            if job_id in new_jobs_dict:
                # Update mit neuer Version
                merged_jobs.append(new_jobs_dict[job_id])
                del new_jobs_dict[job_id]  # Markiere als verarbeitet
            elif keep_unmatched:
                # Behalte alte Jobs, die nicht mehr gefunden wurden
                merged_jobs.append(existing)
        
        # Füge übrige neue Jobs hinzu
        merged_jobs.extend(new_jobs_dict.values())
        
        # Speichere
        with open(self.jobs_file, 'w', encoding='utf-8') as f:
            json.dump(merged_jobs, f, ensure_ascii=False, indent=2)
        
        return {
            'total_jobs': len(merged_jobs),
            'jobs_file': self.jobs_file
        }
    
    def add_to_history(self, summary: Dict):
        """Fügt einen Scan zur Historie hinzu"""
        history = self.load_history()
        history.append(summary)
        
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def get_all_jobs(self) -> List[Dict]:
        """Gibt alle aktuellen Jobs sortiert nach Veröffentlichungsdatum zurück"""
        jobs = self.load_current_jobs()
        # Sortiere nach published_date (neueste zuerst)
        return sorted(jobs, key=lambda x: x.get('published_date', '0000-00-00'), reverse=True)
    
    def get_jobs_by_company(self, company: str) -> List[Dict]:
        """Gibt alle Jobs eines Unternehmens zurück"""
        jobs = self.load_current_jobs()
        return [job for job in jobs if job.get('company', '').lower() == company.lower()]

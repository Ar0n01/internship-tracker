# 🎯 Internship Tracker

Ein automatisiertes System zur Verfolgung von Praktikumsstellen im Internet. Das System scannt Karriereseiten täglich, extrahiert Stelleninformationen mittels Claude AI und speichert sie mit automatischen Veröffentlichungsdatum-Tracking.

## 🚀 Features

- **Automatisches Scraping**: Täglich automatisierte Scans von konfigurierten Karriereseiten
- **Claude AI Integration**: Intelligente Extraktion von Stelleninformationen mittels Claude API
- **Intelligente Datumsverfolgung**:
  - Wenn ein Veröffentlichungsdatum auf der Seite angegeben ist, wird dieses verwendet
  - Für neue Stellen ohne Datum wird das heutige Datum als Veröffentlichungsdatum gespeichert
  - Bereits bekannte Stellen behalten ihr ursprüngliches Datum
- **Web-Dashboard**: Benutzerfreundliche Oberfläche zur Verwaltung und Anzeige
- **E-Mail-Newsletter**: Abonnements für neue Internship-Positionen nach Unternehmen
- **JSON-Speicherung**: Einfache, textbasierte Datenspeicherung
- **Cron-Job Integration**: Automatisierte tägliche Scans auf macOS/Linux

## 📋 Anforderungen

- Python 3.8+
- Flask
- Anthropic Claude API Schlüssel
- macOS oder Linux (für Cron-Jobs)

## 🔧 Installation

### 1. Repository klonen und Verzeichnis öffnen
```bash
cd Internship_Automation
```

### 2. Python-Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 3. `.env` Datei erstellen
Kopieren Sie `.env.example` zu `.env` und füllen Sie Ihre Claude API Schlüssel aus:
```bash
cp .env.example .env
# Bearbeiten Sie .env mit Ihrem API-Schlüssel
```

Erhalten Sie einen API-Schlüssel von: https://console.anthropic.com

## 🎯 Verwendung

### Web-Dashboard starten
```bash
python3 app.py
```
Das Dashboard ist dann unter `http://127.0.0.1:8000` erreichbar.

### Newsletter abonnieren
Öffne `http://127.0.0.1:8000/subscribe`, gib deine E-Mail-Adresse ein und wähle die Unternehmen aus, für die du Benachrichtigungen erhalten möchtest.

### Neue Karriereseite hinzufügen
1. Öffnen Sie das Dashboard
2. Klicken Sie auf "+ Neue Seite"
3. Geben Sie die URL der Karriereseite ein
4. Das System scanned die Seite und extrahiert alle Praktikumsstellen

### Automatische tägliche Scans (Cron-Job)

Installieren Sie den Cron-Job für automatisierte tägliche Scans um 08:00 Uhr:
```bash
chmod +x scripts/install_cron.sh
./scripts/install_cron.sh
```

So sieht ein manueller Cron-Job Eintrag aus:
```bash
0 8 * * * cd /path/to/Internship_Automation && python3 scripts/scan_jobs.py >> logs/scan.log 2>&1
```

Verwalten Sie Cron-Jobs mit:
```bash
crontab -l    # Zeige alle Cron-Jobs
crontab -e    # Bearbeite Cron-Jobs
crontab -r    # Lösche alle Cron-Jobs
```

## 📊 Dateistruktur

```
Internship_Automation/
├── app.py                    # Flask Hauptanwendung
├── config.py                 # Konfiguration
├── tracker.py                # Kernlogik für Stellenverfolgung
├── claude_api.py             # Claude API Integration
├── config_sources.json       # Liste der zu scannenden URLs
├── requirements.txt          # Python Abhängigkeiten
├── .env                      # Umgebungsvariablen (nicht ins Repo!)
├── .env.example              # Beispiel für .env
├── templates/                # HTML Templates
│   ├── base.html
│   ├── dashboard.html
│   ├── add_job.html
│   ├── stats.html
│   └── error.html
├── static/                   # CSS und Assets
│   └── style.css
├── scripts/
│   ├── scan_jobs.py          # Automatisches Scan-Script
│   └── install_cron.sh       # Cron-Installation
├── data/                     # Datenspeicherung
│   ├── internships.json      # Alle aktuellen Stellen
│   └── history.json          # Scan-Historie
└── logs/                     # Cron-Job Logs
    └── scan.log
```

## 🔍 Wie die Stellenverfolgung funktioniert

### Datumsverfolgung (Logik)

```
1. Beim Erhalt einer neuen Stelle von der API:
   ├─ Wenn Veröffentlichungsdatum vorhanden → Verwende dieses
   └─ Wenn E KEIN Datum → Setze heutiges Datum

2. Beim Vergleich mit bestehenden Stellen:
   ├─ Wenn Stelle bereits bekannt → Behalte altes Datum
   └─ Wenn Stelle neu → Markiere mit heutigen Datum
```

### Beispiel

**Tag 1** (15. Januar):
- Stelle "ML Engineer" wird gescannt
- Keine Datumsangabe auf Website
- Wird gespeichert mit Veröffentlichungsdatum: 15. Januar

**Tag 2** (16. Januar):
- Stelle "ML Engineer" wird erneut gefunden
- Alte Stelle wird erkannt (gleicher Titel, Firma, Standort)
- Behält Veröffentlichungsdatum: 15. Januar

**Tag 3** (17. Januar):
- Neue Stelle "Data Scientist" wird gescannt
- Wird gespeichert mit Veröffentlichungsdatum: 17. Januar

## 📡 API Endpoints

- `GET /` - Dashboard mit allen Stellen
- `GET /add` - Formular zum Hinzufügen neuer Quellen
- `POST /add` - Neue Quelle scannen
- `GET /stats` - Statistiken und Scan-Historie
- `GET /api/jobs` - Alle Jobs als JSON-API
- `GET /api/jobs/<company>` - Jobs eines Unternehmens

## 🛠️ Troubleshooting

### "ANTHROPIC_API_KEY nicht gefunden"
Stellen Sie sicher, dass Sie eine `.env` Datei mit Ihrem API-Schlüssel erstellt haben.

### "ModuleNotFoundError"
Führen Sie aus: `pip install -r requirements.txt`

### Cron-Job funktioniert nicht
- Prüfen Sie die Logs: `tail -f logs/scan.log`
- Stellen Sie sicher, dass das Python-Skript ausführbar ist: `chmod +x scripts/scan_jobs.py`
- Prüfen Sie den Cron-Status: `crontab -l`

## 📝 Beispiel: Unternehmenswebseite hinzufügen

1. Geben Sie in der Web-App ein: `https://example.com/careers`
2. Claude AI extrahiert automatisch:
   - Stellentitel
   - Standorte
   - Anforderungen/Beschreibungen
   - Links (falls vorhanden)
3. Neue Stellen werden mit dem heutigen Datum versehen
4. Die Historie wird aktualisiert

## 🔐 Sicherheit

- Speichern Sie `.env` mit sensiblen Daten NICHT in Version Control
- `.gitignore` schließt `.env` automatisch aus
- API-Schlüssel sollten mit Umgebungsvariablen verwaltet werden

## 📄 Lizenz

MIT License - siehe LICENSE Datei für Details

## 🤝 Beitragen

Gerne können Sie Verbesserungen vorschlagen oder Bugs melden!

---

Gebaut mit ❤️ für intelligente Stellensuche

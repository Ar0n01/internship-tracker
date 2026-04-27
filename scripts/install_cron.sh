#!/bin/bash
# Installiert einen Cron-Job für tägliches Scannen
# Verwendung: ./install_cron.sh

# Holen Sie das aktuelle Verzeichnis
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SCAN_SCRIPT="$SCRIPT_DIR/scan_jobs.py"

# Prüfe ob Python vorhanden ist
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 nicht gefunden. Bitte installieren Sie Python3."
    exit 1
fi

# Mache das Script ausführbar
chmod +x "$SCAN_SCRIPT"

# Bestimme den Cron-Ausdruck (täglich um 08:00 Uhr)
CRON_SCHEDULE="0 8 * * *"

# Erstelle den Cron-Job-Befehl
CRON_JOB="$CRON_SCHEDULE cd $PROJECT_DIR && python3 $SCAN_SCRIPT >> $PROJECT_DIR/logs/scan.log 2>&1"

# Erstelle das logs-Verzeichnis falls nicht vorhanden
mkdir -p "$PROJECT_DIR/logs"

# Installiere den Cron-Job
(crontab -l 2>/dev/null | grep -v "$SCAN_SCRIPT"; echo "$CRON_JOB") | crontab -

echo "✅ Cron-Job installiert!"
echo "Täglich um 08:00 Uhr wird die Seite gescannt."
echo ""
echo "Logs: $PROJECT_DIR/logs/scan.log"
echo ""
echo "Aktuelle Cron-Jobs:"
crontab -l

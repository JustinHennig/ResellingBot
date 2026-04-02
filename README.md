# ResellingBot — Kleinanzeigen Monitor

Überwacht Kleinanzeigen automatisch und sendet WhatsApp-Benachrichtigungen bei guten Wiederverkaufsangeboten für Smartphones. Unterstützt iPhone 12–16e, Samsung S21–S25 / A-Serie und Google Pixel 7–9.

Benachrichtigungen werden über die **Meta WhatsApp Cloud API** versendet. Optional bewertet eine **Groq AI** (llama-3.3-70b-versatile) jedes Inserat mit einem Wiederverkaufscore (1–10) und warnt vor nicht-originalen Ersatzteilen.

Die Oberfläche ist ein lokales Web-Dashboard — kein separates Tool notwendig.

---

## Einrichtung

### 1. Python & Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 2. credentials.json anlegen

Erstelle eine Datei `credentials.json` im Projektordner (wird von Git ignoriert):

```json
{
  "groq_api_key": "dein-groq-api-key",
  "whatsapp": {
    "token": "dein-meta-access-token",
    "phone_number_id": "deine-phone-number-id",
    "recipient": ["4917612345678"]
  }
}
```

- **WhatsApp**: Access Token und Phone Number ID erhältst du im [Meta Developer Portal](https://developers.facebook.com/) unter deiner WhatsApp Business App.
- **Groq API Key**: Kostenlos auf [console.groq.com](https://console.groq.com) erstellen. Wenn kein Key angegeben wird, läuft der Bot ohne KI-Scoring.
- `recipient` kann ein einzelner String oder eine Liste von Nummern sein (Ländervorwahl ohne `+`, z.B. `4917612345678`).

### 3. config.json anpassen

`config.json` enthält alle Suchen und allgemeinen Einstellungen. Die Datei ist bereits mit gängigen iPhone-, Samsung- und Pixel-Modellen vorkonfiguriert. Suchen können einzeln aktiviert/deaktiviert werden.

```json
{
  "searches": [
    {
      "name": "iPhone 13",
      "query": "iphone 13",
      "max_price": 130,
      "min_price": 35,
      "keywords_blocked": ["mini", "pro"],
      "enabled": true
    }
  ],
  "settings": {
    "check_interval_minutes": 2,
    "max_workers": 6,
    "seen_listings_file": "data/seen_listings.json",
    "log_file": "logs/bot.log",
    "keywords_blocked": [
      "defekt",
      "bastler",
      "ersatzteil",
      "gesperrt",
      "icloud"
    ]
  },
  "whatsapp": {}
}
```

> Sensitive Felder (`token`, `phone_number_id`, `recipient`, `groq_api_key`) gehören in `credentials.json`, nicht in `config.json`.

### 4. Bot starten

```bash
python server.py
```

Öffne dann **http://localhost:5000** im Browser. Über das Dashboard kannst du den Bot starten/stoppen, das Prüfintervall ändern und einzelne Suchen ein-/ausschalten.

---

## Konfigurationsoptionen

### Suche (`searches[]`)

| Feld                | Beschreibung                                         | Beispiel          |
| ------------------- | ---------------------------------------------------- | ----------------- |
| `name`              | Anzeigename in Benachrichtigungen                    | `"iPhone 13"`     |
| `query`             | Suchbegriff für Kleinanzeigen                        | `"iphone 13"`     |
| `max_price`         | Maximaler Preis in € (0 = kein Limit)                | `130`             |
| `min_price`         | Minimaler Preis in € (filtert Spam-Inserate)         | `35`              |
| `keywords_required` | Alle Keywords müssen im Titel/Beschreibung vorkommen | `["256gb"]`       |
| `keywords_blocked`  | Inserate mit diesen Keywords werden übersprungen     | `["mini", "pro"]` |
| `enabled`           | Suche aktiviert/deaktiviert                          | `true`            |

### Einstellungen (`settings`)

| Feld                     | Beschreibung                                              | Standard                   |
| ------------------------ | --------------------------------------------------------- | -------------------------- |
| `check_interval_minutes` | Prüfintervall in Minuten                                  | `2`                        |
| `max_workers`            | Parallele Such-Threads                                    | `6`                        |
| `seen_listings_file`     | Pfad zur Datei mit bereits gesehenen IDs                  | `data/seen_listings.json`  |
| `log_file`               | Pfad zur Logdatei                                         | `logs/bot.log`             |
| `keywords_blocked`       | Globale Blacklist — gilt für alle Suchen                  | `["defekt", "bastler", …]` |
| `groq_api_key`           | Groq API Key (alternativ in `credentials.json` eintragen) | `""`                       |

---

## Funktionsweise

- Pro Prüfzyklus werden bis zu **3 Seiten** Suchergebnisse gescannt — es werden nur Inserate der letzten 30 Minuten weiterverarbeitet.
- Alle Suchen laufen **parallel** (Thread Pool mit `max_workers` Threads).
- Für jedes vielversprechende Inserat wird die **Detailseite** aufgerufen, um die vollständige Beschreibung und das Konto-Erstellungsdatum des Verkäufers zu lesen.
- **Neues Verkäuferkonto** (heute oder gestern erstellt) → Inserat wird übersprungen.
- Optional bewertet die **Groq AI** das Inserat mit einem Score von 1–10 und gibt eine Warnung aus, falls Displaytausch, Akkutausch oder andere Modifikationen erkannt werden.
- Benachrichtigungen werden als WhatsApp-Nachricht mit Bild versendet; bei fehlender Abbildung nur als Text.
- `data/seen_listings.json` speichert bereits gesehene IDs mit Zeitstempel. Einträge älter als 30 Tage werden automatisch bereinigt.

---

## Projektstruktur

```
ResellingBot/
├── server.py               — Flask-Webserver & Bot-Steuerung (Einstiegspunkt)
├── config.json             — Suchen, Einstellungen, WhatsApp-Platzhalter
├── credentials.json        — Sensitive Zugangsdaten (gitignored)
├── requirements.txt        — Python-Abhängigkeiten
├── bot/
│   ├── main.py             — Orchestrierung, Config-Laden, Seen-Listings
│   ├── scraper.py          — Kleinanzeigen-Scraper & Angebotsfilter
│   ├── notifier.py         — WhatsApp Cloud API Benachrichtigungen
│   └── ai_scorer.py        — Groq AI Scoring (1–10)
├── frontend/
│   ├── index.html          — Dashboard (Start/Stop, Suchen, Status)
│   ├── log.html / log.js   — Log-Viewer
│   ├── main.js             — Dashboard-Logik
│   └── style.css           — Styles
├── data/
│   └── seen_listings.json  — Automatisch erstellt; bereits gesehene IDs
└── logs/
    └── bot.log             — Automatisch erstellt; Logdatei
```

---

## Hinweise

- `data/seen_listings.json` verhindert Doppel-Benachrichtigungen, auch nach Neustart.
- Beim ersten Start werden alle aktuell vorhandenen Inserate als „gesehen" markiert — nur _neue_ Inserate lösen Benachrichtigungen aus.
- Respektiere die Nutzungsbedingungen von Kleinanzeigen. Zu kurze Prüfintervalle können zu temporären Sperren führen (empfohlen: ≥ 2 Minuten).
- Der Meta WhatsApp Cloud API Access Token läuft nach 24 Stunden ab, wenn er aus einem Test-System stammt. Für dauerhaften Betrieb einen permanenten System User Token verwenden.

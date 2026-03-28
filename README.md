# ResellingBot — Kleinanzeigen Monitor

Überwacht Kleinanzeigen automatisch und sendet Telegram-Benachrichtigungen bei guten Handyangeboten.

---

## Einrichtung

### 1. Python & Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 2. WhatsApp-Benachrichtigungen einrichten (CallMeBot)

CallMeBot ist ein kostenloser Dienst, der dir WhatsApp-Nachrichten senden kann.

**Einmalige Aktivierung:**

1. Speichere folgende Nummer in deinen Kontakten: **+34 644 59 84 13** (Name z.B. „CallMeBot")
2. Schicke dieser Nummer auf WhatsApp die Nachricht:  
   `I allow callmebot to send me messages`
3. Du erhältst eine Antwort mit deinem persönlichen **API-Key** (z.B. `1234567`)
4. Trage deine Handynummer (mit Ländervorwahl, ohne `+`, z.B. `4917612345678`) und den API-Key in `config.json` ein

### 3. config.json konfigurieren

```json
{
  "whatsapp": {
    "phone": "4917612345678",
    "api_key": "1234567"
  },
  "searches": [
    {
      "name": "iPhone 13",
      "query": "iphone 13",
      "max_price": 350,
      "min_price": 50,
      "keywords_required": [],
      "keywords_blocked": ["defekt", "bastler", "ersatzteil"],
      "enabled": true
    }
  ],
  "settings": {
    "check_interval_minutes": 5
  }
}
```

### 4. Bot starten

```bash
python main.py
```

---

## Konfigurationsoptionen

### Suche (`searches[]`)

| Feld                | Beschreibung                                       | Beispiel                |
| ------------------- | -------------------------------------------------- | ----------------------- |
| `name`              | Anzeigename in Benachrichtigungen                  | `"iPhone 13"`           |
| `query`             | Suchbegriff für Kleinanzeigen                      | `"iphone 13 256gb"`     |
| `max_price`         | Maximaler Preis in € (0 = kein Limit)              | `350`                   |
| `min_price`         | Minimaler Preis in € (zum Ausfiltern von Spam)     | `50`                    |
| `keywords_required` | Alle diese Keywords müssen im Titel/Text vorkommen | `["256gb"]`             |
| `keywords_blocked`  | Listings mit diesen Keywords werden ignoriert      | `["defekt", "bastler"]` |
| `enabled`           | Suche an/aus                                       | `true`                  |

### Einstellungen (`settings`)

| Feld                     | Beschreibung                        | Standard             |
| ------------------------ | ----------------------------------- | -------------------- |
| `check_interval_minutes` | Wie oft geprüft wird                | `5`                  |
| `seen_listings_file`     | Datei für bereits gesehene Angebote | `seen_listings.json` |
| `log_file`               | Logdatei                            | `bot.log`            |

---

## Projektstruktur

```
ResellingBot/
├── main.py             — Hauptprogramm & Scheduler
├── scraper.py          — Kleinanzeigen-Scraper & Angebotsfilter
├── notifier.py         — Telegram-Benachrichtigungen
├── config.json         — Deine Konfiguration
├── requirements.txt    — Python-Abhängigkeiten
├── seen_listings.json  — Automatisch erstellt; bereits gesehene IDs
└── bot.log             — Automatisch erstellt; Logdatei
```

---

## Hinweise

- Der Bot prüft nur die **erste Suchergebnisseite** (neueste Angebote zuerst)
- `seen_listings.json` verhindert Doppel-Benachrichtigungen, auch nach Neustart
- Beim ersten Start werden alle aktuell vorhandenen Angebote als "gesehen" markiert — nur _neue_ Angebote lösen Benachrichtigungen aus
- Respektiere die Nutzungsbedingungen von Kleinanzeigen; zu kurze Intervalle können zu temporären Sperren führen (empfohlen: ≥ 5 Minuten)

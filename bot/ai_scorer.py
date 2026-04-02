# Groq AI scorer: evaluates a listing's resale value, condition, and originality.
# Returns a score (1-10) and an optional warning string for non-original parts.
# Uses Groq's free tier (console.groq.com) with llama-3.3-70b-versatile.
import json
import logging
import re
import threading
import time
from groq import Groq

logger = logging.getLogger(__name__)

# Serialize Groq calls across threads to avoid hitting rate limits
_groq_lock = threading.Lock()

# Model — llama-3.3-70b-versatile gives significantly better judgment for condition/originality scoring
_GROQ_MODEL = "llama-3.3-70b-versatile"

# System prompt: detailed scoring rubric and strict JSON output format
_SYSTEM = """Du bist ein Experte für die Bewertung von Gebrauchthandy-Inseraten auf deutschen Kleinanzeigenportalen im Hinblick auf Wiederverkaufsgewinn.

Deine Aufgabe ist es, zu bewerten, wie gut ein Inserat für jemanden ist, der das Gerät günstig KAUFEN und mit Gewinn WIEDERVERKAUFEN möchte.

Antworte ausschließlich mit validem JSON in genau diesem Format (kein Markdown, keine Erklärung):
{"score": <ganze Zahl 1-10>, "warning": "<string>"}

BEWERTUNGSSKALA:
10 — Neuwertig / wie neu, vollständiges Originalzubehör, alle Originalteile, guter Preis, keine Warnsignale
8-9 — Guter Zustand, nur leichte Gebrauchsspuren, Originalteile, ausreichende Gewinnmarge
6-7 — Durchschnittlicher Zustand, sichtbare Kratzer oder Dellen, Zubehör fehlt teilweise, noch weiterverkäuflich
4-5 — Deutliche Schäden (gerissene Rückseite, tiefe Kratzer) oder Preis zu hoch für den beschriebenen Zustand
2-3 — Erhebliche Schäden (verbogener Rahmen, tote Pixel, starke Kratzer), Nicht-Originalteile oder stark überteuert
1   — Praktisch unverkäuflich: iCloud-/Google-gesperrt, komplett defekt, Wasserschaden, Gerät nur für Ersatzteile

FAKTOREN DIE DEN SCORE SENKEN:
- Display ausgetauscht (besonders kein Original-Display)
- Akku durch Nicht-Originalteil ersetzt
- Drittanbieter-Reparaturen erwähnt
- Ladekabel, Kabel oder Originalverpackung fehlt (kleine Abwertung)
- Verkäufer schreibt „Verkaufe auf Probe" oder beschreibt Zustand vage
- Preis lässt keine Gewinnmarge
- Gerät gesperrt (iCloud, Google-Konto, Netzsperre)
- Wasser- oder Displayschaden

FAKTOREN DIE DEN SCORE ERHÖHEN:
- „Neuwertig", „wie neu", „TOP Zustand", „1a Zustand"
- Originalzubehör vorhanden (Ladekabel, Box usw.)
- Originalakku und -teile
- Detaillierte, ehrliche Beschreibung oder klare Fotos beschrieben
- Preis deutlich unter Marktwert

WARNUNGSFELD:
- Falls Display, Akku oder ein anderes internes Bauteil ausgetauscht wurde oder kein Original ist, kurz auf Deutsch beschreiben (z.B. „Display ersetzt (kein Original)", „Akku getauscht")
- Falls das Gerät möglicherweise gesperrt ist oder Kontoprobleme bestehen, erwähnen (z.B. „Mögliche iCloud-Sperre")
- Warnungsfeld leer lassen („") wenn alles original und unverändert wirkt"""

# User message — description capped at 600 chars for better context with the stronger model
_USER_TEMPLATE = """Titel: {title}
Preis: {price} EUR{vb}{market_line}
Beschreibung: {description}"""


# Calls Groq API and returns (score, warning). Returns (None, "") on any failure.
# market_price: optional eBay median sold price in EUR to help the AI judge margin.
def score_listing(listing, api_key: str, market_price: int | None = None) -> tuple:
    if not api_key:
        logger.warning("Groq API key not configured — skipping AI score")
        return None, ""

    # 600 chars gives the stronger model enough context to make accurate condition judgments
    description = (listing.description or "")[:600] or "Keine Beschreibung"
    vb_suffix = " (VB)" if listing.negotiable else ""
    price_str = str(listing.price) if listing.price is not None else "Preis auf Anfrage"

    if market_price is not None and listing.price is not None:
        margin = market_price - listing.price
        market_line = f"\nMarktwert auf eBay (Median): ~{market_price} EUR (geschätzte Marge: ~{margin} EUR)"
    else:
        market_line = ""

    user_msg = _USER_TEMPLATE.format(
        title=listing.title,
        price=price_str,
        vb=vb_suffix,
        market_line=market_line,
        description=description,
    )

    client = Groq(api_key=api_key)

    # Serialize calls across threads and retry up to 3 times on 429
    for attempt in range(3):
        with _groq_lock:
            try:
                chat = client.chat.completions.create(
                    model=_GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0,
                    max_tokens=120,
                )
                raw = (chat.choices[0].message.content or "").strip()
                break  # success
            except Exception as e:
                err_str = str(e)
                if "429" in err_str and attempt < 2:
                    # Parse retry delay from error message, fall back to 15s
                    match = re.search(r"retry[_ ]in[_ ](\d+\.?\d*)", err_str, re.IGNORECASE)
                    wait = float(match.group(1)) + 1 if match else 15
                    logger.warning(f"Groq 429 for {listing.listing_id} — retrying in {wait:.0f}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                else:
                    logger.warning(f"Groq scoring failed for listing {listing.listing_id}: {e}")
                    return None, ""
    else:
        return None, ""

    try:
        # Strip markdown code fences if the model wraps the JSON anyway
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        score = int(data.get("score", 0))
        warning = str(data.get("warning", "")).strip()

        # Clamp score to valid range
        score = max(1, min(10, score))
        return score, warning

    except Exception as e:
        logger.warning(f"Groq response parse failed for listing {listing.listing_id}: {e} — raw: {raw[:100]}")
        return None, ""

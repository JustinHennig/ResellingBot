# Groq AI scorer: evaluates a listing's resale value, condition, and originality.
# Returns a score (1-10) and an optional warning string for non-original parts.
# Uses Groq's free tier (console.groq.com) with llama-3.3-70b-versatile.
import json
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)

# Serialize Groq calls across threads to avoid hitting rate limits
_groq_lock = threading.Lock()

# Model — llama-3.1-8b-instant uses ~5x fewer tokens than 70b, fast enough for scoring
_GROQ_MODEL = "llama-3.1-8b-instant"

# System message sent once per call (not repeated in the user message)
_SYSTEM = (
    "You score second-hand electronics listings for resale value. "
    "Reply with ONLY valid JSON: {\"score\":<1-10>,\"warning\":\"<empty or 1 short phrase>\"}. "
    "Score guide: 10=mint/all-original, 7-8=good/minor wear, 5-6=average, 3-4=damage or overpriced, 1-2=heavy damage/locked/parts replaced. "
    "Warning: mention only if screen, battery, or parts were replaced/non-original. Empty string otherwise."
)

# Compact user message — description capped at 350 chars
_USER_TEMPLATE = "Title: {title}\nPrice: {price} EUR{vb}\nDesc: {description}"


# Calls Groq API and returns (score, warning). Returns (None, "") on any failure.
def score_listing(listing, api_key: str) -> tuple:
    # Import here so the package is only needed when AI scoring is enabled
    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq not installed. Run: pip install groq")
        return None, ""

    if not api_key:
        logger.warning("Groq API key not configured — skipping AI score")
        return None, ""

    # Truncate description to keep token usage low — 350 chars captures all condition info
    description = (listing.description or "")[:350] or "Keine Beschreibung"
    vb_suffix = " (VB)" if listing.negotiable else ""
    price_str = str(listing.price) if listing.price is not None else "Preis auf Anfrage"

    user_msg = _USER_TEMPLATE.format(
        title=listing.title,
        price=price_str,
        vb=vb_suffix,
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
                    max_tokens=60,
                )
                raw = chat.choices[0].message.content.strip()
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

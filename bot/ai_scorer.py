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

# Model — llama-3.3-70b-versatile gives significantly better judgment for condition/originality scoring
_GROQ_MODEL = "llama-3.3-70b-versatile"

# System prompt: detailed scoring rubric and strict JSON output format
_SYSTEM = """You are an expert at evaluating second-hand smartphone and electronics listings on German classifieds sites for resale profitability.

Your job is to score how good the listing is for someone who wants to BUY it cheap and RESELL it for profit.

Always respond with ONLY valid JSON in this exact format (no markdown, no explanation):
{"score": <integer 1-10>, "warning": "<string>"}

SCORING GUIDE:
10 — Mint / like new condition, full original accessories included, all original parts, well-priced, no red flags
8-9 — Good condition, minor cosmetic wear only, original parts, reasonable price for resale margin
6-7 — Average condition, visible scratches or dents, missing some accessories, still resellable
4-5 — Noticeable damage (cracked back, deep scratches), or price is too high for the described condition
2-3 — Significant damage (bent frame, dead pixels, heavy scratches), non-original parts, or very overpriced
1   — Basically unsellable: iCloud/Google locked, completely broken, water damage, parts-only device

FACTORS THAT LOWER THE SCORE:
- Screen replaced (especially non-original display)
- Battery replaced with non-original part
- Third-party repairs mentioned
- Missing charger, cable, or original box (minor deduction)
- Seller says "Verkaufe auf Probe" or vague condition
- Price leaves no resale margin
- Device is locked (iCloud, Google account, Netzsperre)
- Water or display damage

FACTORS THAT RAISE THE SCORE:
- "Neuwertig", "wie neu", "TOP Zustand", "1a Zustand"
- Original accessories included (Ladekabel, Box, etc.)
- Original battery and parts
- Clear photos described or detailed honest description
- Price significantly below market value

WARNING FIELD:
- If screen, battery, or any internal part was replaced or is non-original, briefly describe it in German (e.g. "Display ersetzt (kein Original)", "Akku getauscht")
- If the device might be locked or has account issues, mention it (e.g. "Mögliche iCloud-Sperre")
- Leave the warning field as an empty string "" if everything appears original and unmodified"""

# User message — description capped at 600 chars for better context with the stronger model
_USER_TEMPLATE = """Title: {title}
Price: {price} EUR{vb}
Description: {description}"""


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

    # 600 chars gives the stronger model enough context to make accurate condition judgments
    description = (listing.description or "")[:600] or "Keine Beschreibung"
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
                    max_tokens=120,
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

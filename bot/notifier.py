# WhatsApp notification helpers: formats listing data and delivers messages
# via the Meta WhatsApp Cloud API (v22.0).
import logging
import requests
from bot.scraper import Listing

logger = logging.getLogger(__name__)

WA_API_URL = "https://graph.facebook.com/v22.0"


# Sends a WhatsApp text message via the Meta Cloud API.
# recipient can be a single number string or a list of number strings.
def send_whatsapp_message(wa_config: dict, body: str) -> bool:
    token = wa_config["token"]
    phone_number_id = wa_config["phone_number_id"]
    raw = wa_config["recipient"]
    recipients = raw if isinstance(raw, list) else [raw]

    success = True
    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": body},
        }
        try:
            response = requests.post(
                f"{WA_API_URL}/{phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                logger.error(f"WhatsApp notification failed for {recipient}: HTTP {response.status_code} — {response.text[:200]}")
                success = False
        except requests.RequestException as e:
            logger.error(f"WhatsApp notification request failed for {recipient}: {e}")
            success = False
    return success


# Sends a WhatsApp image message with caption via the Meta Cloud API.
# recipient can be a single number string or a list of number strings.
def send_whatsapp_image(wa_config: dict, image_url: str, caption: str) -> bool:
    token = wa_config["token"]
    phone_number_id = wa_config["phone_number_id"]
    raw = wa_config["recipient"]
    recipients = raw if isinstance(raw, list) else [raw]

    success = True
    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption[:1024],  # WhatsApp caption limit
            },
        }
        try:
            response = requests.post(
                f"{WA_API_URL}/{phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning(f"WhatsApp image send failed for {recipient}: HTTP {response.status_code} — {response.text[:200]}")
                success = False
        except requests.RequestException as e:
            logger.warning(f"WhatsApp image request failed for {recipient}: {e}")
            success = False
    return success


# Returns formatted WhatsApp message body for a listing.
def format_listing_message(listing: Listing, search_name: str) -> str:
    if listing.price is not None:
        price_str = f"{listing.price} EUR (VB)" if listing.negotiable else f"{listing.price} EUR"
    else:
        price_str = "Preis auf Anfrage"

    lines = [f"*{search_name}: {listing.title}*"]

    # AI score line, e.g. "⭐ Score: 8/10"
    if listing.ai_score is not None:
        lines.append(f"⭐ Score: {listing.ai_score}/10")

    lines.append(price_str)

    # Margin line, e.g. "📈 Marge: ~60€ (Marktwert ~380€)"
    if listing.market_price is not None and listing.price is not None:
        margin = listing.market_price - listing.price
        lines.append(f"📈 Marge: ~{margin}€ (Marktwert ~{listing.market_price}€)")

    # AI warning for non-original/modified parts
    if listing.ai_warning:
        lines.append(f"⚠️ {listing.ai_warning}")

    if listing.description:
        short_desc = listing.description[:200]
        if len(listing.description) > 200:
            short_desc += "…"
        lines.append(short_desc)
    lines.append(listing.url)

    return "\n".join(lines)


# Sends a WhatsApp notification for a new listing, with image if available.
def notify_new_listing(wa_config: dict, listing: Listing, search_name: str) -> bool:
    body = format_listing_message(listing, search_name)

    if listing.image_url:
        success = send_whatsapp_image(wa_config, listing.image_url, body)
        if success:
            logger.info(f"Notification (image) sent for listing {listing.listing_id}: {listing.title}")
            return True
        # Fall back to text if image send fails
        logger.warning(f"Image send failed for {listing.listing_id}, falling back to text")

    success = send_whatsapp_message(wa_config, body)
    if success:
        logger.info(f"Notification (text) sent for listing {listing.listing_id}: {listing.title}")
    return success


# Sends a startup confirmation WhatsApp message.
def send_startup_message(wa_config: dict, search_names: list[str]) -> None:
    names_str = ", ".join(search_names)
    send_whatsapp_message(wa_config, f"✅ Reselling Bot gestartet\nAktive Suchen: {names_str}")


# Checks that all required WhatsApp config fields are present.
def validate_whatsapp_config(wa_config: dict) -> bool:
    required = ["token", "phone_number_id", "recipient"]
    for field in required:
        if not wa_config.get(field):
            logger.error(f"WhatsApp config fehlt: '{field}' in config.json unter 'whatsapp' eintragen.")
            return False
    logger.info("WhatsApp config OK.")
    return True

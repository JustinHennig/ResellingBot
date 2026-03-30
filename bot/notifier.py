import logging
import requests
from typing import Optional
from bot.scraper import Listing
from bot.scorer import format_stars

logger = logging.getLogger(__name__)

WA_API_URL = "https://graph.facebook.com/v22.0"


def send_whatsapp_message(wa_config: dict, body: str) -> bool:
    """Sends a WhatsApp text message via the Meta Cloud API."""
    token = wa_config["token"]
    phone_number_id = wa_config["phone_number_id"]
    recipient = wa_config["recipient"]

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
        if response.status_code == 200:
            return True
        logger.error(f"WhatsApp notification failed: HTTP {response.status_code} — {response.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.error(f"WhatsApp notification request failed: {e}")
        return False


def send_whatsapp_image(wa_config: dict, image_url: str, caption: str) -> bool:
    """Sends a WhatsApp image message with caption via the Meta Cloud API."""
    token = wa_config["token"]
    phone_number_id = wa_config["phone_number_id"]
    recipient = wa_config["recipient"]

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
        if response.status_code == 200:
            return True
        logger.warning(f"WhatsApp image send failed: HTTP {response.status_code} — {response.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.warning(f"WhatsApp image request failed: {e}")
        return False


def format_listing_message(
    listing: Listing,
    search_name: str,
    score: Optional[tuple[int, str]] = None,
) -> str:
    """Returns formatted WhatsApp message body for a listing."""
    price_str = f"{listing.price} EUR" if listing.price is not None else "Preis auf Anfrage"

    lines = [f"*{search_name}: {listing.title}*"]

    if score is not None:
        stars, reason = score
        lines.append(f"{format_stars(stars)}  {reason}")

    lines.append(price_str)

    if listing.description:
        short_desc = listing.description[:200]
        if len(listing.description) > 200:
            short_desc += "…"
        lines.append(short_desc)
    lines.append(listing.url)

    return "\n".join(lines)


def notify_new_listing(
    wa_config: dict,
    listing: Listing,
    search_name: str,
    score: Optional[tuple[int, str]] = None,
) -> bool:
    """Sends a WhatsApp notification for a new listing, with image if available."""
    body = format_listing_message(listing, search_name, score=score)

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


def send_startup_message(wa_config: dict, search_names: list[str]) -> None:
    """Sends a startup confirmation WhatsApp message."""
    names_str = ", ".join(search_names)
    send_whatsapp_message(wa_config, f"✅ Reselling Bot gestartet\nAktive Suchen: {names_str}")


def validate_whatsapp_config(wa_config: dict) -> bool:
    """Checks that all required WhatsApp config fields are present."""
    required = ["token", "phone_number_id", "recipient"]
    for field in required:
        if not wa_config.get(field):
            logger.error(f"WhatsApp config fehlt: '{field}' in config.json unter 'whatsapp' eintragen.")
            return False
    logger.info("WhatsApp config OK.")
    return True

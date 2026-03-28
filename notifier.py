import logging
import requests
from scraper import Listing

logger = logging.getLogger(__name__)

NTFY_BASE_URL = "https://ntfy.sh"


def send_notification(topic: str, title: str, body: str, url: str = "") -> bool:
    """
    Sends a push notification via ntfy.sh.
    topic: your personal topic name (keep it random/secret)
    """
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": "high",
        "Tags": "bell,iphone",
    }
    if url:
        headers["Click"] = url

    try:
        response = requests.post(
            f"{NTFY_BASE_URL}/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        if response.status_code == 200:
            return True
        logger.error(f"ntfy notification failed: HTTP {response.status_code} — {response.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.error(f"ntfy notification request failed: {e}")
        return False


def format_listing_message(listing: Listing, search_name: str) -> tuple[str, str]:
    """Returns (title, body) for a push notification."""
    price_str = f"{listing.price} EUR" if listing.price is not None else "Preis auf Anfrage"
    title = f"{search_name}: {listing.title} — {price_str}"

    lines = [
        f"💶 {price_str}",
        f"📍 {listing.location}",
    ]
    if listing.description:
        short_desc = listing.description[:150]
        if len(listing.description) > 150:
            short_desc += "…"
        lines.append(short_desc)

    return title, "\n".join(lines)


def notify_new_listing(
    topic: str, listing: Listing, search_name: str
) -> bool:
    """Sends a push notification for a new listing."""
    title, body = format_listing_message(listing, search_name)
    success = send_notification(topic, title, body, url=listing.url)
    if success:
        logger.info(
            f"Notification sent for listing {listing.listing_id}: {listing.title}"
        )
    return success


def send_startup_message(topic: str, search_names: list[str]) -> None:
    """Sends a startup confirmation push notification."""
    names_str = ", ".join(search_names)
    send_notification(
        topic,
        title="✅ Reselling Bot gestartet",
        body=f"Aktive Suchen: {names_str}",
    )


def validate_ntfy_config(topic: str) -> bool:
    """Checks that the topic is configured and the ntfy server is reachable."""
    if topic == "DEIN_TOPIC_NAME_HIER" or not topic:
        logger.error(
            "ntfy-Topic nicht konfiguriert! "
            "Bitte ntfy_topic in config.json eintragen."
        )
        return False
    try:
        response = requests.get(f"{NTFY_BASE_URL}/{topic}/json", timeout=5, stream=True)
        response.close()
        logger.info(f"ntfy topic '{topic}' ist erreichbar.")
        return True
    except requests.RequestException as e:
        logger.error(f"ntfy server nicht erreichbar: {e}")
        return False

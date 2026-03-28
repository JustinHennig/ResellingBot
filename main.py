"""
ResellingBot — Kleinanzeigen Monitor
Überwacht Suchanfragen und benachrichtigt per Telegram bei guten Angeboten.

Konfiguration: config.json
"""

import json
import logging
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import schedule

from notifier import notify_new_listing, send_startup_message, validate_ntfy_config
from scraper import Listing, fetch_listings, is_good_deal

CONFIG_FILE = Path(__file__).parent / "config.json"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_file: str) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"[ERROR] Konfigurationsdatei nicht gefunden: {CONFIG_FILE}")
        sys.exit(1)
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Seen-listings persistence
# ---------------------------------------------------------------------------

def load_seen_listings(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except (json.JSONDecodeError, IOError):
        return set()


def save_seen_listings(path: str, seen: set[str]) -> None:
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------

def check_search(
    search_config: dict,
    seen: set[str],
    topic: str,
    seen_file: str,
    global_blocked: list[str],
) -> None:
    """Runs one search cycle for a single search config entry."""
    name = search_config.get("name", search_config.get("query", "?"))
    query = search_config.get("query", "")
    max_price = search_config.get("max_price", 0)

    if not query:
        return

    logger.info(f"Checking search: '{name}'")
    listings = fetch_listings(query, max_price=max_price, page=0)

    new_count = 0
    cutoff = datetime.now() - timedelta(minutes=30)

    for listing in listings:
        if listing.listing_id in seen:
            continue

        # Filter: ignore listings older than 30 minutes
        if listing.posted_at is not None and listing.posted_at < cutoff:
            logger.debug(f"Skipped old listing {listing.listing_id} (posted {listing.posted_at:%H:%M})")
            continue

        seen.add(listing.listing_id)

        good, reason = is_good_deal(listing, search_config, global_blocked)
        if good:
            logger.info(f"Good deal found: {listing.title} — {listing.price}€")
            notify_new_listing(topic, listing, name)
            new_count += 1
        else:
            logger.debug(f"Skipped listing {listing.listing_id}: {reason}")

    save_seen_listings(seen_file, seen)
    logger.info(
        f"Search '{name}' done. {len(listings)} listings checked, {new_count} notifications sent."
    )


def run_all_searches(config: dict, seen: set[str]) -> None:
    topic = config["ntfy_topic"]
    seen_file = config["settings"].get("seen_listings_file", "seen_listings.json")
    global_blocked = config["settings"].get("keywords_blocked", [])

    for search in config.get("searches", []):
        if not search.get("enabled", True):
            continue
        try:
            check_search(search, seen, topic, seen_file, global_blocked)
        except Exception as e:
            logger.error(
                f"Unexpected error in search '{search.get('name')}': {e}\n"
                + traceback.format_exc()
            )

        # Be polite between requests
        time.sleep(2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_config()
    settings = config.get("settings", {})
    setup_logging(settings.get("log_file", "bot.log"))

    global logger
    logger = logging.getLogger("main")

    topic = config.get("ntfy_topic", "")

    if not validate_ntfy_config(topic):
        logger.error("ntfy-Topic nicht konfiguriert. Bot wird nicht gestartet.")
        sys.exit(1)

    seen_file = settings.get("seen_listings_file", "seen_listings.json")
    seen: set[str] = load_seen_listings(seen_file)
    logger.info(f"Loaded {len(seen)} previously seen listings.")

    interval = settings.get("check_interval_minutes", 5)
    active_names = [
        s["name"]
        for s in config.get("searches", [])
        if s.get("enabled", True)
    ]
    send_startup_message(topic, active_names)

    # Run immediately on start, then on schedule
    run_all_searches(config, seen)

    schedule.every(interval).minutes.do(
        run_all_searches, config=config, seen=seen
    )

    logger.info(f"Bot läuft. Intervall: alle {interval} Minuten. Strg+C zum Beenden.")

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()

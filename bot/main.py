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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import schedule

from bot.notifier import notify_new_listing, send_startup_message, validate_whatsapp_config
from bot.scraper import Listing, fetch_listings, fetch_listing_details, is_good_deal, is_new_seller
from bot.scorer import score_listing

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

logger = logging.getLogger(__name__)
_seen_lock = Lock()


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

SEEN_MAX_AGE_DAYS = 30  # IDs older than this are removed from seen_listings.json


def load_seen_listings(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
        # Backward compat: old format was a plain list with no timestamps
        if isinstance(data, list):
            return set(data)
        # New format: {id: iso_timestamp} — prune entries older than SEEN_MAX_AGE_DAYS
        cutoff = datetime.now() - timedelta(days=SEEN_MAX_AGE_DAYS)
        result: set[str] = set()
        for listing_id, ts_str in data.items():
            try:
                if datetime.fromisoformat(ts_str) >= cutoff:
                    result.add(listing_id)
            except (ValueError, TypeError):
                result.add(listing_id)  # Keep entries with unparseable timestamps
        pruned = len(data) - len(result)
        if pruned:
            logger.info(f"Pruned {pruned} old entries from seen listings ({len(result)} remaining).")
        return result
    except (json.JSONDecodeError, IOError):
        return set()


def save_seen_listings(path: str, seen: set[str]) -> None:
    p = Path(path)
    # Load existing timestamps so first-seen dates are preserved across saves
    existing: dict[str, str] = {}
    if p.exists():
        try:
            with p.open(encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    existing = data
        except (json.JSONDecodeError, IOError):
            pass
    now_iso = datetime.now().isoformat()
    timestamps = {id_: existing.get(id_, now_iso) for id_ in seen}
    # Atomic write: write to .tmp then replace so a crash never corrupts the file
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(timestamps, f, indent=2, sort_keys=True)
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------

def check_search(
    search_config: dict,
    seen: set[str],
    wa_config: dict,
    seen_file: str,
    global_blocked: list[str],
    stop_event,
    claude_config: dict | None = None,
) -> None:
    """Runs one search cycle for a single search config entry."""
    name = search_config.get("name", search_config.get("query", "?"))
    query = search_config.get("query", "")
    max_price = search_config.get("max_price", 0)

    if not query:
        return

    logger.info(f"Checking search: '{name}'")
    cutoff = datetime.now() - timedelta(minutes=30)

    # Fetch pages until all listings on a page are older than 30 minutes (max 3 pages)
    listings = []
    for page in range(3):
        if stop_event.is_set():
            return
        page_listings = fetch_listings(query, max_price=max_price, page=page)
        if not page_listings:
            break
        listings.extend(page_listings)
        # If every dated listing on this page is older than the cutoff, no point going further
        dated = [l for l in page_listings if l.posted_at is not None]
        if dated and all(l.posted_at < cutoff for l in dated):
            break
        if page > 0:
            time.sleep(1)

    new_count = 0

    for listing in listings:
        if stop_event.is_set():
            return

        with _seen_lock:
            if listing.listing_id in seen:
                continue
            # Reserve the ID immediately so another thread doesn't process the same listing
            seen.add(listing.listing_id)

        # Filter: ignore listings older than 30 minutes
        if listing.posted_at is not None and listing.posted_at < cutoff:
            logger.debug(f"Skipped old listing {listing.listing_id} (posted {listing.posted_at:%H:%M})")
            continue

        good, reason = is_good_deal(listing, search_config, global_blocked)
        if not good:
            logger.debug(f"Skipped listing {listing.listing_id}: {reason}")
            continue

        if stop_event.is_set():
            return

        # Fetch detail page once for full description + seller join date
        full_desc, join_date = fetch_listing_details(listing.url)

        if is_new_seller(join_date):
            logger.info(f"Skipped listing {listing.listing_id}: new seller account")
            continue

        # Re-run keyword check against the full description
        if full_desc:
            listing.description = full_desc
            good, reason = is_good_deal(listing, search_config, global_blocked)
            if not good:
                logger.info(f"Skipped listing {listing.listing_id} after full desc check: {reason}")
                continue

        logger.info(f"Good deal found: {listing.title} — {listing.price}€")
        score = None
        if claude_config and claude_config.get("api_key"):
            score = score_listing(
                listing,
                search_name=name,
                max_price=max_price,
                api_key=claude_config["api_key"],
            )
        notify_new_listing(wa_config, listing, name, score=score)
        new_count += 1

    with _seen_lock:
        save_seen_listings(seen_file, seen)
    logger.info(
        f"Search '{name}' done. {len(listings)} listings checked, {new_count} notifications sent."
    )


def run_all_searches(config: dict, seen: set[str], stop_event=None) -> None:
    import threading
    if stop_event is None:
        stop_event = threading.Event()  # never-set fallback for main.py standalone use
    wa_config = config["whatsapp"]
    seen_file = config["settings"].get("seen_listings_file", "seen_listings.json")
    global_blocked = config["settings"].get("keywords_blocked", [])
    max_workers = config["settings"].get("max_workers", 6)
    claude_config = config.get("claude")

    active_searches = [s for s in config.get("searches", []) if s.get("enabled", True)]

    def _run(search):
        try:
            check_search(search, seen, wa_config, seen_file, global_blocked, stop_event, claude_config)
        except Exception as e:
            logger.error(
                f"Unexpected error in search '{search.get('name')}': {e}\n"
                + traceback.format_exc()
            )

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="search") as executor:
        futures = {executor.submit(_run, s): s.get("name", "?") for s in active_searches}
        for future in as_completed(futures):
            name = futures[future]
            if future.exception():
                logger.error(f"Thread for '{name}' raised: {future.exception()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_config()
    settings = config.get("settings", {})
    setup_logging(settings.get("log_file", "bot.log"))

    global logger
    logger = logging.getLogger("main")

    wa_config = config.get("whatsapp", {})

    if not validate_whatsapp_config(wa_config):
        logger.error("WhatsApp nicht konfiguriert. Bot wird nicht gestartet.")
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
    send_startup_message(wa_config, active_names)

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

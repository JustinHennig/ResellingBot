import requests
from bs4 import BeautifulSoup
import logging
import time
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class Listing:
    listing_id: str
    title: str
    price: Optional[int]
    location: str
    url: str
    description: str
    image_url: str
    posted_at: Optional[datetime] = None


def build_search_url(query: str, max_price: int = 0, page: int = 0) -> str:
    """Builds the Kleinanzeigen search URL."""
    encoded_query = quote_plus(query)
    price_segment = f"/preis::{max_price}" if max_price > 0 else ""
    page_segment = f"/seite:{page + 1}" if page > 0 else ""
    return (
        f"https://www.kleinanzeigen.de/s-anzeige:angebote"
        f"{price_segment}"
        f"/{encoded_query}"
        f"/k0{page_segment}"
    )


def parse_posted_at(text: str) -> Optional[datetime]:
    """
    Parses Kleinanzeigen timestamp strings into a datetime.
    Examples: 'Heute, 14:30', 'Gestern, 09:15', '22.03.2026', 'Gerade eben'
    """
    if not text:
        return None
    # Strip HTML entities and tags before processing
    text = re.sub(r'&#?\w+;', '', text)   # remove HTML entities like &#8203;
    text = re.sub(r'<[^>]+>', '', text)    # remove any stray HTML tags
    text = text.strip()
    if not text:
        return None

    now = datetime.now()

    if "gerade" in text.lower():
        return now

    # "Heute, HH:MM"
    m = re.match(r"(?i)heute,?\s*(\d{1,2}):(\d{2})", text)
    if m:
        try:
            return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        except ValueError:
            return None

    # "Gestern, HH:MM"
    m = re.match(r"(?i)gestern,?\s*(\d{1,2}):(\d{2})", text)
    if m:
        try:
            yesterday = now - timedelta(days=1)
            return yesterday.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        except ValueError:
            return None

    # "DD.MM.YYYY"
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


def parse_price(price_text: str) -> Optional[int]:
    """Extracts integer price from a price string like '350 €' or 'VB 350 €'.
    Returns None if the text looks like location data, HTML, or anything other than a price.
    """
    if not price_text:
        return None
    # Reject HTML content immediately
    if "<" in price_text or ">" in price_text:
        return None
    # Reject if text contains letters but no currency/price indicator
    # (catches location names like "82031 Freimann")
    has_currency = re.search(r'[€]|\bEUR\b|\bVB\b|\bvb\b', price_text, re.IGNORECASE)
    if re.search(r'[a-zA-ZäöüÄÖÜß]', price_text) and not has_currency:
        return None
    digits = re.sub(r'[^0-9]', '', price_text)
    if not digits:
        return None
    try:
        price = int(digits)
    except ValueError:
        return None
    # Sanity check: no phone has a plausible price above 9999 €
    return price if price <= 9999 else None


def fetch_listings(query: str, max_price: int = 0, page: int = 0) -> list[Listing]:
    """
    Fetches listings from Kleinanzeigen for a given search query.
    Returns a list of Listing objects.
    """
    url = build_search_url(query, max_price, page)
    logger.debug(f"Fetching: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Request failed for query '{query}': {e}")
        return []

    # Python 3.14's html.parser crashes on malformed numeric entities like &#8203 (missing semicolon).
    # Fix them before parsing.
    html = re.sub(r'&#(\d+)(?!;)', r'&#\1;', response.text)
    soup = BeautifulSoup(html, "html.parser")
    listings = []

    # Kleinanzeigen wraps each ad in an <article> with class 'aditem'
    articles = soup.select("article.aditem")

    if not articles:
        # Fallback: try li elements
        articles = soup.select("li[data-adid]")

    for article in articles:
        try:
            listing = _parse_article(article)
            if listing:
                listings.append(listing)
        except Exception as e:
            logger.debug(f"Failed to parse article: {e}")
            continue

    logger.info(f"Found {len(listings)} listings for '{query}' (page {page + 1})")
    return listings


def _parse_article(article) -> Optional[Listing]:
    """Parses a single article/li element into a Listing."""

    # --- ID ---
    listing_id = (
        article.get("data-adid")
        or article.get("data-ad-id")
        or article.get("id", "")
    )
    if not listing_id:
        return None

    # --- Title ---
    title_el = (
        article.select_one("h2.text-module-begin a")
        or article.select_one(".ellipsis")
        or article.select_one("a.ellipsis")
        or article.select_one("h2 a")
    )
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    # --- URL ---
    link_el = article.select_one("a[href]")
    relative_url = link_el["href"] if link_el else ""
    full_url = (
        f"https://www.kleinanzeigen.de{relative_url}"
        if relative_url.startswith("/")
        else relative_url
    )

    # --- Price ---
    price_el = (
        article.select_one("p.aditem-main--middle--price-shipping--price")
        or article.select_one(".aditem-main--middle--price")
    )
    price_text = price_el.get_text(strip=True) if price_el else ""
    price = parse_price(price_text)

    # --- Location ---
    location_el = article.select_one(".aditem-main--top--left")
    location = location_el.get_text(strip=True) if location_el else "Unbekannt"
    # Strip any HTML entities from location text
    location = re.sub(r'&#?\w+;', '', location).strip() or "Unbekannt"

    # --- Description ---
    desc_el = article.select_one("p.aditem-main--middle--description")
    description = desc_el.get_text(strip=True) if desc_el else ""

    # --- Image ---
    img_el = article.select_one("img[src]")
    image_url = img_el["src"] if img_el else ""

    # --- Posted at ---
    date_el = (
        article.select_one(".aditem-main--top--right")
        or article.select_one("[class*='date']")
        or article.select_one(".simpletag")
    )
    posted_at = parse_posted_at(date_el.get_text(strip=True)) if date_el else None

    return Listing(
        listing_id=str(listing_id),
        title=title,
        price=price,
        location=location,
        url=full_url,
        description=description,
        image_url=image_url,
        posted_at=posted_at,
    )


def _parse_german_date(text: str) -> Optional[datetime]:
    """Parses a German date like 'Aktiv seit 15. März 2024' into a datetime."""
    if not text:
        return None
    m = re.search(r'(\d{1,2})\.\s*(\w+)\s+(\d{4})', text)
    if not m:
        return None
    day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = GERMAN_MONTHS.get(month_str)
    if not month:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def fetch_seller_join_date(listing_url: str) -> Optional[datetime]:
    """Fetches the listing detail page and returns the seller's account creation date."""
    try:
        time.sleep(1)
        response = requests.get(listing_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.debug(f"Could not fetch listing page for seller check: {e}")
        return None

    html = re.sub(r'&#(\d+)(?!;)', r'&#\1;', response.text)
    soup = BeautifulSoup(html, "html.parser")

    date_el = (
        soup.select_one(".userprofile-vip-membershipdate")
        or soup.select_one("[class*='membershipdate']")
    )
    if date_el:
        return _parse_german_date(date_el.get_text(strip=True))

    # Fallback: search raw text for "Aktiv seit" / "Mitglied seit"
    for el in soup.find_all(string=re.compile(r'(?i)(aktiv|mitglied)\s+seit')):
        date = _parse_german_date(el)
        if date:
            return date

    return None


def is_new_seller(listing_url: str) -> bool:
    """Returns True if the seller's account was created today or yesterday (likely a scammer)."""
    join_date = fetch_seller_join_date(listing_url)
    if join_date is None:
        return False  # Can't determine — give benefit of the doubt
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    return join_date.date() >= yesterday


def is_good_deal(listing: Listing, search_config: dict, global_blocked: list[str] = []) -> tuple[bool, str]:
    """
    Checks whether a listing matches the configured criteria.
    Returns (is_good, reason_string).
    """
    min_price = search_config.get("min_price", 0)
    max_price = search_config.get("max_price", 0)
    keywords_required: list[str] = search_config.get("keywords_required", [])
    keywords_blocked: list[str] = list(global_blocked) + search_config.get("keywords_blocked", [])

    text = f"{listing.title} {listing.description}".lower()

    # Price check
    if listing.price is None:
        return False, "Kein Preis angegeben"

    if max_price > 0 and listing.price > max_price:
        return False, f"Preis {listing.price}€ zu hoch (Max: {max_price}€)"

    if min_price > 0 and listing.price < min_price:
        return False, f"Preis {listing.price}€ zu niedrig (Min: {min_price}€)"

    # Blocked keywords
    for kw in keywords_blocked:
        if kw.lower() in text:
            return False, f"Gesperrtes Keyword gefunden: '{kw}'"

    # Required keywords
    for kw in keywords_required:
        if kw.lower() not in text:
            return False, f"Pflicht-Keyword fehlt: '{kw}'"

    return True, "Passt allen Kriterien"

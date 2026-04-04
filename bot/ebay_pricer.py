# Scrapes eBay.de completed/sold listings to estimate the resale market price
# for a given search query.
import logging
import re
import statistics
import time
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_EBAY_SOLD_URL = (
    "https://www.ebay.de/sch/i.html"
    "?_nkw={query}&LH_Sold=1&LH_Complete=1&_sacat=0"
)

_HEADERS = {
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

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _ebay_get(url: str, retries: int = 3, base_delay: float = 2.0) -> requests.Response:
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=_HEADERS, timeout=15)
            if response.status_code not in _RETRY_STATUSES:
                response.raise_for_status()
                return response
            raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
        except requests.ConnectionError as e:
            # DNS / network unreachable — retrying won't help, fail immediately
            raise
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"eBay request failed ({e}), retrying in {delay:.0f}s …")
            time.sleep(delay)
    raise RuntimeError("unreachable")


# Parses eBay price strings like "EUR 129,99" or "49,00 EUR" into an integer.
# Returns None for price ranges ("EUR 40,00 bis EUR 60,00") or unparseable text.
def _parse_ebay_price(text: str) -> Optional[int]:
    if not text:
        return None
    # Skip price ranges — they are ambiguous
    if " bis " in text or " to " in text:
        return None
    # Keep only digits, commas, and dots; take the first token
    cleaned = re.sub(r"[^\d,\.]", " ", text).strip()
    if not cleaned:
        return None
    token = cleaned.split()[0]
    # German decimal separator: "129,99" → "129.99"
    token = token.replace(",", ".")
    try:
        price = float(token)
        if 1 <= price <= 9999:
            return int(round(price))
    except ValueError:
        pass
    return None


# Fetches eBay.de completed listings for *query* and returns the median sold
# price in EUR. Returns None if fewer than 3 prices could be parsed (not enough
# data for a reliable estimate).
# TODO: re-enable once eBay network access is confirmed working
def fetch_ebay_sold_price(query: str, max_results: int = 30) -> Optional[int]:
    return None  # Temporarily disabled
    url = _EBAY_SOLD_URL.format(query=quote_plus(query))
    try:
        time.sleep(1)  # Polite delay — avoid hammering eBay
        response = _ebay_get(url)
    except Exception as e:
        logger.warning(f"eBay price fetch failed for '{query}': {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("li.s-item")

    prices = []
    for item in items[:max_results]:
        # eBay injects a dummy "Shop on eBay" item as the first result — skip it
        title_el = item.select_one(".s-item__title")
        if title_el and "Shop on eBay" in title_el.get_text():
            continue

        price_el = item.select_one(".s-item__price")
        if not price_el:
            continue

        price = _parse_ebay_price(price_el.get_text(strip=True))
        if price is not None:
            prices.append(price)

    if len(prices) < 3:
        logger.debug(f"Not enough eBay sold prices for '{query}' (found {len(prices)})")
        return None

    median = int(statistics.median(prices))
    logger.info(f"eBay.de median sold price for '{query}': {median}€ ({len(prices)} results)")
    return median

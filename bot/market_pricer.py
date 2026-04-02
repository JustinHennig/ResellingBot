# eBay market price fetcher: queries the eBay Finding API for recently sold listings
# and returns the median sold price for a given search query.
# Prices are cached in data/market_prices.json with a 14-day TTL.
import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent.parent / "data" / "market_prices.json"
CACHE_TTL_DAYS = 14
EBAY_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with CACHE_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    try:
        tmp.replace(CACHE_FILE)
    except PermissionError:
        import shutil
        shutil.copy2(tmp, CACHE_FILE)
        tmp.unlink(missing_ok=True)


# Fetches the median sold price for a query from the eBay Finding API.
# Returns None if the API key is missing, the request fails, or no results are found.
def get_market_price(query: str, ebay_app_id: str) -> Optional[int]:
    if not ebay_app_id:
        return None

    cache = _load_cache()
    entry = cache.get(query)
    if entry:
        try:
            fetched_at = datetime.fromisoformat(entry["fetched_at"])
            if datetime.now() - fetched_at < timedelta(days=CACHE_TTL_DAYS):
                logger.debug(f"Market price cache hit for '{query}': {entry['price']}€")
                return entry["price"]
        except (KeyError, ValueError):
            pass

    logger.info(f"Fetching eBay sold prices for '{query}' …")
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": ebay_app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "categoryId": "9355",           # Mobile Phones & Smartphones
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "ListingType",
        "itemFilter(1).value": "AuctionWithBIN",
        "itemFilter(2).name": "ListingType(1)",
        "itemFilter(2).value": "FixedPrice",
        "itemFilter(3).name": "Currency",
        "itemFilter(3).value": "EUR",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": "20",
        "outputSelector": "SellingStatus",
        "siteid": "77",                 # eBay.de
    }

    try:
        response = requests.get(EBAY_FINDING_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"eBay API request failed for '{query}': {e}")
        return None

    try:
        items = (
            data
            .get("findCompletedItemsResponse", [{}])[0]
            .get("searchResult", [{}])[0]
            .get("item", [])
        )
    except (KeyError, IndexError, TypeError):
        logger.warning(f"Unexpected eBay API response structure for '{query}'")
        return None

    if not items:
        logger.info(f"No eBay sold results for '{query}'")
        return None

    prices = []
    for item in items:
        try:
            price_str = (
                item["sellingStatus"][0]["currentPrice"][0]["__value__"]
            )
            prices.append(float(price_str))
        except (KeyError, IndexError, ValueError, TypeError):
            continue

    if not prices:
        logger.warning(f"Could not parse any prices from eBay results for '{query}'")
        return None

    median_price = int(statistics.median(prices))
    logger.info(f"eBay median sold price for '{query}': {median_price}€ (from {len(prices)} results)")

    cache[query] = {"price": median_price, "fetched_at": datetime.now().isoformat()}
    _save_cache(cache)

    return median_price

# Not yet implemented: This module will use the Claude API to score listings based on their quality and resale potential.

import json
import logging
from typing import Optional

import anthropic

from bot.scraper import Listing

logger = logging.getLogger(__name__)

_STARS = {1: "⭐☆☆☆☆", 2: "⭐⭐☆☆☆", 3: "⭐⭐⭐☆☆", 4: "⭐⭐⭐⭐☆", 5: "⭐⭐⭐⭐⭐"}

_PROMPT = """\
You are evaluating a second-hand phone listing for resale potential.

Listing: {search_name}
Title: {title}
Price: {price} EUR  (budget max: {max_price} EUR)
Description: {description}

Rate this listing 1–5 stars based on:
- Price vs budget (much cheaper than max = better)
- Described condition (mint/like new = better, scratches/damage = worse)
- Completeness (original box, charger, accessories = better)
- Seller credibility (detailed honest description = better, very vague = worse)

Respond with ONLY a JSON object, nothing else:
{{"stars": <1-5>, "reason": "<one short sentence in English>"}}"""


def score_listing(
    listing: Listing,
    search_name: str,
    max_price: int,
    api_key: str,
) -> Optional[tuple[int, str]]:
    """
    Asks Claude to rate the listing quality from 1–5 stars.
    Returns (stars, reason) or None if scoring is unavailable or fails.
    """
    if not api_key:
        return None

    prompt = _PROMPT.format(
        search_name=search_name,
        title=listing.title,
        price=listing.price if listing.price is not None else "?",
        max_price=max_price,
        description=listing.description[:800],
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        data = json.loads(raw)
        stars = max(1, min(5, int(data["stars"])))
        reason = str(data.get("reason", ""))[:120]
        logger.info(f"Scored listing {listing.listing_id}: {stars}★ — {reason}")
        return stars, reason
    except Exception as e:
        logger.warning(f"Scoring failed for listing {listing.listing_id}: {e}")
        return None


def format_stars(stars: int) -> str:
    return _STARS.get(stars, "")

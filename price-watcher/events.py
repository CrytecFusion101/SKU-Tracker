from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from scrapers import ScrapedProduct


@dataclass
class PriceEvent:
    """Canonical record produced by every scrape, regardless of outcome.

    This is the single object that flows from the scraper stage to the
    notifier and the state store, so both consumers see the same shape
    instead of the tracker deciding upfront what "counts" as a change.
    """

    product: str
    marketplace: str
    url: str
    title: str
    old_price: Optional[float]
    new_price: Optional[float]
    old_in_stock: Optional[bool]
    new_in_stock: bool
    target_price: Optional[float]
    changed: bool
    target_hit: bool


def build_price_event(
    *,
    product_name: str,
    url: str,
    marketplace: str,
    target_price: Optional[float],
    previous: Optional[Dict[str, Any]],
    scraped: ScrapedProduct,
) -> PriceEvent:
    """Diff a fresh scrape against prior state and produce a PriceEvent.

    `changed` covers a price move or a stock-status flip. `target_hit`
    covers the price crossing at/below target for the first time -- it
    does not keep firing on every later scrape while still under target.
    A first-ever scrape (no previous state) is never `changed`/`target_hit`;
    it only establishes a baseline for future comparisons.
    """
    old_price = previous.get("price") if previous else None
    old_in_stock = previous.get("in_stock") if previous else None

    if previous is None:
        changed = False
        target_hit = False
    else:
        price_changed = old_price != scraped.price
        stock_changed = old_in_stock != scraped.in_stock

        previously_hit = (
            target_price is not None
            and old_price is not None
            and old_price <= target_price
        )
        target_hit = (
            target_price is not None
            and scraped.price is not None
            and scraped.price <= target_price
            and not previously_hit
        )
        changed = price_changed or stock_changed

    return PriceEvent(
        product=product_name,
        marketplace=marketplace,
        url=url,
        title=scraped.title,
        old_price=old_price,
        new_price=scraped.price,
        old_in_stock=old_in_stock,
        new_in_stock=scraped.in_stock,
        target_price=target_price,
        changed=changed,
        target_hit=target_hit,
    )

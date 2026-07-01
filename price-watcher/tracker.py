from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from notifier import PriceChangeEvent, TelegramNotifier
from scrapers import ScrapedProduct, get_scraper_for_url
from utils import retry_with_backoff

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = BASE_DIR / "products.json"
STATE_FILE = BASE_DIR / "state.json"

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 2.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("price_watcher")


def load_products() -> List[Dict[str, Any]]:
    """Load the list of tracked products from products.json."""
    if not PRODUCTS_FILE.exists():
        logger.warning("products.json not found at %s", PRODUCTS_FILE)
        return []
    with PRODUCTS_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_state() -> Dict[str, Any]:
    """Load previously recorded product state from state.json."""
    if not STATE_FILE.exists():
        return {}
    with STATE_FILE.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError:
            logger.warning("state.json contains invalid JSON; starting fresh")
            return {}


def save_state(state: Dict[str, Any]) -> None:
    """Persist the latest known product state to state.json."""
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


async def scrape_product(page: Page, url: str) -> ScrapedProduct:
    """Detect the marketplace for a URL and scrape it, retrying on failure."""
    scraper = get_scraper_for_url(url)
    if scraper is None:
        raise ValueError(f"No scraper registered for URL: {url}")

    async def attempt() -> ScrapedProduct:
        return await scraper.scrape(page, url)

    return await retry_with_backoff(
        attempt,
        retries=RETRY_ATTEMPTS,
        base_delay=RETRY_BASE_DELAY_SECONDS,
        label=f"scrape[{scraper.marketplace_name}] {url}",
    )


def has_meaningful_change(
    previous: Optional[Dict[str, Any]],
    current: ScrapedProduct,
    target_price: Optional[float],
) -> bool:
    """Decide whether the new scrape differs enough from history to notify.

    Triggers on a price change, a stock-status change, or the price
    crossing at or below the user's target for the first time. A first-ever
    scrape (no previous state) only records a baseline; it never notifies.
    """
    if previous is None:
        return False

    price_changed = previous.get("price") != current.price
    stock_changed = previous.get("in_stock") != current.in_stock

    previously_reached = (
        target_price is not None
        and previous.get("price") is not None
        and previous.get("price") <= target_price
    )
    newly_reached = (
        target_price is not None
        and current.price is not None
        and current.price <= target_price
        and not previously_reached
    )

    return price_changed or stock_changed or newly_reached


async def process_product(
    page: Page,
    product: Dict[str, Any],
    state: Dict[str, Any],
    notifier: TelegramNotifier,
) -> None:
    """Scrape one product, compare it against stored state, and notify on change."""
    url = product["url"]
    name = product.get("name") or url
    target_price = product.get("target_price")

    try:
        current = await scrape_product(page, url)
    except Exception:
        logger.exception("Giving up on '%s' after %d attempts", name, RETRY_ATTEMPTS)
        return

    previous = state.get(url)

    if has_meaningful_change(previous, current, target_price):
        scraper = get_scraper_for_url(url)
        event = PriceChangeEvent(
            name=name,
            marketplace=scraper.marketplace_name if scraper else "Unknown",
            url=url,
            old_price=previous.get("price") if previous else None,
            new_price=current.price,
            old_in_stock=previous.get("in_stock") if previous else None,
            new_in_stock=current.in_stock,
            target_price=target_price,
        )
        await notifier.notify(event)
        logger.info("Change detected for '%s' -> notification sent", name)
    else:
        logger.info("No significant change for '%s' (price=%s)", name, current.price)

    state[url] = {
        "name": name,
        "title": current.title,
        "price": current.price,
        "in_stock": current.in_stock,
    }


async def track_prices() -> None:
    """Entry point: scrape every tracked product and notify on any change."""
    products = load_products()
    if not products:
        logger.info("No products configured in products.json; nothing to do")
        return

    state = load_state()
    notifier = TelegramNotifier()
    if not notifier.is_configured:
        logger.warning(
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured; "
            "notifications will be skipped this run"
        )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            # Products are scraped one at a time on a shared page to keep
            # traffic to each marketplace low and avoid tripping bot
            # detection. This is a deliberate tradeoff of speed for reliability.
            for product in products:
                await process_product(page, product, state, notifier)
        finally:
            await context.close()
            await browser.close()

    save_state(state)
    logger.info("Tracking run complete (%d product(s) processed)", len(products))


if __name__ == "__main__":
    asyncio.run(track_prices())

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from datetime import datetime

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from events import PriceEvent, build_price_event
from notifier import TelegramNotifier
from scrapers import BaseScraper, ScrapedProduct, get_scraper_for_url
from state_store import StateStore
from utils import retry_with_backoff

# Timezone used to decide when a new day starts for the once-daily summary.
SUMMARY_TIMEZONE = ZoneInfo("Asia/Kolkata")

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = BASE_DIR / "products.json"
STATE_FILE = BASE_DIR / "state.json"

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 2.0
DELAY_BETWEEN_PRODUCTS_SECONDS = 5.0

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


async def scrape_with_retry(scraper: BaseScraper, page: Page, url: str) -> ScrapedProduct:
    """Run a scraper's scrape() with exponential-backoff retries."""

    async def attempt() -> ScrapedProduct:
        return await scraper.scrape(page, url)

    return await retry_with_backoff(
        attempt,
        retries=RETRY_ATTEMPTS,
        base_delay=RETRY_BASE_DELAY_SECONDS,
        label=f"scrape[{scraper.marketplace_name}] {url}",
    )


async def process_product(
    page: Page,
    product: Dict[str, Any],
    state_store: StateStore,
    notifier: TelegramNotifier,
) -> Optional[PriceEvent]:
    """Run one product through the pipeline:

    Marketplace Resolver -> Scraper -> Price Event -> Notifier -> State Store

    Returns the PriceEvent on success (used to build the daily summary), or
    None if the product couldn't be scraped this run.
    """
    url = product["url"]
    name = product.get("name") or url
    target_price = product.get("target_price")

    # Marketplace Resolver
    scraper = get_scraper_for_url(url)
    if scraper is None:
        logger.warning("No scraper registered for URL: %s", url)
        return None

    # Scraper
    try:
        scraped = await scrape_with_retry(scraper, page, url)
    except Exception:
        logger.exception("Giving up on '%s' after %d attempts", name, RETRY_ATTEMPTS)
        return None

    logger.info(
        "Scraped '%s' via %s: price=%s, in_stock=%s, title=%r",
        name, scraper.marketplace_name, scraped.price, scraped.in_stock, scraped.title,
    )

    # Price Event
    event = build_price_event(
        product_name=name,
        url=url,
        marketplace=scraper.marketplace_name,
        target_price=target_price,
        previous=state_store.get(url),
        scraped=scraped,
    )

    # Notifier (decides internally whether the event warrants an alert)
    await notifier.handle(event)

    # State Store
    state_store.update(
        url,
        name=name,
        title=scraped.title,
        price=scraped.price,
        in_stock=scraped.in_stock,
    )

    return event


async def track_prices() -> None:
    """Entry point: load products and run every one through the pipeline."""
    products = load_products()
    if not products:
        logger.info("No products configured in products.json; nothing to do")
        return

    state_store = StateStore(STATE_FILE)
    notifier = TelegramNotifier()
    if not notifier.is_configured:
        logger.warning(
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured; "
            "notifications will be skipped this run"
        )

    async with async_playwright() as playwright:
        # Amazon/Flipkart bot-check on obvious automation fingerprints, so
        # the launch/context options below aim to look like a normal desktop
        # Chrome session (real viewport, locale/timezone, no automation
        # banner, no navigator.webdriver flag) rather than a bare headless
        # browser. This reduces false positives but is not a guarantee --
        # sophisticated bot detection may still block datacenter IPs outright.
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        events: List[PriceEvent] = []
        try:
            # Products are scraped one at a time on a shared page, with a
            # pause between each, to keep traffic to each marketplace low.
            # Bursting straight through several product URLs in a row is
            # exactly what tripped Flipkart's rate-based IP block during
            # testing -- spacing requests out is cheap insurance against it.
            for index, product in enumerate(products):
                if index > 0:
                    await asyncio.sleep(DELAY_BETWEEN_PRODUCTS_SECONDS)
                event = await process_product(page, product, state_store, notifier)
                if event is not None:
                    events.append(event)
        finally:
            await context.close()
            await browser.close()

    # Once-a-day digest of every product's current price/availability, on
    # top of handle()'s change-triggered alerts. Only claims today's slot
    # if we actually have something to report, so a run where every scrape
    # failed doesn't burn the day's summary for a later, successful run.
    today = datetime.now(SUMMARY_TIMEZONE).date().isoformat()
    if events and state_store.get_last_daily_summary_date() != today:
        await notifier.send_daily_summary(events)
        state_store.set_last_daily_summary_date(today)

    state_store.save()
    logger.info("Tracking run complete (%d product(s) processed)", len(products))


if __name__ == "__main__":
    asyncio.run(track_prices())

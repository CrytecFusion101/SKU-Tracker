from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ScrapeError(Exception):
    """Raised when a scrape didn't yield usable data (blocked, layout change,
    slow page, etc). Callers should treat this like any other scrape failure
    -- it's what makes retry_with_backoff actually retry instead of the
    tracker silently persisting a price of None as if it were real data.
    """


@dataclass
class ScrapedProduct:
    """Normalized result every scraper implementation returns to the tracker."""

    title: str
    price: Optional[float]
    in_stock: bool
    currency: str = "INR"


class BaseScraper(ABC):
    """Common interface every marketplace scraper must implement.

    Navigation and the overall scrape flow live here so they only need to be
    written once. Subclasses only provide marketplace-specific selectors and
    parsing logic, which keeps the scraper interface easy to extend: adding a
    new marketplace just means subclassing this and filling in the three
    extraction methods below.
    """

    #: Human readable marketplace name, used in notifications and logs.
    marketplace_name: str = "generic"

    #: Domain fragments used to auto-detect this scraper from a product URL.
    domains: Tuple[str, ...] = ()

    #: Whether this marketplace hides the price entirely once a product is
    #: out of stock. Amazon does (no buybox price at all, so any selector
    #: match found while out of stock is noise from an unrelated
    #: recommendation widget elsewhere on the page). Flipkart doesn't -- it
    #: keeps showing the price next to a "Notify Me" button -- so leave this
    #: False there and let _extract_price run normally either way.
    hides_price_when_out_of_stock: bool = False

    async def scrape(self, page: Page, url: str) -> ScrapedProduct:
        """Navigate to the product URL and return normalized product data."""
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self._wait_for_content(page)

        title = await self._extract_title(page)
        in_stock = await self._extract_availability(page)

        if not in_stock and self.hides_price_when_out_of_stock:
            price = None
        else:
            price = await self._extract_price(page)

        if price is None and in_stock:
            # Missing price while the page claims the product is in stock is
            # suspicious -- likely a blocked/bot-check page or a layout
            # change, not a genuine data gap. Treat it as a failed scrape so
            # retry_with_backoff retries and the tracker skips persisting
            # this result, rather than committing junk to state.json.
            await self._log_page_diagnostics(page, url)
            raise ScrapeError(f"{self.marketplace_name}: could not extract a price from {url}")

        return ScrapedProduct(title=title, price=price, in_stock=in_stock)

    def shorten_url(self, url: str) -> str:
        """Return a short, display-friendly version of a product URL for use
        in notifications. The default strips query params/fragment, keeping
        just the path -- marketplaces whose path alone isn't a stable link
        (e.g. one that depends on a query param to pick a specific variant)
        should override this.
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    async def _wait_for_content(self, page: Page) -> None:
        """Optional hook subclasses can override to wait for dynamic content."""
        return None

    async def _log_page_diagnostics(self, page: Page, url: str) -> None:
        """Best-effort logging of what actually rendered on a failed scrape.

        Once this runs on a remote host (e.g. Railway) there's no way to
        inspect the page directly, so a failure needs to be tellable apart
        -- from the logs alone -- as a bot-check/captcha page versus a
        genuine site layout change.
        """
        try:
            page_title = await page.title()
            body_text = await page.locator("body").inner_text(timeout=5000)
            snippet = " ".join(body_text.split())[:300]
            logger.warning(
                "%s diagnostic for %s -- page title: %r, body snippet: %r",
                self.marketplace_name, url, page_title, snippet,
            )
        except Exception:
            logger.warning("%s diagnostic capture failed for %s", self.marketplace_name, url)

    @abstractmethod
    async def _extract_title(self, page: Page) -> str:
        """Return the product title. Selectors must live only in the subclass."""

    @abstractmethod
    async def _extract_price(self, page: Page) -> Optional[float]:
        """Return the current price, or None if it can't be found/parsed."""

    @abstractmethod
    async def _extract_availability(self, page: Page) -> bool:
        """Return True if the product currently appears to be in stock."""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page

from .base import BaseScraper

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """Scraper for Amazon India (and .com) product pages."""

    marketplace_name = "Amazon"
    domains = ("amazon.in", "amazon.com")

    # Amazon renders the price in different DOM shapes depending on deal
    # type (buy box, lightning deal, coupon, etc). Selectors are tried in
    # order and the first match wins.
    _PRICE_SELECTORS = (
        "span.a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        ".a-price-whole",
    )
    _TITLE_SELECTOR = "#productTitle"
    _AVAILABILITY_SELECTOR = "#availability span"

    # A locator timeout for calls made *after* _wait_for_content has already
    # given the page a chance to load. If the content isn't there by then,
    # waiting another full default timeout (30s) per call just wastes time
    # across 3 retries x N products.
    _FAST_TIMEOUT_MS = 5000

    async def _wait_for_content(self, page: Page) -> None:
        try:
            await page.wait_for_selector(self._TITLE_SELECTOR, timeout=10000)
            return
        except Exception:
            # Page may still be usable (e.g. captcha, layout variant); let
            # the individual extractors fail gracefully instead of aborting.
            logger.warning("Amazon title selector did not appear in time")

        await self._try_dismiss_interstitial(page)

    async def _try_dismiss_interstitial(self, page: Page) -> None:
        """Click through Amazon's "Click the button below to continue
        shopping" page if present. It's a plain click-through, not a
        CAPTCHA, so it's worth one attempt before giving up on this page.
        """
        try:
            continue_button = page.get_by_role(
                "button", name=re.compile("continue shopping", re.IGNORECASE)
            )
            if await continue_button.count() == 0:
                return
            logger.info("Amazon interstitial detected; attempting to click through")
            await continue_button.first.click(timeout=self._FAST_TIMEOUT_MS)
            await page.wait_for_selector(self._TITLE_SELECTOR, timeout=10000)
        except Exception:
            logger.warning("Amazon interstitial click-through did not reveal product content")

    async def _extract_title(self, page: Page) -> str:
        try:
            text = await page.locator(self._TITLE_SELECTOR).first.text_content(
                timeout=self._FAST_TIMEOUT_MS
            )
            return text.strip() if text else "Unknown product"
        except Exception:
            logger.warning("Failed to extract Amazon title")
            return "Unknown product"

    async def _extract_price(self, page: Page) -> Optional[float]:
        for selector in self._PRICE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                text = await locator.text_content(timeout=self._FAST_TIMEOUT_MS)
                price = self._parse_price(text)
                if price is not None:
                    return price
            except Exception:
                continue
        logger.warning("Could not locate a price element on Amazon page")
        return None

    async def _extract_availability(self, page: Page) -> bool:
        try:
            locator = page.locator(self._AVAILABILITY_SELECTOR)
            count = await locator.count()
            if count == 0:
                # No availability banner usually means the buy box (and
                # therefore the product) is available.
                return True

            # Amazon renders several spans in this block and several are
            # routinely empty -- the actual "Currently unavailable" message
            # can land in any of them, so .first alone is not reliable.
            # Check the combined text of all of them instead.
            combined = ""
            for i in range(count):
                text = await locator.nth(i).text_content(timeout=self._FAST_TIMEOUT_MS)
                combined += (text or "") + " "
            combined = combined.strip().lower()
            return "unavailable" not in combined and "out of stock" not in combined
        except Exception:
            return True

    def shorten_url(self, url: str) -> str:
        """Reduce to https://<host>/dp/<ASIN>, dropping tracking query params."""
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        if match:
            host = urlparse(url).netloc
            return f"https://{host}/dp/{match.group(1)}"
        return super().shorten_url(url)

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        """Extract a float from strings like '₹1,299.00'."""
        if not text:
            return None
        match = re.search(r"[\d,]+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except ValueError:
            return None

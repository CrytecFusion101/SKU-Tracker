from __future__ import annotations

import logging
import re
from typing import Optional

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

    async def _wait_for_content(self, page: Page) -> None:
        try:
            await page.wait_for_selector(self._TITLE_SELECTOR, timeout=10000)
        except Exception:
            # Page may still be usable (e.g. captcha, layout variant); let
            # the individual extractors fail gracefully instead of aborting.
            logger.warning("Amazon title selector did not appear in time")

    async def _extract_title(self, page: Page) -> str:
        try:
            text = await page.locator(self._TITLE_SELECTOR).first.text_content()
            return text.strip() if text else "Unknown product"
        except Exception:
            logger.warning("Failed to extract Amazon title", exc_info=True)
            return "Unknown product"

    async def _extract_price(self, page: Page) -> Optional[float]:
        for selector in self._PRICE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                text = await locator.text_content()
                price = self._parse_price(text)
                if price is not None:
                    return price
            except Exception:
                continue
        logger.warning("Could not locate a price element on Amazon page")
        return None

    async def _extract_availability(self, page: Page) -> bool:
        try:
            locator = page.locator(self._AVAILABILITY_SELECTOR).first
            if await locator.count() == 0:
                # No availability banner usually means the buy box (and
                # therefore the product) is available.
                return True
            text = (await locator.text_content() or "").strip().lower()
            return "unavailable" not in text and "out of stock" not in text
        except Exception:
            return True

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

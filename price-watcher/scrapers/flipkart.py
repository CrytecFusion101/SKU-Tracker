from __future__ import annotations

import logging
import re
from typing import Optional

from playwright.async_api import Page

from .base import BaseScraper

logger = logging.getLogger(__name__)


class FlipkartScraper(BaseScraper):
    """Scraper for Flipkart product pages."""

    marketplace_name = "Flipkart"
    domains = ("flipkart.com",)

    # Flipkart's class names are obfuscated/rotated periodically, so we keep
    # a short list of known-good fallbacks and try them in order.
    _TITLE_SELECTORS = (
        "span.VU-ZEz",
        "span.B_NuCI",
        "h1 span",
    )
    _PRICE_SELECTORS = (
        "div.Nx9bqj.CxhGGd",
        "div._30jeq3._16Jk6d",
        "div._30jeq3",
    )
    _OUT_OF_STOCK_SELECTORS = (
        "div._16FRp0",
        "div.Z8JjpR",
    )

    async def _wait_for_content(self, page: Page) -> None:
        try:
            await page.wait_for_selector(",".join(self._PRICE_SELECTORS), timeout=10000)
        except Exception:
            logger.warning("Flipkart price selector did not appear in time")

    async def _extract_title(self, page: Page) -> str:
        for selector in self._TITLE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                text = await locator.text_content()
                if text and text.strip():
                    return text.strip()
            except Exception:
                continue
        logger.warning("Failed to extract Flipkart title")
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
        logger.warning("Could not locate a price element on Flipkart page")
        return None

    async def _extract_availability(self, page: Page) -> bool:
        for selector in self._OUT_OF_STOCK_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    text = (await locator.text_content() or "").strip().lower()
                    if "sold out" in text or "out of stock" in text or "coming soon" in text:
                        return False
            except Exception:
                continue
        return True

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        """Extract a float from strings like '₹1,299'."""
        if not text:
            return None
        match = re.search(r"[\d,]+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0).replace(",", ""))
        except ValueError:
            return None

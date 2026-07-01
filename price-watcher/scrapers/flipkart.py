from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

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

    # Timeout for calls made after _wait_for_content already gave the page
    # a chance to settle -- avoids stacking another full default timeout
    # (30s) on top per call across 3 retries x N products.
    _FAST_TIMEOUT_MS = 5000

    # Flipkart's <title> tag reliably contains the product name even when
    # the on-page CSS classes are rotated, just with a boilerplate suffix.
    _TITLE_SUFFIX_PATTERN = re.compile(
        r"\s*(Online at Best Price(?: On Flipkart\.com)?|Price in India.*)\s*$",
        re.IGNORECASE,
    )

    # Fallback when none of _PRICE_SELECTORS match: Flipkart's variant
    # selector widget renders plain text like "256 GB ↓8% 82,900 ₹75,900"
    # for the currently selected variant, regardless of CSS class rotation.
    _VARIANT_PRICE_PATTERN = re.compile(r"↓\s*\d+%\s*[\d,]+\s*₹\s*([\d,]+)")

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
                text = await locator.text_content(timeout=self._FAST_TIMEOUT_MS)
                if text and text.strip():
                    return text.strip()
            except Exception:
                continue

        try:
            page_title = await page.title()
            cleaned = self._TITLE_SUFFIX_PATTERN.sub("", page_title).strip()
            if cleaned:
                return cleaned
        except Exception:
            pass

        logger.warning("Failed to extract Flipkart title")
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

        try:
            body_text = await page.locator("body").inner_text(timeout=self._FAST_TIMEOUT_MS)
            match = self._VARIANT_PRICE_PATTERN.search(body_text)
            if match:
                return float(match.group(1).replace(",", ""))
        except Exception:
            pass

        logger.warning("Could not locate a price element on Flipkart page")
        return None

    async def _extract_availability(self, page: Page) -> bool:
        for selector in self._OUT_OF_STOCK_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    text = (await locator.text_content(timeout=self._FAST_TIMEOUT_MS) or "").strip().lower()
                    if "sold out" in text or "out of stock" in text or "coming soon" in text:
                        return False
            except Exception:
                continue
        return True

    def shorten_url(self, url: str) -> str:
        """Keep the path plus `pid` (it selects the specific color/storage
        variant) but drop tracking-only params like lid/marketplace/fm.
        """
        parsed = urlparse(url)
        pid = parse_qs(parsed.query).get("pid", [None])[0]
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return f"{base}?pid={pid}" if pid else base

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

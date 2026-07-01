from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple

from playwright.async_api import Page

logger = logging.getLogger(__name__)


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

    async def scrape(self, page: Page, url: str) -> ScrapedProduct:
        """Navigate to the product URL and return normalized product data."""
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self._wait_for_content(page)

        title = await self._extract_title(page)
        price = await self._extract_price(page)
        in_stock = await self._extract_availability(page)

        return ScrapedProduct(title=title, price=price, in_stock=in_stock)

    async def _wait_for_content(self, page: Page) -> None:
        """Optional hook subclasses can override to wait for dynamic content."""
        return None

    @abstractmethod
    async def _extract_title(self, page: Page) -> str:
        """Return the product title. Selectors must live only in the subclass."""

    @abstractmethod
    async def _extract_price(self, page: Page) -> Optional[float]:
        """Return the current price, or None if it can't be found/parsed."""

    @abstractmethod
    async def _extract_availability(self, page: Page) -> bool:
        """Return True if the product currently appears to be in stock."""

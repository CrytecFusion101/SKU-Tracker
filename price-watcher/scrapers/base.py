from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """Base interface for all price scrapers."""

    @abstractmethod
    def fetch_price(self, product_url: str) -> float:
        """Return the current price for the given product URL."""
        raise NotImplementedError

    @abstractmethod
    def get_name(self) -> str:
        """Return the scraper name."""
        raise NotImplementedError

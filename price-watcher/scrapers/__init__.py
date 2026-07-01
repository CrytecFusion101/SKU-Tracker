from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse

from .amazon import AmazonScraper
from .base import BaseScraper, ScrapedProduct
from .flipkart import FlipkartScraper

# Registry of available scrapers. Adding support for a new marketplace only
# requires implementing BaseScraper in its own module and listing an
# instance here -- nothing else in the codebase needs to change.
SCRAPERS: List[BaseScraper] = [
    AmazonScraper(),
    FlipkartScraper(),
]


def get_scraper_for_url(url: str) -> Optional[BaseScraper]:
    """Auto-detect which scraper handles a given product URL by hostname."""
    hostname = urlparse(url).hostname or ""
    for scraper in SCRAPERS:
        if any(domain in hostname for domain in scraper.domains):
            return scraper
    return None


__all__ = ["BaseScraper", "ScrapedProduct", "SCRAPERS", "get_scraper_for_url"]

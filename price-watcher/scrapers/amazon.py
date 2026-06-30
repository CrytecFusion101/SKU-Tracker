from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper


class AmazonScraper(BaseScraper):
    def get_name(self) -> str:
        return "amazon"

    def fetch_price(self, product_url: str) -> float:
        response = requests.get(product_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        price_text = None

        for candidate in soup.select("span.a-price .a-offscreen"):
            price_text = candidate.get_text(strip=True)
            break

        if not price_text:
            raise ValueError("Could not find Amazon price")

        match = re.search(r"([0-9,]+(?:\.[0-9]+)?)", price_text)
        if not match:
            raise ValueError("Could not parse Amazon price")

        return float(match.group(1).replace(",", ""))

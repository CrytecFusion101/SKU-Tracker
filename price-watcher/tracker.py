from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scrapers.amazon import AmazonScraper
from scrapers.flipkart import FlipkartScraper

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = BASE_DIR / "products.json"
STATE_FILE = BASE_DIR / "state.json"

SCRAPERS = {
    "amazon": AmazonScraper(),
    "flipkart": FlipkartScraper(),
}


def load_json(path: Path) -> Any:
    if not path.exists():
        return [] if path.name == "products.json" else {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def track_prices() -> None:
    products = load_json(PRODUCTS_FILE)
    state = load_json(STATE_FILE)

    for product in products:
        scraper = SCRAPERS.get(product.get("store"))
        if not scraper:
            continue

        price = scraper.fetch_price(product["url"])
        state[product["sku"]] = {
            "price": price,
            "store": product.get("store"),
            "url": product["url"],
        }

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    track_prices()

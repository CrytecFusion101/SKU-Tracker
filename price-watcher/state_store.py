from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Reserved key for cross-cutting metadata (e.g. last daily summary date),
# stored alongside the per-URL entries. Safe from collisions since product
# URLs always start with "https://".
_META_KEY = "__meta__"


class StateStore:
    """Persists last-known scrape results to a JSON file, keyed by product URL.

    This is the final pipeline stage: it only records what a scrape found,
    independent of whether the notifier considered it worth alerting on.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as handle:
            try:
                return json.load(handle)
            except json.JSONDecodeError:
                logger.warning("%s contains invalid JSON; starting fresh", self._path)
                return {}

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Return the last recorded state for a product URL, or None if unseen."""
        return self._data.get(url)

    def update(
        self,
        url: str,
        *,
        name: str,
        title: str,
        price: Optional[float],
        in_stock: bool,
    ) -> None:
        """Record the latest scrape result for a product URL."""
        self._data[url] = {"name": name, "title": title, "price": price, "in_stock": in_stock}

    def get_last_daily_summary_date(self) -> Optional[str]:
        """Return the ISO date (YYYY-MM-DD) the daily summary last went out."""
        return self._data.get(_META_KEY, {}).get("last_daily_summary_date")

    def set_last_daily_summary_date(self, date_str: str) -> None:
        """Record that the daily summary was sent for the given ISO date."""
        self._data.setdefault(_META_KEY, {})["last_daily_summary_date"] = date_str

    def save(self) -> None:
        """Flush all recorded state to disk."""
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)

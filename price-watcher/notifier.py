from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


@dataclass
class PriceChangeEvent:
    """Everything needed to render a single Telegram notification."""

    name: str
    marketplace: str
    url: str
    old_price: Optional[float]
    new_price: Optional[float]
    old_in_stock: Optional[bool]
    new_in_stock: bool
    target_price: Optional[float]


class TelegramNotifier:
    """Sends formatted price-change alerts to a Telegram chat via Bot API."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def notify(self, event: PriceChangeEvent) -> None:
        """Format and send a notification without blocking the event loop."""
        if not self.is_configured:
            logger.warning(
                "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set; skipping notification for %s",
                event.name,
            )
            return

        message = self._format_message(event)
        try:
            await asyncio.to_thread(self._send, message)
            logger.info("Telegram notification sent for %s", event.name)
        except Exception:
            logger.exception("Failed to send Telegram notification for %s", event.name)

    def _send(self, message: str) -> None:
        """Blocking HTTP call to the Telegram Bot API; run via asyncio.to_thread."""
        url = TELEGRAM_API_URL.format(token=self.bot_token)
        response = requests.post(
            url,
            json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        response.raise_for_status()

    def _format_message(self, event: PriceChangeEvent) -> str:
        """Build the Telegram message body in the required notification format."""
        lines = [
            f"<b>{event.name}</b>",
            f"Marketplace: {event.marketplace}",
            "",
        ]

        if event.old_price is not None:
            lines.append(f"Old Price: ₹{event.old_price:,.2f}")
        else:
            lines.append("Old Price: N/A (first time tracked)")

        if event.new_price is not None:
            lines.append(f"New Price: ₹{event.new_price:,.2f}")
        else:
            lines.append("New Price: Unavailable")

        if event.old_price is not None and event.new_price is not None:
            diff = event.new_price - event.old_price
            if diff > 0:
                direction = "increased"
            elif diff < 0:
                direction = "decreased"
            else:
                direction = "unchanged"
            lines.append(f"Difference: ₹{abs(diff):,.2f} ({direction})")

        if event.old_in_stock is not None and event.old_in_stock != event.new_in_stock:
            status = "In Stock" if event.new_in_stock else "Out of Stock"
            lines.append(f"Stock status changed: {status}")

        if (
            event.target_price is not None
            and event.new_price is not None
            and event.new_price <= event.target_price
        ):
            lines.append("")
            lines.append(f"Target reached! (Target: ₹{event.target_price:,.2f})")

        lines.append("")
        lines.append(event.url)

        return "\n".join(lines)

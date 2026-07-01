from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import requests

from events import PriceEvent

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Notifier pipeline stage: decides whether a PriceEvent is worth an
    alert, formats it, and sends it to a Telegram chat via the Bot API.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def handle(self, event: PriceEvent) -> None:
        """Entry point for every scrape's PriceEvent; only alerts when warranted."""
        if not (event.changed or event.target_hit):
            logger.info("No significant change for '%s'; skipping notification", event.product)
            return

        if not self.is_configured:
            logger.warning(
                "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set; skipping notification for %s",
                event.product,
            )
            return

        message = self._format_message(event)
        try:
            await asyncio.to_thread(self._send, message)
            logger.info("Telegram notification sent for %s", event.product)
        except Exception:
            logger.exception("Failed to send Telegram notification for %s", event.product)

    def _send(self, message: str) -> None:
        """Blocking HTTP call to the Telegram Bot API; run via asyncio.to_thread."""
        url = TELEGRAM_API_URL.format(token=self.bot_token)
        response = requests.post(
            url,
            json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        response.raise_for_status()

    def _format_message(self, event: PriceEvent) -> str:
        """Build the Telegram message body in the required notification format."""
        lines = [
            f"<b>{event.product}</b>",
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

        if event.target_hit and event.target_price is not None:
            lines.append("")
            lines.append(f"Target reached! (Target: ₹{event.target_price:,.2f})")

        lines.append("")
        lines.append(event.url)

        return "\n".join(lines)

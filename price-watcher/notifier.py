from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

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

    async def send_daily_summary(self, events: List[PriceEvent]) -> None:
        """Send one digest per day covering every product's current price
        and availability, regardless of whether anything changed. This is
        separate from handle()'s change-triggered alerts -- it's a
        "here's where things stand" check-in rather than a notable event.
        """
        if not events:
            return

        if not self.is_configured:
            logger.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set; skipping daily summary")
            return

        message = self._format_daily_summary(events)
        try:
            await asyncio.to_thread(self._send, message)
            logger.info("Daily summary sent for %d product(s)", len(events))
        except Exception:
            logger.exception("Failed to send daily summary")

    def _send(self, message: str) -> None:
        """Blocking HTTP call to the Telegram Bot API; run via asyncio.to_thread."""
        url = TELEGRAM_API_URL.format(token=self.bot_token)
        response = requests.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        response.raise_for_status()

    def _format_message(self, event: PriceEvent) -> str:
        """Build the Telegram message body for a change-triggered alert."""
        lines = [f"📦 <b>{event.product}</b>", f"🏬 {event.marketplace}", ""]

        if event.new_price is None:
            lines.append("💰 Price unavailable")
        elif event.old_price is None:
            lines.append(f"💰 ₹{event.new_price:,.0f}")
        else:
            lines.append(f"💰 ₹{event.old_price:,.0f} → ₹{event.new_price:,.0f}")
            diff = event.new_price - event.old_price
            if diff:
                pct = abs(diff) / event.old_price * 100 if event.old_price else 0
                arrow, verb = ("📉", "cheaper") if diff < 0 else ("📈", "pricier")
                lines.append(f"{arrow} ₹{abs(diff):,.0f} {verb} ({pct:.1f}%)")

        if event.old_in_stock is not None and event.old_in_stock != event.new_in_stock:
            stock_emoji = "🟢" if event.new_in_stock else "🔴"
            stock_text = "In Stock" if event.new_in_stock else "Out of Stock"
            lines.append("")
            lines.append(f"🔄 Stock: {stock_emoji} {stock_text}")

        if event.target_hit and event.target_price is not None:
            lines.append("")
            lines.append(f"🎯 Target Reached! (₹{event.target_price:,.0f})")

        lines.append("")
        lines.append(f'🔗 <a href="{event.url}">Link</a>')

        return "\n".join(lines)

    def _format_daily_summary(self, events: List[PriceEvent]) -> str:
        """Build the once-a-day digest: current price/availability per product."""
        lines = ["📊 <b>Price Watcher — Daily Summary</b>", ""]

        for event in events:
            stock_emoji = "🟢" if event.new_in_stock else "🔴"
            stock_text = "In Stock" if event.new_in_stock else "Out of Stock"
            price_str = f"₹{event.new_price:,.0f}" if event.new_price is not None else "Unavailable"

            lines.append(f"📦 <b>{event.product}</b> ({event.marketplace})")
            lines.append(f"💰 {price_str} | {stock_emoji} {stock_text}")
            if event.target_price is not None:
                lines.append(f"🎯 Target: ₹{event.target_price:,.0f}")
            lines.append(f'🔗 <a href="{event.url}">Link</a>')
            lines.append("")

        return "\n".join(lines).rstrip()

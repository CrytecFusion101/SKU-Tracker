from __future__ import annotations

import os
from typing import Any

import requests


def send_notification(message: str) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    payload = {"content": message}
    requests.post(webhook_url, json=payload, timeout=10)

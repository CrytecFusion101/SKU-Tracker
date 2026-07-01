from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 2.0,
    label: str = "operation",
) -> T:
    """Run an async callable, retrying on failure with exponential backoff.

    Waits base_delay * 2**attempt seconds between attempts (2s, 4s, 8s, ...
    for the default base_delay). Re-raises the final exception once all
    retries are exhausted so the caller can decide how to handle it.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return await func()
        except Exception as exc:
            last_exc = exc
            logger.warning("%s failed (attempt %d/%d): %s", label, attempt, retries, exc)
            if attempt < retries:
                delay = base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc

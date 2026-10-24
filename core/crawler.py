import random
import time
import asyncio
import logging
from core.config import settings

logger = logging.getLogger("crawler")

def dynamic_delay_sync(min_s: float = None, max_s: float = None) -> float:
    """Thread-safe dynamic jitter delay between crawling HTTP requests."""
    min_val = min_s if min_s is not None else settings.crawler_delay_min
    max_val = max_s if max_s is not None else settings.crawler_delay_max
    if max_val < min_val:
        max_val = min_val
    delay = random.uniform(min_val, max_val)
    if delay > 0:
        time.sleep(delay)
    return delay

async def dynamic_delay_async(min_s: float = None, max_s: float = None) -> float:
    """Async dynamic jitter delay between crawling HTTP requests."""
    min_val = min_s if min_s is not None else settings.crawler_delay_min
    max_val = max_s if max_s is not None else settings.crawler_delay_max
    if max_val < min_val:
        max_val = min_val
    delay = random.uniform(min_val, max_val)
    if delay > 0:
        await asyncio.sleep(delay)
    return delay

def handle_rate_limit_backoff_sync(attempt: int, base_seconds: float = 3.0) -> float:
    """Exponential backoff when encountering rate limiting (429/403/captcha)."""
    backoff = base_seconds * (2 ** min(attempt, 4)) + random.uniform(0.5, 2.0)
    logger.warning(f"[Crawler Rate-Limit] Backing off for {backoff:.2f}s (attempt {attempt})...")
    time.sleep(backoff)
    return backoff

async def handle_rate_limit_backoff_async(attempt: int, base_seconds: float = 3.0) -> float:
    """Async exponential backoff when encountering rate limiting."""
    backoff = base_seconds * (2 ** min(attempt, 4)) + random.uniform(0.5, 2.0)
    logger.warning(f"[Crawler Rate-Limit] Async backing off for {backoff:.2f}s (attempt {attempt})...")
    await asyncio.sleep(backoff)
    return backoff

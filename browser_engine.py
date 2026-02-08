"""
Persistent session (browser_context) and stealth engine.
Use create_persistent_context(playwright_instance) inside Stealth().use_async() in main.
"""
import asyncio
import random
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import BrowserContext, Page

from config import HEADLESS, MAX_DELAY_SEC, MIN_DELAY_SEC, USER_DATA_DIR
from logger_config import logger


async def human_delay(min_sec: Optional[float] = None, max_sec: Optional[float] = None) -> None:
    """Random delay between min and max seconds to mimic human behavior."""
    lo = min_sec if min_sec is not None else MIN_DELAY_SEC
    hi = max_sec if max_sec is not None else MAX_DELAY_SEC
    delay = random.uniform(lo, hi)
    logger.debug("Human delay %.1fs", delay)
    await asyncio.sleep(delay)


def get_user_data_dir() -> str:
    """Resolve user data dir to absolute path (Playwright quirk with relative paths)."""
    path = Path(USER_DATA_DIR)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


async def create_persistent_context(playwright: Any) -> BrowserContext:
    """
    Create a persistent browser context (stores cookies/session to linkedin_user_data/).
    Pass the playwright instance from Stealth().use_async(async_playwright()) so stealth is applied.
    Does not log in every time — reuses existing LinkedIn session.
    """
    user_dir = get_user_data_dir()
    logger.info("Session will be saved to: %s", user_dir)
    context = await playwright.chromium.launch_persistent_context(
        user_dir,
        headless=HEADLESS,
        viewport={"width": 1280, "height": 900},
        locale="fr-FR",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-extensions",
        ],
    )
    return context


async def close_context(context: BrowserContext) -> None:
    """Close context (playwright lifecycle is tied to Stealth context manager in main)."""
    try:
        await context.close()
    except Exception as e:
        logger.warning("Error closing context: %s", e)


async def safe_click_with_delay(page: Page, selector: str, timeout_ms: int = 15000) -> bool:
    """Click element after human delay. Returns True if clicked, False on failure."""
    await human_delay()
    try:
        await page.click(selector, timeout=timeout_ms)
        return True
    except Exception as e:
        logger.warning("Click failed for %s: %s", selector, e)
        return False


async def safe_fill_with_delay(
    page: Page, selector: str, value: str, timeout_ms: int = 15000
) -> bool:
    """Fill input after human delay. Returns True if filled, False on failure."""
    await human_delay()
    try:
        await page.fill(selector, value, timeout=timeout_ms)
        return True
    except Exception as e:
        logger.warning("Fill failed for %s: %s", selector, e)
        return False

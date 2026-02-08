"""
Smart scraper: navigate job search, select first job. No pauses.
"""
import asyncio
from typing import List, Tuple

from playwright.async_api import Page

from browser_engine import human_delay
from config import LINKEDIN_JOB_SEARCH_URL
from logger_config import logger

# Selectors for job list and Easy Apply (French: Candidature Simplifiée)
JOB_CARD_SELECTOR = "div.job-card-container, li.jobs-search-results__list-item, [data-job-id]"
EASY_APPLY_BUTTON_TEXT = "Candidature simplifiée"
EASY_APPLY_BUTTON_ALT = "Easy Apply"
JOB_LIST_SCROLL_SELECTOR = ".jobs-search-results-list, .scaffold-layout__list-container, [role='list']"


async def navigate_to_job_search(page: Page) -> bool:
    """Navigate to LinkedIn job search (Easy Apply filter). No login pause—uses saved session."""
    try:
        await page.goto(LINKEDIN_JOB_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector(
            ".jobs-search-results-list, .scaffold-layout__list-container, ul.scaffold-layout__list-container, [data-job-id]",
            state="visible",
            timeout=45000,
        )
        return True
    except Exception as e:
        logger.exception("Failed to navigate to job search: %s", e)
        return False


# Job cards in the left list (LinkedIn uses li, div.job-card-container, or [data-job-id])
JOB_CARD_LIST_SELECTOR = (
    ".scaffold-layout__list-container li, "
    "ul.scaffold-layout__list-container li, "
    ".jobs-search-results-list li, "
    "li.jobs-search-results__list-item, "
    ".job-card-container, "
    "[data-job-id].job-card-container"
)
# Scope to left list only (avoid detail panel): list container then its cards
LIST_CONTAINER_SELECTOR = ".scaffold-layout__list-container, .jobs-search-results-list, ul.scaffold-layout__list-container"


async def _get_list_cards_locator(page: Page):
    """Return a locator for job cards scoped to the left list, with fallbacks."""
    # Prefer: list container -> then li or job-card inside it (avoids right-panel [data-job-id])
    try:
        container = page.locator(LIST_CONTAINER_SELECTOR).first
        scoped = container.locator("li, .job-card-container, [data-job-id]")
        n = await scoped.count()
        if n > 0:
            return scoped
    except Exception:
        pass
    # Fallback: global selector (same as select_first_job used to use)
    return page.locator(JOB_CARD_LIST_SELECTOR)


async def get_job_list_count(page: Page, max_count: int = 50) -> int:
    """Return the number of job cards currently in the list (capped at max_count)."""
    try:
        await asyncio.sleep(2)
        # Wait for at least one card to be visible (list may render after container)
        try:
            await page.wait_for_selector(
                ".scaffold-layout__list-container li, .job-card-container, li.jobs-search-results__list-item",
                state="visible",
                timeout=10000,
            )
        except Exception:
            pass
        loc = await _get_list_cards_locator(page)
        n = await loc.count()
        return min(max(n, 0), max_count)
    except Exception as e:
        logger.debug("get_job_list_count: %s", e)
        return 0


async def select_job_at_index(page: Page, index: int) -> bool:
    """Select the job at the given index (0-based) in the list. Click so it shows in the right panel."""
    try:
        loc = await _get_list_cards_locator(page)
        card = loc.nth(index)
        await card.scroll_into_view_if_needed(timeout=15000)
        await card.click(timeout=15000)
        logger.info("Selected job %s.", index + 1)
        return True
    except Exception as e:
        logger.warning("Could not select job at index %s: %s", index, e)
        return False


async def select_first_job(page: Page) -> bool:
    """Select the first job in the list (click so it shows in the right panel). No pauses."""
    return await select_job_at_index(page, 0)


# Filter pill (search UI) has this id — exclude it so we click only the apply button in the job detail panel
FILTER_PILL_ID = "searchFilter_applyWithLinkedin"


async def click_easy_apply_selected(page: Page) -> bool:
    """Click the 'Candidature simplifiée' apply button for the selected offer. Excludes the filter pill."""
    try:
        await asyncio.sleep(0.3)
        btn = page.locator(
            f"button:has-text('{EASY_APPLY_BUTTON_TEXT}'):not(#{FILTER_PILL_ID}), "
            f"button:has-text('{EASY_APPLY_BUTTON_ALT}'):not(#{FILTER_PILL_ID})"
        ).first
        await btn.scroll_into_view_if_needed(timeout=2000)  # ~2s then skip when no Easy Apply
        await btn.click(timeout=2000)
        logger.info("Clicked Candidature simplifiée for the selected offer.")
        return True
    except Exception as e:
        logger.warning("Could not click Candidature simplifiée: %s", e)
        return False


async def scroll_job_list(page: Page, max_scrolls: int = 5) -> None:
    """Scroll the job list to load more cards."""
    for i in range(max_scrolls):
        await human_delay(1, 3)
        try:
            await page.evaluate(
                """
                (sel) => {
                    const el = document.querySelector(sel);
                    if (el) el.scrollTop = el.scrollHeight;
                }
                """,
                JOB_LIST_SCROLL_SELECTOR,
            )
        except Exception as e:
            logger.debug("Scroll attempt %s: %s", i + 1, e)
        await human_delay(2, 4)


def _easy_apply_locator(page: Page):
    """Locator for Easy Apply / Candidature simplifiée buttons."""
    return page.get_by_role("button", name=EASY_APPLY_BUTTON_TEXT).or_(
        page.get_by_role("button", name=EASY_APPLY_BUTTON_ALT)
    ).or_(
        page.locator(f"button:has-text('{EASY_APPLY_BUTTON_TEXT}')")
    ).or_(
        page.locator(f"span:has-text('{EASY_APPLY_BUTTON_TEXT}')").locator("..")
    )


async def get_job_cards_with_easy_apply(page: Page) -> List[Tuple[str, str]]:
    """
    Collect job card elements that have an Easy Apply button (in DOM order).
    Note: the first job in the visible list may not have Easy Apply, so our first
    result can be the second (or later) list item—that's expected.
    Returns list of (job_card_selector_or_id, job_text_snippet) for later use.
    """
    await scroll_job_list(page)
    await human_delay(2, 5)

    # Find all Easy Apply buttons in DOM order (first result = first Easy Apply job, not necessarily first list item)
    easy_apply_buttons = await page.locator(
        f"button:has-text('{EASY_APPLY_BUTTON_TEXT}'), "
        f"button:has-text('{EASY_APPLY_BUTTON_ALT}'), "
        f"span:has-text('{EASY_APPLY_BUTTON_TEXT}')"
    ).all()

    results: List[Tuple[str, str]] = []
    seen = set()

    for btn in easy_apply_buttons:
        try:
            # Get parent job card to extract job text and avoid duplicates
            card = await btn.evaluate_handle(
                """el => {
                    let n = el;
                    for (let i = 0; i < 15 && n; i++) {
                        if (n.getAttribute?.('data-job-id') || n.classList?.contains?.('job-card-container')
                            || n.classList?.contains?.('jobs-search-results__list-item')) return n;
                        n = n.parentElement;
                    }
                    return el.closest?.('[data-job-id]') || el.closest?.('.job-card-container') || el;
                }"""
            )
            job_id = await card.evaluate("el => el.getAttribute?.('data-job-id') || el.innerText?.slice(0, 80) || ''")
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            job_text = await card.evaluate("el => el.innerText || ''")
            # Use data-job-id as stable identifier; fallback to snippet
            key = await card.evaluate("el => el.getAttribute?.('data-job-id') || el.innerText?.slice(0, 100) || ''")
            results.append((key, job_text[:3000]))
        except Exception as e:
            logger.debug("Skipping one Easy Apply button: %s", e)
    return results


async def click_easy_apply_on_card(page: Page, job_card_identifier: str) -> bool:
    """
    Locate the job card by identifier, scroll it into view, then click its Easy Apply button.
    job_card_identifier: data-job-id or text snippet from get_job_cards_with_easy_apply.
    """
    await human_delay()
    try:
        # Use data-job-id when the identifier looks like an ID (digits, or digits with hyphen)
        use_data_id = job_card_identifier.isdigit() or (
            len(job_card_identifier) <= 25 and job_card_identifier.replace("-", "").isdigit()
        )
        if use_data_id:
            card = page.locator(f"[data-job-id='{job_card_identifier}']").first
        else:
            card = page.locator(".job-card-container, .jobs-search-results__list-item").filter(
                has_text=job_card_identifier[:50]
            ).first
        await card.scroll_into_view_if_needed(timeout=10000)
        await human_delay(0.5, 1.5)
        btn = card.get_by_role("button", name=EASY_APPLY_BUTTON_TEXT).or_(
            card.get_by_role("button", name=EASY_APPLY_BUTTON_ALT)
        ).or_(card.locator(f"button:has-text('{EASY_APPLY_BUTTON_TEXT}')")).first
        await btn.click(timeout=15000)
        return True
    except Exception as e:
        logger.warning("Click Easy Apply failed for %s: %s", job_card_identifier[:50], e)
        return False

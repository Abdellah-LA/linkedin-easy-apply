"""
LinkedIn: open job search (Easy Apply filter), then loop over offers one by one in order.
For each: select job → Candidature simplifiée → fill contact + Suivant/Vérifier/Soumettre → next job.
"""
import asyncio
import sys
from typing import Optional

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from applier import close_easy_apply_modal, fill_contact_and_click_suivant, wait_for_easy_apply_modal_closed
from browser_engine import close_context, create_persistent_context
from daily_limit import page_has_daily_limit_message, show_daily_limit_popup
from logger_config import logger
from scraper import (
    click_easy_apply_selected,
    get_job_list_count,
    navigate_to_job_search,
    scroll_job_list,
    select_job_at_index,
)


async def _block_invalid_extension_route(route):
    if route.request.url.startswith("chrome-extension://"):
        await route.abort()
    else:
        await route.continue_()


async def main(
    *,
    state: Optional[dict] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> int:
    """Run the Easy Apply loop. Optional state dict is updated with applied_count and running."""
    if state is not None:
        state["running"] = True
        state["applied_count"] = 0
        state["error"] = None
    logger.info("Starting: Easy Apply loop — one offer after another in list order.")
    try:
        async with Stealth().use_async(async_playwright()) as p:
            context = await create_persistent_context(p)
            await context.route("**/*", _block_invalid_extension_route)
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                if not await navigate_to_job_search(page):
                    logger.error("Navigation failed; exiting")
                    return 1

                applied_total = 0
                round_no = 0

                while True:
                    if stop_event and stop_event.is_set():
                        logger.info("Stop requested; exiting loop.")
                        return 0
                    round_no += 1
                    count = await get_job_list_count(page)
                    if count == 0:
                        await scroll_job_list(page, max_scrolls=3)
                        await asyncio.sleep(3)
                        count = await get_job_list_count(page)
                    if count == 0:
                        logger.warning("No jobs in list. Scrolling to load more in 15s...")
                        await asyncio.sleep(15)
                        continue

                    logger.info("Round %s: found %s job(s). Applying one by one (Ctrl+C to stop).", round_no, count)
                    for i in range(count):
                        try:
                            if not await select_job_at_index(page, i):
                                continue
                            if await page_has_daily_limit_message(page):
                                logger.info("LinkedIn daily limit detected; stopping.")
                                show_daily_limit_popup()
                                return 0
                            if not await click_easy_apply_selected(page):
                                await close_easy_apply_modal(page)
                                continue
                            if await page_has_daily_limit_message(page):
                                logger.info("LinkedIn daily limit detected; stopping.")
                                await close_easy_apply_modal(page)
                                show_daily_limit_popup()
                                return 0
                            applied = await fill_contact_and_click_suivant(page)
                            if await page_has_daily_limit_message(page):
                                logger.info("LinkedIn daily limit detected; stopping.")
                                await close_easy_apply_modal(page)
                                show_daily_limit_popup()
                                return 0
                            if applied:
                                applied_total += 1
                                if state is not None:
                                    state["applied_count"] = applied_total
                                logger.info("Applied to job (total %s).", applied_total)
                            else:
                                await close_easy_apply_modal(page)
                        except Exception as e:
                            logger.warning("Skip job %s and continue: %s", i + 1, e)
                            await close_easy_apply_modal(page)
                        await wait_for_easy_apply_modal_closed(page)
                        await asyncio.sleep(0.6)
                        if stop_event and stop_event.is_set():
                            break

                    # Load more jobs for next round
                    if stop_event and stop_event.is_set():
                        break
                    await scroll_job_list(page, max_scrolls=5)
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e) or "closed" in str(e).lower():
                    logger.info("Browser closed. Applied to %s offer(s) in total.", applied_total)
                else:
                    raise
            finally:
                await close_context(context)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        if state is not None:
            state["error"] = str(e)
        return 1
    finally:
        if state is not None:
            state["running"] = False
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

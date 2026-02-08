"""
LinkedIn daily application limit: detect the message and show a user-friendly popup, then stop the script.
"""
import tempfile
import webbrowser
from pathlib import Path

from playwright.async_api import Page

from logger_config import logger

# French phrases from LinkedIn: "Nous limitons le nombre d'envois quotidiens... postulez demain."
DAILY_LIMIT_PHRASES = (
    "envois quotidiens",
    "limitons le nombre",
    "postulez demain",
    "enregistrez cette offre",
)

# Short, friendly message for the popup (any device/screen size)
POPUP_MESSAGE = (
    "LinkedIn daily limit reached. "
    "Save this job and try again tomorrow."
)
POPUP_TITLE = "Easy Apply — Daily limit"


async def page_has_daily_limit_message(page: Page) -> bool:
    """True if the page shows LinkedIn's daily application limit message."""
    try:
        text = await page.evaluate("() => (document.body?.innerText || '').toLowerCase()")
        if not text:
            return False
        for phrase in DAILY_LIMIT_PHRASES:
            if phrase in text:
                return True
    except Exception as e:
        logger.debug("Daily limit check failed: %s", e)
    return False


def show_daily_limit_popup() -> None:
    """
    Show a user-friendly popup (responsive HTML) with the daily limit message.
    Opens in the default browser so it works on any device/screen size.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{POPUP_TITLE}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #f3f6f8;
      padding: 1rem;
    }}
    .card {{
      max-width: 420px;
      width: 100%;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,.08);
      padding: 2rem;
      text-align: center;
    }}
    h1 {{
      margin: 0 0 1rem;
      font-size: 1.25rem;
      color: #0a66c2;
    }}
    p {{
      margin: 0;
      color: #333;
      line-height: 1.5;
      font-size: 1rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{POPUP_TITLE}</h1>
    <p>{POPUP_MESSAGE}</p>
  </div>
</body>
</html>
"""
    try:
        path = Path(tempfile.gettempdir()) / "linkedin_daily_limit.html"
        path.write_text(html, encoding="utf-8")
        webbrowser.open(path.as_uri())
        logger.info("Opened daily limit popup in browser.")
    except Exception as e:
        logger.warning("Could not open popup; message: %s — %s", POPUP_MESSAGE, e)

"""
Work authorization: detect citizenship / residency / legally authorized to work questions.
Always answer that the candidate is NOT authorized to work in the search country (needs sponsorship).
"""
import re
from typing import Optional

from config import (
    WORK_AUTHORIZATION_ANSWER,
    WORK_AUTHORIZATION_COUNTRY,
    WORK_NEED_SPONSORSHIP_ANSWER,
)
from logger_config import logger

# Phrases: "authorized to work / citizen" -> No (not authorized)
WORK_AUTH_PATTERNS = (
    r"citizenship",
    r"citizen of",
    r"authorized to work",
    r"legally (eligible|authorized) to work",
    r"right to work",
    r"resid(e|ency) in",
    r"currently (live|reside)",
    r"work (permit|authorization|visa)",
    r"citoyenneté",
    r"autorisé à travailler",
    r"résidence",
    r"work in (canada|usa|united states|uk|france)",
)
# "Do you need / require sponsorship?" / "parrainage d'immigration" -> use WORK_NEED_SPONSORSHIP_ANSWER
SPONSORSHIP_QUESTION_PATTERNS = (
    r"require.*sponsorship",
    r"need.*sponsorship",
    r"do you (need|require) sponsorship",
    r"sponsorship (required|needed)",
    r"sponsorship.*(employment)?.*visa",
    r"visa.*sponsorship",
    r"will you .* require sponsorship",
    r"sponsorship for employment visa",
    r"parrainage.*(immigration|autorisation|travail)",
    r"aur(ez|ez-vous).*parrainage",
)

# Country names to detect in question (lowercase)
COUNTRIES = ("canada", "usa", "united states", "uk", "france", "germany", "maroc", "morocco")


def _normalize(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").lower().strip())


def is_work_authorization_question(question_label: str, country_hint: str = "") -> bool:
    """True if the question is about citizenship, residency, or work authorization in a country."""
    if not question_label:
        return False
    text = _normalize(question_label)
    country = (country_hint or WORK_AUTHORIZATION_COUNTRY).lower()
    for pat in WORK_AUTH_PATTERNS:
        if re.search(pat, text):
            return True
    for c in COUNTRIES:
        if c in text and ("work" in text or "authorized" in text or "citizen" in text or "resid" in text):
            return True
    if country in text and ("work" in text or "authorized" in text or "citizen" in text or "resid" in text):
        return True
    return False


def get_work_authorization_answer(question_label: str) -> Optional[str]:
    """
    Return the answer for work authorization questions.
    - "Do you require sponsorship for employment visa?" -> Yes (WORK_NEED_SPONSORSHIP_ANSWER).
    - "Are you authorized to work in Canada?" / citizenship / residency -> No (WORK_AUTHORIZATION_ANSWER).
    """
    if not question_label:
        return None
    text = _normalize(question_label)
    # Match sponsorship/visa first — always Yes
    for pat in SPONSORSHIP_QUESTION_PATTERNS:
        if re.search(pat, text):
            logger.debug("Sponsorship question -> %s", WORK_NEED_SPONSORSHIP_ANSWER)
            return WORK_NEED_SPONSORSHIP_ANSWER
    # "sponsorship" or "visa" or "parrainage" in question about requiring it
    if "sponsorship" in text and ("require" in text or "need" in text or "future" in text):
        return WORK_NEED_SPONSORSHIP_ANSWER
    if "visa" in text and "sponsorship" in text:
        return WORK_NEED_SPONSORSHIP_ANSWER
    if "parrainage" in text and ("immigration" in text or "autorisation" in text or "travail" in text or "aurez" in text):
        return WORK_NEED_SPONSORSHIP_ANSWER
    if not is_work_authorization_question(question_label):
        return None
    logger.debug("Work authorization question -> %s", WORK_AUTHORIZATION_ANSWER)
    return WORK_AUTHORIZATION_ANSWER

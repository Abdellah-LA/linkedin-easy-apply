"""
SaaS-ready configuration loaded from environment.
"""
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

# Dify
DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "")
DIFY_BASE_URL: str = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1").rstrip("/")
DIFY_CV_FILE_ID: str = os.getenv("DIFY_CV_FILE_ID", "")
DIFY_USER: str = os.getenv("DIFY_USER", "abdellah_bot")

# LinkedIn job search: country + job title (intitulé du poste) — or full URL override
JOB_SEARCH_KEYWORDS: str = os.getenv("JOB_SEARCH_KEYWORDS", "software engineer java").strip()
JOB_SEARCH_COUNTRY: str = os.getenv("JOB_SEARCH_COUNTRY", "Canada").strip()
_raw_search_url: str = os.getenv("LINKEDIN_JOB_SEARCH_URL", "").strip()
if _raw_search_url:
    LINKEDIN_JOB_SEARCH_URL: str = _raw_search_url
else:
    _kw = JOB_SEARCH_KEYWORDS or "software engineer java"
    _loc = JOB_SEARCH_COUNTRY or "Canada"
    LINKEDIN_JOB_SEARCH_URL = (
        f"https://www.linkedin.com/jobs/search/?keywords={quote(_kw)}&location={quote(_loc)}&f_AL=true"
    )
LINKEDIN_BASE_URL: str = "https://www.linkedin.com"

# Resume (local file for Easy Apply upload)
RESUME_PATH: str = os.getenv("RESUME_PATH", "")
if RESUME_PATH:
    RESUME_PATH = str(Path(RESUME_PATH).expanduser().resolve())

# Easy Apply: preferred email to select from dropdown (contact step)
EASY_APPLY_EMAIL: str = os.getenv("EASY_APPLY_EMAIL", "abdellah-lakhnigue@outlook.fr")
# First name / last name (Prénom / Nom) — used for form fields in English and French
EASY_APPLY_FIRST_NAME: str = os.getenv("EASY_APPLY_FIRST_NAME", "").strip()
EASY_APPLY_LAST_NAME: str = os.getenv("EASY_APPLY_LAST_NAME", "").strip()
# Default years of experience for "Additional Questions" (Java, EJB, Spring, Mockito, Data Structures, etc.)
EASY_APPLY_YEARS_DEFAULT: str = os.getenv("EASY_APPLY_YEARS_DEFAULT", "3")
# Current company / title / gender for Easy Apply (leave empty for N/A or fallback)
EASY_APPLY_CURRENT_COMPANY: str = os.getenv("EASY_APPLY_CURRENT_COMPANY", "").strip()
EASY_APPLY_CURRENT_TITLE: str = os.getenv("EASY_APPLY_CURRENT_TITLE", "").strip()
EASY_APPLY_GENDER: str = os.getenv("EASY_APPLY_GENDER", "").strip()
# CV PDF path for form answers and Gemini extraction
CV_PATH: str = os.getenv("CV_PATH", "")
if CV_PATH:
    CV_PATH = str(Path(CV_PATH).expanduser().resolve())

# Gemini API (optional): exact answers from CV for open-ended questions
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
USE_GEMINI_FOR_CV: bool = os.getenv("USE_GEMINI_FOR_CV", "true").lower() in ("true", "1", "yes")

# Groq API (free tier, fallback when Gemini quota is exhausted): https://console.groq.com/keys
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Default city for "Location (city)*" and similar fields
DEFAULT_LOCATION_CITY: str = os.getenv("DEFAULT_LOCATION_CITY", "Casablanca")
# Notice period before start date (CDI norm in Morocco = 3 months)
NOTICE_PERIOD_DEFAULT: str = os.getenv("NOTICE_PERIOD_DEFAULT", "3 months")
# Certifications: comma-separated (e.g. AWS, Azure) for "do you have certificate: X?" — also checked in CV
EASY_APPLY_CERTIFICATIONS: str = os.getenv("EASY_APPLY_CERTIFICATIONS", "").strip()
# Hybrid / remote / work mode questions: answer Yes or No (e.g. "Are you able to work in hybrid mode?")
EASY_APPLY_HYBRID_ANSWER: str = os.getenv("EASY_APPLY_HYBRID_ANSWER", "Yes").strip()
# Work authorization: not authorized in search country; need sponsorship
WORK_AUTHORIZATION_ANSWER: str = os.getenv("WORK_AUTHORIZATION_ANSWER", "No")
WORK_NEED_SPONSORSHIP_ANSWER: str = os.getenv("WORK_NEED_SPONSORSHIP_ANSWER", "Yes")
WORK_AUTHORIZATION_COUNTRY: str = os.getenv("WORK_AUTHORIZATION_COUNTRY", "Canada")

# Persistent session (cookies / user data) — saved to linkedin_user_data/ for reuse
USER_DATA_DIR: str = os.getenv(
    "USER_DATA_DIR",
    str(Path(__file__).resolve().parent / "linkedin_user_data"),
)

# Stealth / human-like delays (seconds)
MIN_DELAY_SEC: float = float(os.getenv("MIN_DELAY_SEC", "5"))
MAX_DELAY_SEC: float = float(os.getenv("MAX_DELAY_SEC", "15"))
HEADLESS: bool = os.getenv("HEADLESS", "false").lower() in ("true", "1", "yes")

# Logging
LOG_FILE: str = os.getenv("LOG_FILE", str(Path(__file__).resolve().parent / "automation.log"))

# Runtime overrides from web form (JSON file); applied before starting the loop
_config_overrides_path: str = os.getenv(
    "CONFIG_OVERRIDES_FILE",
    str(Path(__file__).resolve().parent / "data" / "config_overrides.json"),
)


def _refresh_from_env() -> None:
    """Re-read all config from os.environ (used after apply_overrides_from_file)."""
    global DIFY_API_KEY, DIFY_BASE_URL, DIFY_CV_FILE_ID, DIFY_USER
    global JOB_SEARCH_KEYWORDS, JOB_SEARCH_COUNTRY, LINKEDIN_JOB_SEARCH_URL, LINKEDIN_BASE_URL
    global RESUME_PATH, CV_PATH, EASY_APPLY_EMAIL, EASY_APPLY_FIRST_NAME, EASY_APPLY_LAST_NAME
    global EASY_APPLY_YEARS_DEFAULT, EASY_APPLY_CURRENT_COMPANY, EASY_APPLY_CURRENT_TITLE
    global EASY_APPLY_GENDER, GEMINI_API_KEY, GEMINI_MODEL, USE_GEMINI_FOR_CV
    global GROQ_API_KEY, GROQ_MODEL, DEFAULT_LOCATION_CITY, NOTICE_PERIOD_DEFAULT
    global EASY_APPLY_CERTIFICATIONS, EASY_APPLY_HYBRID_ANSWER
    global WORK_AUTHORIZATION_ANSWER, WORK_NEED_SPONSORSHIP_ANSWER, WORK_AUTHORIZATION_COUNTRY
    global USER_DATA_DIR, MIN_DELAY_SEC, MAX_DELAY_SEC, HEADLESS, LOG_FILE
    DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
    DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1").rstrip("/")
    DIFY_CV_FILE_ID = os.getenv("DIFY_CV_FILE_ID", "")
    DIFY_USER = os.getenv("DIFY_USER", "abdellah_bot")
    JOB_SEARCH_KEYWORDS = os.getenv("JOB_SEARCH_KEYWORDS", "software engineer java").strip()
    JOB_SEARCH_COUNTRY = os.getenv("JOB_SEARCH_COUNTRY", "Canada").strip()
    _raw = os.getenv("LINKEDIN_JOB_SEARCH_URL", "").strip()
    if _raw:
        LINKEDIN_JOB_SEARCH_URL = _raw
    else:
        _kw = JOB_SEARCH_KEYWORDS or "software engineer java"
        _loc = JOB_SEARCH_COUNTRY or "Canada"
        LINKEDIN_JOB_SEARCH_URL = f"https://www.linkedin.com/jobs/search/?keywords={quote(_kw)}&location={quote(_loc)}&f_AL=true"
    LINKEDIN_BASE_URL = "https://www.linkedin.com"
    RESUME_PATH = os.getenv("RESUME_PATH", "")
    if RESUME_PATH:
        RESUME_PATH = str(Path(RESUME_PATH).expanduser().resolve())
    CV_PATH = os.getenv("CV_PATH", "")
    if CV_PATH:
        CV_PATH = str(Path(CV_PATH).expanduser().resolve())
    EASY_APPLY_EMAIL = os.getenv("EASY_APPLY_EMAIL", "abdellah-lakhnigue@outlook.fr")
    EASY_APPLY_FIRST_NAME = os.getenv("EASY_APPLY_FIRST_NAME", "").strip()
    EASY_APPLY_LAST_NAME = os.getenv("EASY_APPLY_LAST_NAME", "").strip()
    EASY_APPLY_YEARS_DEFAULT = os.getenv("EASY_APPLY_YEARS_DEFAULT", "3")
    EASY_APPLY_CURRENT_COMPANY = os.getenv("EASY_APPLY_CURRENT_COMPANY", "").strip()
    EASY_APPLY_CURRENT_TITLE = os.getenv("EASY_APPLY_CURRENT_TITLE", "").strip()
    EASY_APPLY_GENDER = os.getenv("EASY_APPLY_GENDER", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    USE_GEMINI_FOR_CV = os.getenv("USE_GEMINI_FOR_CV", "true").lower() in ("true", "1", "yes")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    DEFAULT_LOCATION_CITY = os.getenv("DEFAULT_LOCATION_CITY", "Casablanca")
    NOTICE_PERIOD_DEFAULT = os.getenv("NOTICE_PERIOD_DEFAULT", "3 months")
    EASY_APPLY_CERTIFICATIONS = os.getenv("EASY_APPLY_CERTIFICATIONS", "").strip()
    EASY_APPLY_HYBRID_ANSWER = os.getenv("EASY_APPLY_HYBRID_ANSWER", "Yes").strip()
    WORK_AUTHORIZATION_ANSWER = os.getenv("WORK_AUTHORIZATION_ANSWER", "No")
    WORK_NEED_SPONSORSHIP_ANSWER = os.getenv("WORK_NEED_SPONSORSHIP_ANSWER", "Yes")
    WORK_AUTHORIZATION_COUNTRY = os.getenv("WORK_AUTHORIZATION_COUNTRY", "Canada")
    USER_DATA_DIR = os.getenv("USER_DATA_DIR", str(Path(__file__).resolve().parent / "linkedin_user_data"))
    MIN_DELAY_SEC = float(os.getenv("MIN_DELAY_SEC", "5"))
    MAX_DELAY_SEC = float(os.getenv("MAX_DELAY_SEC", "15"))
    HEADLESS = os.getenv("HEADLESS", "false").lower() in ("true", "1", "yes")
    LOG_FILE = os.getenv("LOG_FILE", str(Path(__file__).resolve().parent / "automation.log"))


def apply_overrides_from_file(path: str | None = None) -> bool:
    """
    Load JSON from path (default: data/config_overrides.json), set os.environ, and refresh config.
    Returns True if file existed and was applied.
    """
    import json
    p = Path(path or _config_overrides_path)
    if not p.exists():
        return False
    data = json.loads(p.read_text(encoding="utf-8"))
    for k, v in data.items():
        if v is None:
            continue
        os.environ[k] = str(v)
    _refresh_from_env()
    return True

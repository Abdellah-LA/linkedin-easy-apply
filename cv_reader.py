"""
Form answer service: CV PDF extraction + experience map + work authorization + location + Gemini.
Provides a single get_answer_for_question() for Easy Apply forms.
"""
import re
from pathlib import Path
from typing import List, Optional

from logger_config import logger

from config import (
    DEFAULT_LOCATION_CITY,
    EASY_APPLY_CERTIFICATIONS,
    EASY_APPLY_CURRENT_COMPANY,
    EASY_APPLY_CURRENT_TITLE,
    EASY_APPLY_FIRST_NAME,
    EASY_APPLY_GENDER,
    EASY_APPLY_HYBRID_ANSWER,
    EASY_APPLY_LAST_NAME,
    NOTICE_PERIOD_DEFAULT,
    WORK_AUTHORIZATION_COUNTRY,
)
from experience_map import get_yes_no_for_experience, get_years_for_question, is_yes_no_experience_question
from gemini_cv import (
    get_answer_any_question_gemini,
    get_answer_from_cv_with_gemini,
    get_salary_expectation_gemini,
    get_years_of_experience_from_cv,
)
from work_authorization import get_work_authorization_answer

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

_cv_text_cache: Optional[str] = None


def _extract_skill_phrases_from_question(question_label: str) -> List[str]:
    """
    Extract technology/skill phrases from a question like
    "How many years of experience with Docker and/or Kubernetes?" or
    "Do you have experience with CI/CD pipelines using GitHub Actions?".
    Returns a list of normalized phrases to look for in the CV (e.g. ["docker", "kubernetes"], ["ci/cd", "github actions"]).
    """
    if not question_label or not question_label.strip():
        return []
    text = question_label.strip()
    # Take the part after "with", "avec", "using", "utilisant", "in" (experience with X / expérience avec X)
    for sep in (" with ", " avec ", " using ", " utilisant ", " in "):
        if sep in text.lower():
            idx = text.lower().index(sep) + len(sep)
            rest = text[idx:].strip()
            rest = re.sub(r"\s*\?+\s*\*?\s*$", "", rest).strip()
            if len(rest) > 2 and len(rest) < 150:
                break
    else:
        rest = text
        rest = re.sub(r"\s*\?+\s*\*?\s*$", "", rest).strip()
    # "technologies suivantes : MQ, Kafka ou MFT" -> take part after " : " to get the actual tech list
    if " : " in rest or ":" in rest:
        after_colon = rest.split(":")[-1].strip()
        if 2 < len(after_colon) < 120:
            rest = after_colon
    # Split by " et/ou ", " and/or ", " and ", " or ", " et ", " ou ", commas
    parts = re.split(r"\s+et/ou\s+|\s+and/or\s+|\s+and\s+|\s+or\s+|\s+et\s+|\s+ou\s+|,|/", rest, flags=re.I)
    phrases = []
    for p in parts:
        p = re.sub(r"^(des?|du|de la|les?|the|using|utilisant)\s+", "", p.strip(), flags=re.I).strip()
        p = p.strip(" .*")
        if len(p) > 1 and len(p) < 60:
            phrases.append(p.lower())
    # Dedupe and add known multi-word tech that might be in the question
    seen = set()
    result = []
    for ph in phrases:
        if ph and ph not in seen:
            seen.add(ph)
            result.append(ph)
    # Ensure we have at least one meaningful token from the question (e.g. "docker", "kubernetes")
    if not result and rest:
        for word in re.findall(r"[a-zA-Z0-9+#./]+", rest):
            if len(word) > 2 and word.lower() not in ("the", "and", "you", "have", "your", "avec", "experience", "expérience", "years", "années"):
                result.append(word.lower())
    return result[:15]


def _skill_mentioned_in_cv(question_label: str, cv_text: str, config_skills_list: str = "") -> bool:
    """
    True if any technology/skill mentioned in the question appears in the CV text
    or in the config list (EASY_APPLY_CERTIFICATIONS / skills). Used to return 0.0 / No when the skill is not found.
    """
    phrases = _extract_skill_phrases_from_question(question_label)
    if not phrases:
        return True  # Can't extract skill -> assume we have it (keep current behavior)
    # Check config list first (e.g. "Docker, Kafka, GitHub Actions" in .env)
    if config_skills_list and config_skills_list.strip():
        list_parts = [p.strip().lower() for p in config_skills_list.split(",") if p.strip()]
        for ph in phrases:
            for part in list_parts:
                if part in ph or ph in part:
                    return True
    # Check CV
    if cv_text and cv_text.strip():
        cv_lower = cv_text.lower()
        for ph in phrases:
            if ph in cv_lower:
                return True
            if len(ph) > 3 and ph.replace(" ", "") in cv_lower.replace(" ", ""):
                return True
    return False


def _has_certification(cert_name: str, cv_text: str, config_list: str) -> bool:
    """True if cert_name appears to be in the candidate's certifications (CV or .env list)."""
    if not cert_name or not cert_name.strip():
        return False
    cert_clean = cert_name.strip().lower()
    # Normalize: "AWS Certifications" -> "aws", "Azure Fundamentals" -> "azure"
    cert_key = cert_clean.split()[0] if cert_clean else cert_clean
    cv_lower = (cv_text or "").lower()
    if cert_key in cv_lower:
        return True
    if "certif" in cv_lower and cert_key in cv_lower:
        return True
    if "certified" in cv_lower and cert_key in cv_lower:
        return True
    if config_list:
        for part in config_list.split(","):
            part = part.strip().lower()
            if part and (part in cert_clean or cert_key in part):
                return True
    return False


def _certification_question_and_name(question_label: str) -> Optional[tuple[bool, str]]:
    """If this is a certification/permit question, return (True, certification_name)."""
    if not question_label:
        return None
    label_lower = question_label.lower()
    if not any(k in label_lower for k in ("certificat", "certification", "permit", "permis", "licence")):
        return None
    # Extract name: "Avez-vous le permis ou le certificat requis : AWS Certifications ?" -> "AWS Certifications"
    import re
    if ":" in question_label:
        after_colon = question_label.split(":", 1)[-1].strip()
        after_colon = re.sub(r"\s*\?+\s*\*?\s*$", "", after_colon).strip()
        if after_colon and len(after_colon) < 80 and not after_colon.lower().startswith(("avez", "do you", "have you")):
            return (True, after_colon)
    if "certification" in label_lower or "certificat" in label_lower:
        return (True, question_label.strip())
    return None


def load_cv_text(cv_path: str) -> str:
    """Extract raw text from PDF CV. Cached after first load."""
    global _cv_text_cache
    if _cv_text_cache is not None:
        return _cv_text_cache
    if not cv_path or not Path(cv_path).exists():
        return ""
    if PdfReader is None:
        logger.warning("pypdf not installed; CV text not loaded")
        return ""
    try:
        reader = PdfReader(cv_path)
        parts = []
        for p in reader.pages:
            parts.append(p.extract_text() or "")
        _cv_text_cache = "\n".join(parts)
        return _cv_text_cache
    except Exception as e:
        logger.warning("Could not read CV PDF: %s", e)
        return ""


def get_answer_for_question(
    question_label: str,
    years_default: str = "3",
    cv_path: str = "",
    use_gemini: bool = True,
) -> Optional[str]:
    """
    Single entry point for Easy Apply form answers.
    Order: work authorization -> years -> Yes/No experience -> Gemini from CV.
    """
    if not question_label or not (question_label := question_label.strip()):
        return None

    # 1) Work authorization / citizenship / residency -> always No (need sponsorship)
    work_ans = get_work_authorization_answer(question_label)
    if work_ans is not None:
        return work_ans

    # 2) Legal status in Canada -> user is Moroccan, not Canadian citizen: "No status" or "Other"
    label_lower = question_label.lower()
    if "legal status" in label_lower and "canada" in label_lower:
        return "No status"  # or "Other" depending on dropdown options; prefer "No status"

    # 3) Location (city) -> default city from config (e.g. Casablanca)
    if "location" in label_lower and "city" in label_lower:
        if DEFAULT_LOCATION_CITY:
            return DEFAULT_LOCATION_CITY.strip()

    # 3a) First name / Last name (English + French: First name, Prénom, Last name, Nom)
    if any(k in label_lower for k in ("first name", "prénom", "prenom", "given name")) and "last" not in label_lower and "nom de famille" not in label_lower:
        if EASY_APPLY_FIRST_NAME:
            return EASY_APPLY_FIRST_NAME.strip()
        return "N/A"
    if any(k in label_lower for k in ("last name", "nom de famille", "family name", "surname")) or label_lower.strip() == "nom":
        if EASY_APPLY_LAST_NAME:
            return EASY_APPLY_LAST_NAME.strip()
        return "N/A"

    # 3b) Hybrid / remote / work mode: use EASY_APPLY_HYBRID_ANSWER (Yes/No from .env)
    hybrid_keywords = (
        "hybride", "hybrid", "remote", "télétravail", "telework", "work from home", "présence obligatoire",
        "on-site", "on site", "in-office", "work arrangement", "mode de travail", "work mode",
    )
    if any(k in label_lower for k in hybrid_keywords):
        raw = (EASY_APPLY_HYBRID_ANSWER or "Yes").strip()
        if raw.lower() in ("no", "non", "0", "false"):
            return "No"
        return "Yes"  # yes, oui, 1, true, or any other value -> Yes

    # 4) Salary expectations -> mid-range for mid-level software engineer (Gemini lookup by region)
    if "salary" in label_lower and ("expectation" in label_lower or "expected" in label_lower or "compensation" in label_lower):
        region = WORK_AUTHORIZATION_COUNTRY or "Canada"
        salary = get_salary_expectation_gemini(region=region, role="mid-level software engineer")
        if salary:
            return salary

    # 5) Notice period / start date / joining -> 3 months (CDI norm in Morocco)
    if "notice" in label_lower and ("start" in label_lower or "before" in label_lower or "joining" in label_lower):
        return (NOTICE_PERIOD_DEFAULT or "3 months").strip()

    # 5b) Current Company / Current Title (from .env; else N/A)
    if "current company" in label_lower or "company" in label_lower and "current" in label_lower:
        return (EASY_APPLY_CURRENT_COMPANY or "N/A").strip()
    if "current title" in label_lower or ("title" in label_lower and "current" in label_lower):
        return (EASY_APPLY_CURRENT_TITLE or "N/A").strip()

    # 5c) Gender / sex (Male, Female, Other — set EASY_APPLY_GENDER in .env to match form options)
    if "pronouns" in label_lower:
        return "Prefer not to say"
    if any(k in label_lower for k in ("gender", "sexe", "sex ", "male", "female", "how do you describe your gender")):
        if EASY_APPLY_GENDER:
            return EASY_APPLY_GENDER.strip()
        return "Male"  # fallback if not set

    # 5d) Certification/permit: "Do you have the required certificate: AWS Certifications?" — check CV + EASY_APPLY_CERTIFICATIONS
    cert_result = _certification_question_and_name(question_label)
    if cert_result is not None:
        _, cert_name = cert_result
        cv_text = load_cv_text(cv_path) if cv_path else ""
        if _has_certification(cert_name, cv_text, EASY_APPLY_CERTIFICATIONS or ""):
            return "Yes"  # applier maps Yes/oui to same radio
        return "No"

    # 6) Years of experience (any: Design, Java, career) -> whole number only; user: "3" for all career years
    if "years" in label_lower and "experience" in label_lower:
        # Rating-style fields (frontend*, backend*) use decimals — handled in 8b
        if any(k in label_lower for k in ("frontend", "backend", "microservice", "api", "database", "devops", "fullstack", "mobile", "cloud", "security", "testing")):
            pass  # fall through to 8b
        else:
            # "How many years of experience with X?" -> 0 if skill not in CV/list
            cv_text = load_cv_text(cv_path) if cv_path else ""
            if "how many" in label_lower and not _skill_mentioned_in_cv(question_label, cv_text, EASY_APPLY_CERTIFICATIONS or ""):
                return "0"  # whole number when skill not in CV
            # Priority 1: your defined experience_map (Java 4, Spring/Docker etc 3, other 2)
            years = get_years_for_question(question_label)
            if years is not None:
                return str(int(years))
            # Priority 2: AI from CV when map had no match
            if use_gemini and cv_text and len(cv_text.strip()) >= 50:
                ai_years = get_years_of_experience_from_cv(question_label, cv_text)
                if ai_years is not None:
                    return ai_years
            try:
                return str(int(years_default))
            except (TypeError, ValueError):
                return "3"

    # 7) Yes/No experience question (radios or dropdowns); if skill not in CV/list -> No
    if is_yes_no_experience_question(question_label):
        cv_text = load_cv_text(cv_path) if cv_path else ""
        if not _skill_mentioned_in_cv(question_label, cv_text, EASY_APPLY_CERTIFICATIONS or ""):
            return "No"
        yes_no = get_yes_no_for_experience(question_label)
        if yes_no is not None:
            return yes_no

    # 8) "How many years of experience with X?" (if not caught above) -> experience_map first, then AI
    years = get_years_for_question(question_label)
    if years is not None:
        return str(int(years))
    if use_gemini and cv_path:
        cv_text = load_cv_text(cv_path) or ""
        if len(cv_text.strip()) >= 50:
            ai_years = get_years_of_experience_from_cv(question_label, cv_text)
            if ai_years is not None:
                return ai_years

    # 8b) Rating/level decimals (e.g. frontend*, backend*, microservice* — "Enter a decimal number larger than 0.0")
    # Short labels that are typically 1–10 scale: 8.0 for frontend/backend, 5.0 for anything else
    label_clean = re.sub(r"\*+\s*$", "", (question_label or "").strip()).lower().strip()
    rating_keywords = (
        "frontend", "backend", "microservice", "microservices", "api", "database", "devops",
        "fullstack", "full-stack", "mobile", "cloud", "security", "testing", "data",
    )
    if label_clean and len(label_clean) < 50 and any(k in label_clean for k in rating_keywords):
        if "frontend" in label_clean or "backend" in label_clean:
            return "8.0"
        return "5.0"

    # 9) Open-ended: use Gemini with CV if enabled
    cv_text = load_cv_text(cv_path) if cv_path else ""
    if use_gemini:
        if cv_text and len(cv_text.strip()) >= 50:
            gemini_ans = get_answer_from_cv_with_gemini(question_label, cv_text)
            if gemini_ans is not None:
                return gemini_ans
        # Last resort: Gemini with just the question (no CV) so we never leave a field empty
        gemini_ans = get_answer_any_question_gemini(question_label)
        if gemini_ans is not None:
            return gemini_ans

    # Ultimate fallback: safe defaults so we never get stuck (whole number for years)
    if any(w in label_lower for w in ("year", "experience", "how many")):
        try:
            n = int(years_default)
            return str(n)  # whole number, no decimal
        except (TypeError, ValueError):
            return "3"
    if any(w in label_lower for w in ("yes", "no", "experience with", "have you", "do you have")):
        return "Yes"
    if "number" in label_lower or "salary" in label_lower or "amount" in label_lower:
        return "1"
    # Last resort for unknown short labels that might be decimal (e.g. rating): safe decimal so we never get stuck
    q = (question_label or "").strip()
    if len(q) < 40 and not any(w in label_lower for w in ("describe", "explain", "why", "what", "comment")):
        return "5.0"
    return "N/A"

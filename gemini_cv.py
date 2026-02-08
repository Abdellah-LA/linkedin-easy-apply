"""
LLM API: Gemini primary, Groq free-tier fallback for form answers and salary.
Uses Google Gemini when available; on quota error or no key, tries Groq (free).
"""
import re
from typing import Optional

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    USE_GEMINI_FOR_CV,
)
from logger_config import logger

try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None


def _call_groq(prompt: str, max_tokens: int = 150) -> Optional[str]:
    """Call Groq API (free tier). Returns first reply text or None."""
    if not GROQ_API_KEY or Groq is None:
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        r = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            max_tokens=max_tokens,
        )
        if r and r.choices:
            text = (r.choices[0].message.content or "").strip()
            return text if text else None
    except Exception as e:
        logger.warning("Groq API failed: %s", e)
    return None


def get_salary_expectation_gemini(region: str = "Canada", role: str = "mid-level software engineer") -> Optional[str]:
    """
    Use Gemini (or Groq fallback) to return a single mid-range salary number.
    Form fields often want "a decimal number larger than 0.0" (annual salary).
    """
    prompt = f"""What is the typical mid-range annual salary in local currency for a {role} in {region}? Consider current market data.
Reply with ONLY one number, no currency symbol, no commas, no explanation. E.g. 95000 or 85000."""
    text = None
    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = getattr(response, "text", None) if response else None
        except Exception as e:
            logger.warning("Gemini salary lookup failed: %s", e)
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                text = _call_groq(prompt, max_tokens=50)
    if not text and GROQ_API_KEY and Groq:
        text = _call_groq(prompt, max_tokens=50)
    if text:
        num = re.sub(r"[^0-9.]", "", str(text).strip())
        if num:
            return num.split(".")[0] if "." in num and num.split(".")[0].isdigit() else (num if num.isdigit() else "95000")
    return "95000"


def get_answer_from_options(question: str, options: list[str]) -> Optional[str]:
    """
    Pick the best option from a dropdown list using the API (Gemini then Groq).
    Returns one of the exact strings from options, or None.
    Use this when the dropdown has specific labels (e.g. Work Authorization, Hybrid, Relocate).
    """
    options = [str(o).strip() for o in (options or []) if str(o).strip()]
    if not options:
        return None
    question = (question or "").strip()
    opts_text = "\n".join(f"- {o}" for o in options)
    prompt = f"""You are a form-filling assistant. For this job application dropdown, choose exactly ONE option from the list. Reply with ONLY that option text, nothing else.

Question: {question}

Options (reply with one of these exactly):
{opts_text}

Context: Candidate is a software engineer, not currently authorized to work in Canada (needs sponsorship), open to hybrid/relocate for the right role. For work authorization choose the option that means "requires sponsorship" or "not authorized". For hybrid/relocate choose "Yes" or the most positive option if no simple Yes.

Answer (exact option text only):"""
    text = None
    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = getattr(response, "text", None) if response else None
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                text = _call_groq(prompt, max_tokens=200)
            if not text:
                logger.warning("Gemini options pick failed: %s", e)
    if not text and GROQ_API_KEY and Groq:
        text = _call_groq(prompt, max_tokens=200)
    if not text:
        return options[0]
    chosen = str(text).strip().strip('"\'')
    for o in options:
        if o.lower() == chosen.lower() or chosen.lower() in o.lower() or o.lower() in chosen.lower():
            return o
    return options[0]


def get_answer_any_question_gemini(question: str, max_length: int = 100) -> Optional[str]:
    """
    Answer any form question in one short phrase (no CV). Tries Gemini first, then Groq if quota/no key.
    """
    question = (question or "").strip()
    if not question:
        return None
    prompt = f"""You are a form-filling assistant. Answer this job application question with ONLY the value to put in the form. No explanation.
- For Yes/No questions reply exactly "Yes" or "No".
- For numbers reply with just the number.
- For dropdowns (notice period, pronouns, etc.) reply with one short option e.g. "3 months", "2 weeks", "Prefer not to say".
- Be professional and concise (max {max_length} characters).

Question: {question}

Answer (only the value, nothing else):"""
    text = None
    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = getattr(response, "text", None) if response else None
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                text = _call_groq(prompt, max_tokens=max_length + 20)
            if not text:
                logger.warning("Gemini any-answer failed: %s", e)
    if not text and GROQ_API_KEY and Groq:
        text = _call_groq(prompt, max_tokens=max_length + 20)
    if text:
        out = str(text).strip().strip('"\'')[:max_length]
        return out if out else None
    return None


def get_years_of_experience_from_cv(question: str, cv_text: str) -> Optional[str]:
    """
    Use AI to infer years of experience (0-99, whole number) from the CV for this specific question.
    E.g. "How many years of Design experience?" -> infer from CV roles, skills, dates; return "2", "5", etc.
    """
    if not question or not (cv_text or "").strip() or len(cv_text.strip()) < 30:
        return None
    question = question.strip()
    prompt = f"""You are a form-filling assistant. The job application asks a "years of experience" question. Based ONLY on the candidate's CV below, infer how many years of experience they have for what is asked. Consider:
- Job titles and tenure (dates) in the CV.
- Skills and technologies mentioned relative to the question (e.g. Design, Java, management).
- Overall experience level (junior = 1-3, mid = 3-6, senior = 6+).

Reply with ONLY one whole number between 0 and 99. No decimals, no words, no explanation. If the CV does not show relevant experience, reply 0.

CV:
---
{cv_text[:10000]}
---

Question: {question}

Answer (single integer 0-99 only):"""
    text = None
    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = getattr(response, "text", None) if response else None
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                text = _call_groq(prompt, max_tokens=20)
            if not text:
                logger.warning("Gemini years-from-CV failed: %s", e)
    if not text and GROQ_API_KEY and Groq:
        text = _call_groq(prompt, max_tokens=20)
    if not text:
        return None
    num = re.sub(r"[^0-9]", "", str(text).strip())
    if not num:
        return None
    n = int(num[:2]) if len(num) >= 2 else int(num)  # cap at 99
    n = min(99, max(0, n))
    return str(n)


def get_answer_from_cv_with_gemini(question: str, cv_text: str, max_length: int = 100) -> Optional[str]:
    """
    Use Gemini to answer a form question based on CV content.
    Returns a short string suitable for a form field (number, Yes/No, or one phrase).
    """
    if not USE_GEMINI_FOR_CV or not cv_text or not question:
        return None
    question = (question or "").strip()
    if not question or len(cv_text.strip()) < 50:
        return None
    prompt = f"""You are a form-filling assistant. Given the candidate's CV and a job application question, return ONLY the exact value to put in the form field. No explanation.

Rules:
- For "How many years of experience with X?" return a single number between 0 and 99 based on the CV. If unclear, use 2 or 3.
- For Yes/No questions, return exactly "Yes" or "No".
- For citizenship / work authorization in a specific country: if the candidate is NOT a citizen and needs sponsorship, return "No".
- For other questions, return one short phrase or number (max {max_length} characters).

CV:
---
{cv_text[:12000]}
---

Question: {question}

Answer (only the value for the form, nothing else):"""
    text = None
    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            text = getattr(response, "text", None) if response else None
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                text = _call_groq(prompt, max_tokens=max_length + 50)
            if not text:
                logger.warning("Gemini CV answer failed: %s", e)
    if not text and GROQ_API_KEY and Groq:
        text = _call_groq(prompt, max_tokens=max_length + 50)
    if text:
        out = str(text).strip().strip('"\'')[:max_length]
        return out if out else None
    return None

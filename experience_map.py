"""
Experience map: technology → years of experience for Easy Apply forms.
Used to answer "How many years of experience with X?" and "Do you have experience with X?" (Yes/No).
"""
import re
from typing import Optional

# Java core (main language): max 4 years
YEARS_JAVA_CORE = 4
# Spring Boot, React, Angular, DBs, testing, methodologies: 3 years
YEARS_PRIMARY = 3
# Other technologies: 2 years
YEARS_OTHER = 2
# "How many total years of work experience?" (no specific tech) -> 3
TOTAL_YEARS_DEFAULT = 3

# Technologies that map to 4 years (Java core)
TECH_4_YEARS = (
    "java",
    "core java",
    "java se",
    "jvm",
)

# Technologies that map to 3 years
TECH_3_YEARS = (
    "spring",
    "spring boot",
    "springboot",
    "postgres",
    "postgresql",
    "mysql",
    "websocket",
    "web socket",
    "webservices",
    "web services",
    "rest api",
    "restapis",
    "restful",
    "react",
    "angular",
    "mockito",
    "unit test",
    "unittesting",
    "junit",
    "agile",
    "scrum",
    "agile/scrum",
    "microservices",
    "docker",
    "ci/cd",
    "git",
    "nestjs",
    "typescript",
    "ejb",
    "enterprise javabeans",
    "data structures",
    "keycloak",
    "rbac",
    "graphql",
    "graph ql",
    "ruby",
    "banking",
    "angular ui",
    "ui integration",
)

# Phrases that indicate a Yes/No experience question (not a number)
YES_NO_EXPERIENCE_PATTERNS = (
    r"do you have .* experience",
    r"do you have experience",
    r"do you have (at least|an understanding of)",
    r"have you (worked|used|experience)",
    r"are you (experienced|familiar)",
    r"experience with .*\?",
    r"experience (programming|using|with)",
    r"avez-vous .* expérience",
    r"oui ou non",
    r"yes or no",
    r"yes/no",
)


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").lower().strip())


def get_years_for_question(question_label: str) -> Optional[int]:
    """
    Return years of experience (0-99) for a "How many years with X?" question.
    "Total years of work experience" -> TOTAL_YEARS_DEFAULT (3). Java core -> 4; Spring, etc. -> 3; other -> 2.
    """
    if not question_label:
        return None
    text = _normalize_label(question_label)
    if not any(k in text for k in ("year", "years", "année", "expérience", "experience")):
        return None
    # "How many total years of work experience you have?" -> 3
    if "total" in text and ("year" in text or "experience" in text):
        return TOTAL_YEARS_DEFAULT
    for tech in TECH_4_YEARS:
        if tech in text:
            return YEARS_JAVA_CORE
    for tech in TECH_3_YEARS:
        if tech in text:
            return YEARS_PRIMARY
    if "year" in text or "experience" in text:
        return YEARS_OTHER
    return None


def is_yes_no_experience_question(question_label: str) -> bool:
    """True if the question is a Yes/No about having experience (e.g. "Do you have experience with X?")."""
    if not question_label:
        return False
    text = _normalize_label(question_label)
    if "how many" in text and "years" in text:
        return False  # "How many years of experience with X?" wants a number, not Yes/No
    for pat in YES_NO_EXPERIENCE_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def get_yes_no_for_experience(question_label: str) -> Optional[str]:
    """
    For Yes/No experience questions: if we have >0 years for that tech, return "Yes", else "No".
    """
    if not is_yes_no_experience_question(question_label):
        return None
    years = get_years_for_question(question_label)
    if years is None:
        years = YEARS_OTHER
    return "Yes" if years > 0 else "No"

"""
Quick test: Gemini API + CV integration.
Run: python test_gemini.py

Requires: pip install pypdf google-genai
"""
import sys

# Check deps before importing app modules
try:
    from google import genai
except ImportError:
    print("Missing package: run  pip install google-genai")
    sys.exit(1)
try:
    from pypdf import PdfReader
except ImportError:
    print("Missing package: run  pip install pypdf")
    sys.exit(1)

from config import CV_PATH, GEMINI_API_KEY, GEMINI_MODEL, USE_GEMINI_FOR_CV
from cv_reader import get_answer_for_question, load_cv_text
from gemini_cv import get_answer_from_cv_with_gemini


def main() -> int:
    print("=== Gemini + CV integration test ===\n")

    # Config check
    key_status = "set" if (GEMINI_API_KEY and len(GEMINI_API_KEY) > 10) else "NOT SET or too short"
    print(f"GEMINI_API_KEY: {key_status}")
    print(f"GEMINI_MODEL:   {GEMINI_MODEL}")
    print(f"USE_GEMINI_FOR_CV: {USE_GEMINI_FOR_CV}")
    print(f"CV_PATH:        {CV_PATH or '(not set)'}")
    print()

    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        print("ERROR: Set GEMINI_API_KEY in .env (get one from https://aistudio.google.com/app/apikey)")
        return 1

    # Load CV
    cv_text = load_cv_text(CV_PATH or "")
    if not cv_text or len(cv_text.strip()) < 50:
        print("WARNING: CV text empty or too short. Set CV_PATH in .env to your PDF.")
        cv_text = "Software Engineer with Java and Spring Boot experience. 3+ years backend development."
        print("Using a minimal placeholder for the API test.\n")
    else:
        print(f"CV loaded: {len(cv_text)} characters.\n")

    # Test 1: Direct Gemini call (one question)
    print("--- Test 1: Gemini API (direct) ---")
    question1 = "How many years of experience do you have with Spring Boot?"
    try:
        answer1 = get_answer_from_cv_with_gemini(question1, cv_text)
        if answer1 is not None:
            print(f"Q: {question1}")
            print(f"A: {answer1}\n")
        else:
            print("Gemini returned None. Running raw API check...")
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                r = client.models.generate_content(model=GEMINI_MODEL, contents="Reply with only the number 3.")
                raw = getattr(r, "text", None)
                if raw is None and getattr(r, "candidates", None):
                    c = r.candidates[0]
                    parts = getattr(c, "content", None) and getattr(c.content, "parts", None)
                    if parts:
                        raw = getattr(parts[0], "text", None)
                print(f"Raw API response: {raw!r}")
                if not raw:
                    print("No text in response. Check GEMINI_MODEL (e.g. gemini-2.0-flash or gemini-1.5-flash).\n")
                else:
                    print("API works; CV answer may be empty for that question.\n")
            except Exception as e2:
                err_str = str(e2)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    print("API key works but quota exceeded (free tier limit). Check plan/billing at https://ai.google.dev/gemini-api/docs/rate-limits")
                    print("You can try GEMINI_MODEL=gemini-1.5-flash in .env (different quota), or wait and retry later.\n")
                else:
                    print(f"Raw API check failed: {e2}\n")
    except Exception as e:
        print(f"Gemini call failed: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

    # Test 2: Full pipeline (cv_reader.get_answer_for_question — experience map may answer first)
    print("--- Test 2: Full pipeline (experience map + Gemini) ---")
    question2 = "What is your highest level of education?"
    answer2 = get_answer_for_question(question2, years_default="3", cv_path=CV_PATH or "", use_gemini=True)
    print(f"Q: {question2}")
    print(f"A: {answer2}\n")

    print("=== Test finished. ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

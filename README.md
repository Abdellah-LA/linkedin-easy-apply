# LinkedIn Easy Apply (Candidature Simplifiée) Automation

Stealthy automation for LinkedIn job search and Easy Apply, with a **Dify** workflow as the “brain” that decides **PROCEED** or **SKIP** and returns **form_answers** for each job.

## Features

- **Persistent session**: Uses Playwright `launch_persistent_context` and stores cookies in `linkedin_user_data/` so you don’t log in every run (reduces ban risk).
- **Stealth**: `playwright-stealth` + randomized delays (5–15 s between actions).
- **Dify integration**: `call_dify_brain(job_text)` POSTs to your Dify workflow and parses `apply_status` (PROCEED/SKIP) and `form_answers`.
- **Smart scraper**: Navigates job search, scrolls the list, finds “Candidature Simplifiée” (Easy Apply) buttons.
- **Auto-applier**: If Dify says PROCEED, clicks Easy Apply, fills the multi-step form from `form_answers`, uploads resume when required.
- **Resilience**: Logging to `automation.log`, “skip and move on” on per-job or per-step failures.

## Setup

1. **Python 3.9+** and venv (recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Environment**: Copy `.env.example` to `.env` and set:

   - `DIFY_API_KEY` – Dify workflow API key  
   - `DIFY_BASE_URL` – e.g. `https://api.dify.ai/v1`  
   - `DIFY_CV_FILE_ID` – Your CV file ID in Dify (or leave blank and use `RESUME_PATH`)  
   - `RESUME_PATH` – Local path to resume PDF for Easy Apply upload (optional)  
   - `LINKEDIN_JOB_SEARCH_URL` – LinkedIn job search URL (optional)  
   - `MIN_DELAY_SEC` / `MAX_DELAY_SEC` – Random delay range (default 5–15 s)  
   - `HEADLESS` – `true` / `false`  

3. **First run (login once)**  
   Run with `HEADLESS=false`, complete LinkedIn login in the browser. The session is saved in `linkedin_user_data/` and reused on later runs.

## Dify workflow contract

- **Inputs**:  
  - `linkedin_data`: string (job listing text sent by the script)  
  - `cv_pdf`: string (value of `DIFY_CV_FILE_ID`)  
- **User**: `abdellah_bot` (or `DIFY_USER`).  
- **Outputs** (workflow must expose):  
  - `apply_status`: `"PROCEED"` or `"SKIP"`  
  - `form_answers`: object, e.g. `{"years_of_experience": "5", "salary": "50k", ...}`  
  The script matches form labels (and normalized keys like `years_of_experience`) to these keys when filling the Easy Apply form.

## Run

```bash
python main.py
```

Logs go to the console and to `automation.log`.

## Deploy online (free) and multi-user

To run the app **online** and support **multiple users with different IP addresses**, see **[DEPLOY.md](DEPLOY.md)**. It covers:

- **Docker**: one-command run with `docker compose up` (one user per machine = one IP).
- **Free cloud**: Railway, Render, Fly.io, Oracle Cloud (one deployment per user = one IP per user).
- **Multi-user**: each user runs their own instance (own machine or own deploy) so each has a different IP.

## Form answer system (subscription-ready)

Easy Apply questions are answered in this order:

1. **Work authorization** (`work_authorization.py`): Citizenship / residency / “authorized to work in [country]” → **No**. “Do you require sponsorship?” → **Yes**. Configure: `WORK_AUTHORIZATION_ANSWER`, `WORK_NEED_SPONSORSHIP_ANSWER`, `WORK_AUTHORIZATION_COUNTRY`.

2. **Experience map** (`experience_map.py`): “How many years with X?” → number by technology (e.g. Java core 4, Spring Boot / React / Mockito / Agile 3, others 2). “Do you have experience with X?” (Yes/No) → **Yes** if years &gt; 0, else **No**.

3. **Gemini + CV** (`gemini_cv.py`, `cv_reader.py`): Open-ended questions → answer from your CV using the Gemini API (set `GEMINI_API_KEY`, `CV_PATH`, `USE_GEMINI_FOR_CV=true`). Uses AI to extract a short form answer from the CV text.

4. **CV PDF** (`cv_reader.py`): CV text is loaded with `pypdf` and cached. Required for Gemini; experience map works without it.

All answers are config-driven via `.env` for multi-tenant or subscription use.

## Project layout

- `main.py` – Entry point; loop over jobs, select → Easy Apply → fill (contact + additional) → next.
- `config.py` – Loads `.env` (LinkedIn, CV, Gemini, work auth, delays).
- `logger_config.py` – File + console logging.
- `browser_engine.py` – Persistent context, stealth, human delays.
- `scraper.py` – Navigate job search, get job list, select job by index, click Candidature simplifiée.
- `applier.py` – Easy Apply modal: contact (email), then fill all additional questions (input/select/radio) and click Suivant/Vérifier/Soumettre.
- `cv_reader.py` – CV PDF text extraction; single `get_answer_for_question()` (work auth → years → Yes/No → Gemini).
- `experience_map.py` – Technology → years of experience; Yes/No from years.
- `work_authorization.py` – Detect citizenship/residency/sponsorship questions; return No / Yes.
- `gemini_cv.py` – Gemini API: answer open-ended form questions from CV text.

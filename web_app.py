"""
Web app: setup form (profile + CV upload), then start/stop the Easy Apply loop.
One deployment = one LinkedIn account; all visitors share the same run.
If env vars are set (e.g. Railway Variables from .env), the form is optional.
"""
import asyncio
import importlib
import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

# State shared with main loop (updated by main(), read by API)
_run_state: dict = {
    "running": False,
    "applied_count": 0,
    "error": None,
}
_stop_event: asyncio.Event | None = None
_run_task: asyncio.Task | None = None

DATA_DIR = Path(__file__).resolve().parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OVERRIDES_FILE = DATA_DIR / "config_overrides.json"

# Form keys that map to config env (string values)
SETUP_FORM_KEYS = (
    "EASY_APPLY_FIRST_NAME", "EASY_APPLY_LAST_NAME", "EASY_APPLY_EMAIL",
    "JOB_SEARCH_COUNTRY", "JOB_SEARCH_KEYWORDS", "DEFAULT_LOCATION_CITY",
    "WORK_AUTHORIZATION_ANSWER", "WORK_NEED_SPONSORSHIP_ANSWER", "WORK_AUTHORIZATION_COUNTRY",
    "EASY_APPLY_YEARS_DEFAULT", "EASY_APPLY_CURRENT_COMPANY", "EASY_APPLY_CURRENT_TITLE",
    "EASY_APPLY_GENDER", "EASY_APPLY_CERTIFICATIONS", "EASY_APPLY_HYBRID_ANSWER",
    "MIN_DELAY_SEC", "MAX_DELAY_SEC", "GEMINI_API_KEY", "GROQ_API_KEY",
)

app = FastAPI(title="LinkedIn Easy Apply", version="1.0")


def _get_html() -> str:
    path = Path(__file__).resolve().parent / "static" / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _default_index_html()


def _default_index_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LinkedIn Easy Apply</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f3f6f8; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1rem; }
    .card { max-width: 420px; width: 100%; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.08); padding: 2rem; }
    h1 { margin: 0 0 0.5rem; font-size: 1.5rem; color: #0a66c2; }
    .sub { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
    .status { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; padding: 0.75rem; border-radius: 8px; background: #f0f7ff; }
    .status.running { background: #e8f5e9; }
    .status.error { background: #ffebee; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: #9e9e9e; }
    .status.running .dot { background: #4caf50; animation: pulse 1.5s ease-in-out infinite; }
    .status.error .dot { background: #f44336; }
    @keyframes pulse { 0%,100%{ opacity:1 } 50%{ opacity:.5 } }
    .count { font-size: 1.25rem; font-weight: 600; color: #333; margin-bottom: 1.5rem; }
    .btns { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    button { padding: 0.75rem 1.25rem; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; font-weight: 500; }
    .btn-start { background: #0a66c2; color: #fff; }
    .btn-start:hover { background: #004182; }
    .btn-start:disabled { background: #ccc; cursor: not-allowed; }
    .btn-stop { background: #d32f2f; color: #fff; }
    .btn-stop:hover { background: #b71c1c; }
    .btn-stop:disabled { background: #ccc; cursor: not-allowed; }
    .error-msg { color: #c62828; font-size: 0.9rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>LinkedIn Easy Apply</h1>
    <p class="sub">Start the bot to apply to jobs one by one. One run per deployment.</p>
    <div id="status" class="status">
      <span class="dot"></span>
      <span id="statusText">Idle</span>
    </div>
    <div class="count">Applied this run: <span id="count">0</span></div>
    <div id="error" class="error-msg" style="display:none"></div>
    <div class="btns">
      <button id="btnStart" class="btn-start">Start</button>
      <button id="btnStop" class="btn-stop" disabled>Stop</button>
    </div>
  </div>
  <script>
    const statusEl = document.getElementById('status');
    const statusText = document.getElementById('statusText');
    const countEl = document.getElementById('count');
    const errorEl = document.getElementById('error');
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');

    function setState(data) {
      const running = !!data.running;
      statusEl.classList.remove('running', 'error');
      if (data.error) { statusEl.classList.add('error'); statusText.textContent = 'Error'; errorEl.style.display = 'block'; errorEl.textContent = data.error; }
      else { errorEl.style.display = 'none'; statusEl.classList.toggle('running', running); statusText.textContent = running ? 'Running' : 'Idle'; }
      countEl.textContent = data.applied_count ?? 0;
      btnStart.disabled = running;
      btnStop.disabled = !running;
    }

    async function fetchStatus() {
      try {
        const r = await fetch('/api/status');
        const data = await r.json();
        setState(data);
      } catch (e) { statusText.textContent = 'Offline'; }
    }

    btnStart.onclick = async () => {
      try {
        const r = await fetch('/api/start', { method: 'POST' });
        if (r.ok) { await fetchStatus(); return; }
        const text = await r.text();
        let msg = 'Start failed';
        try { const j = JSON.parse(text); msg = j.detail || msg; } catch (_) { if (text) msg = text.slice(0, 300); }
        alert(msg);
      } catch (e) { alert('Request failed: ' + (e.message || e)); }
    };

    btnStop.onclick = async () => {
      try {
        await fetch('/api/stop', { method: 'POST' });
        await fetchStatus();
      } catch (e) { alert('Request failed'); }
    };

    fetchStatus();
    setInterval(fetchStatus, 3000);
  </script>
</body>
</html>
"""


def _ensure_data_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    """Health check for Railway/Render (returns 200 if app is up)."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    return _get_html()


def _is_configured_from_env() -> bool:
    """True if we have enough in env to run (no form needed)."""
    has_resume = bool(os.getenv("RESUME_PATH") or os.getenv("CV_PATH"))
    has_email = bool(os.getenv("EASY_APPLY_EMAIL"))
    return has_resume and has_email


@app.get("/api/setup")
def api_setup_get():
    """Return whether setup is done (form or env) and current config (for pre-fill)."""
    if OVERRIDES_FILE.exists():
        try:
            data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
            out = {}
            for k, v in data.items():
                if k in ("GEMINI_API_KEY", "GROQ_API_KEY") and v and len(str(v)) > 8:
                    out[k] = str(v)[:4] + "…"
                else:
                    out[k] = v
            return {"configured": True, "config": out}
        except Exception:
            pass
    if _is_configured_from_env():
        return {"configured": True, "config": {}}
    return {"configured": False, "config": {}}


@app.post("/api/setup")
async def api_setup_post(
    cv_file: UploadFile = File(..., description="CV/Resume PDF (ATS-friendly)"),
    easy_apply_first_name: str = Form(""),
    easy_apply_last_name: str = Form(""),
    easy_apply_email: str = Form(""),
    job_search_country: str = Form(""),
    job_search_keywords: str = Form(""),
    default_location_city: str = Form(""),
    work_authorization_answer: str = Form("No"),
    work_need_sponsorship_answer: str = Form("Yes"),
    work_authorization_country: str = Form("Canada"),
    easy_apply_years_default: str = Form("3"),
    easy_apply_current_company: str = Form(""),
    easy_apply_current_title: str = Form(""),
    easy_apply_gender: str = Form(""),
    easy_apply_certifications: str = Form(""),
    easy_apply_hybrid_answer: str = Form("Yes"),
    min_delay_sec: str = Form("10"),
    max_delay_sec: str = Form("30"),
    gemini_api_key: str = Form(""),
    groq_api_key: str = Form(""),
):
    """Save setup form and uploaded CV; create config_overrides.json."""
    _ensure_data_dirs()
    if not cv_file.filename or not cv_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file (CV/Resume).")
    # Save single file for both resume and CV
    resume_path = UPLOADS_DIR / "resume.pdf"
    content = await cv_file.read()
    resume_path.write_bytes(content)
    abs_path = str(resume_path.resolve())
    payload = {
        "EASY_APPLY_FIRST_NAME": (easy_apply_first_name or "").strip(),
        "EASY_APPLY_LAST_NAME": (easy_apply_last_name or "").strip(),
        "EASY_APPLY_EMAIL": (easy_apply_email or "").strip(),
        "JOB_SEARCH_COUNTRY": (job_search_country or "").strip(),
        "JOB_SEARCH_KEYWORDS": (job_search_keywords or "").strip(),
        "DEFAULT_LOCATION_CITY": (default_location_city or "").strip(),
        "WORK_AUTHORIZATION_ANSWER": (work_authorization_answer or "No").strip(),
        "WORK_NEED_SPONSORSHIP_ANSWER": (work_need_sponsorship_answer or "Yes").strip(),
        "WORK_AUTHORIZATION_COUNTRY": (work_authorization_country or "Canada").strip(),
        "EASY_APPLY_YEARS_DEFAULT": (easy_apply_years_default or "3").strip(),
        "EASY_APPLY_CURRENT_COMPANY": (easy_apply_current_company or "").strip(),
        "EASY_APPLY_CURRENT_TITLE": (easy_apply_current_title or "").strip(),
        "EASY_APPLY_GENDER": (easy_apply_gender or "").strip(),
        "EASY_APPLY_CERTIFICATIONS": (easy_apply_certifications or "").strip(),
        "EASY_APPLY_HYBRID_ANSWER": (easy_apply_hybrid_answer or "Yes").strip(),
        "MIN_DELAY_SEC": (min_delay_sec or "10").strip(),
        "MAX_DELAY_SEC": (max_delay_sec or "30").strip(),
        "RESUME_PATH": abs_path,
        "CV_PATH": abs_path,
    }
    if (gemini_api_key or "").strip():
        payload["GEMINI_API_KEY"] = gemini_api_key.strip()
    if (groq_api_key or "").strip():
        payload["GROQ_API_KEY"] = groq_api_key.strip()
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "saved", "configured": True}


@app.get("/api/status")
def api_status():
    return {
        "running": _run_state["running"],
        "applied_count": _run_state["applied_count"],
        "error": _run_state.get("error"),
    }


def _run_start_steps():
    """Run start steps and raise with a clear step name on failure."""
    import main as main_mod
    if OVERRIDES_FILE.exists():
        try:
            import config
            config.apply_overrides_from_file()
        except Exception as e:
            raise RuntimeError(f"apply_overrides: {e!s}") from e
        for name, mod in [
            ("config", "config"),
            ("applier", "applier"),
            ("browser_engine", "browser_engine"),
            ("cv_reader", "cv_reader"),
            ("gemini_cv", "gemini_cv"),
            ("work_authorization", "work_authorization"),
            ("scraper", "scraper"),
            ("main", "main"),
        ]:
            try:
                m = __import__(mod)
                importlib.reload(m)
            except Exception as e:
                raise RuntimeError(f"reload {name}: {e!s}") from e
        main_mod = __import__("main")
    return main_mod


@app.post("/api/start")
async def api_start():
    global _run_task, _stop_event
    if _run_state["running"]:
        raise HTTPException(status_code=409, detail="Run already in progress")
    if not OVERRIDES_FILE.exists() and not _is_configured_from_env():
        raise HTTPException(
            status_code=400,
            detail="Please complete Setup first (profile + CV upload) or set RESUME_PATH, CV_PATH and EASY_APPLY_EMAIL in Railway Variables.",
        )

    try:
        main_mod = _run_start_steps()
        _run_state["running"] = True
        _run_state["applied_count"] = 0
        _run_state["error"] = None
        _stop_event = asyncio.Event()
        _run_task = asyncio.create_task(main_mod.main(state=_run_state, stop_event=_stop_event))

        def _done(_t):
            _run_state["running"] = False

        _run_task.add_done_callback(_done)
        return {"status": "started"}
    except Exception as e:
        _run_state["running"] = False
        _run_state["error"] = str(e)
        detail = f"Start failed: {e!s}"
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=detail) from e


@app.post("/api/stop")
async def api_stop():
    global _stop_event
    if not _run_state["running"] or _stop_event is None:
        return {"status": "not_running"}
    _stop_event.set()
    return {"status": "stop_requested"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

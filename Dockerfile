# Playwright Python image with Chromium and system deps (no need to run playwright install)
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Install Python deps (playwright already in image, pip will skip or upgrade)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir python-multipart

# App code (config, main, applier, web, etc.)
COPY config.py logger_config.py main.py daily_limit.py web_app.py ./
COPY applier.py browser_engine.py cv_reader.py scraper.py ./
COPY experience_map.py work_authorization.py gemini_cv.py ./
COPY dify_client.py ./
COPY static/ ./static/

# .env and linkedin_user_data/ are mounted at run time
# CV and resume paths: mount a volume or set RESUME_PATH/CV_PATH to paths inside container

# Default: run headless in container
ENV HEADLESS=true

# Avoid zombie processes; improve Chromium stability
# Web app: use PORT from Railway/Render (default 8000). For CLI-only run: docker run ... python -u main.py
ENV PORT=8000
EXPOSE 8000
# Shell form so Railway's PORT is used when set
ENTRYPOINT ["sh", "-c", "exec python -u -m uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}"]

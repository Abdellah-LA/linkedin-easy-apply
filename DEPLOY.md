# Deploying LinkedIn Easy Apply online (free) and multi-user

This guide explains how to run the app **online for free** and support **multiple users with different IP addresses**.

---

## How “multiple users” and “different IP” work

**Web app:** Open http://localhost:8000 to Start/Stop the loop and see status. Run: `python -m uvicorn web_app:app --host 0.0.0.0 --port 8000`. CLI only: `python -u main.py`.

- **One instance = one LinkedIn account.** The app uses a persistent browser session (cookies in `linkedin_user_data/`). Each run uses one account.
- **Different IP per user:**  
  - **Option A (recommended):** Each user runs **their own instance** (their own machine or their own cloud deployment). Each instance has one IP, so each user has a different IP.  
  - **Option B:** One server with **residential or mobile proxies** so each account uses a different IP (not covered here; would require proxy config in the app).

So for a free first step: **each user gets their own deployment or their own machine.** That gives you multiple users and different IPs naturally.

---

## 1. Run with Docker (same machine, one user)

Good for: your PC, a VPS, or any single server. One IP per machine.

### Prerequisites

- Docker and Docker Compose installed.
- A `.env` file (copy from `.env.example` and fill in LinkedIn, Gemini, job search, etc.).

### First-time login (non-headless)

LinkedIn needs a one-time login so the session can be saved. Run **once** with a visible browser:

```bash
# Build
docker compose build

# Run with browser visible to log in to LinkedIn (then stop and run normally)
docker compose run --rm -e HEADLESS=false linkedin-applier python -u main.py
```

On a **server without a display**, do the first login on your laptop with Docker, then copy the `linkedin_user_data` folder into the server and mount it in the same way.

### Normal run (web app + headless)

```bash
docker compose up --build
```

Then open **http://localhost:8000** in your browser. Use **Start** to begin applying and **Stop** to stop. Session is stored in the `linkedin_user_data` Docker volume; next runs reuse it (no login).

### CV / Resume inside Docker

Put your CV and resume PDFs in a folder (e.g. `./cv_resume/`) and mount it:

```yaml
volumes:
  - ./cv_resume:/app/cv_resume:ro
```

In `.env` (or in `docker-compose.yml` `environment`):

```env
RESUME_PATH=/app/cv_resume/your-resume.pdf
CV_PATH=/app/cv_resume/your-cv.pdf
```

---

## 2. Free cloud hosting (one deployment per user = one IP per user)

Each **deployment** = one user account and one IP. To support many users, each user deploys their own app (or you deploy one per user).

### Railway (free tier)

- Sign up: [railway.app](https://railway.app).
- New project → **Deploy from GitHub** (push this repo).
- Add **Dockerfile** as build (Railway detects it).
- In **Variables**, add all keys from `.env` (e.g. `GEMINI_API_KEY`, `JOB_SEARCH_COUNTRY`, `EASY_APPLY_EMAIL`, etc.).
- **Persistent data:** Add a **Volume**, mount path `/app/linkedin_user_data`. So LinkedIn session is kept between deploys.
- **First run:** You need one LinkedIn login. Either run once locally with `HEADLESS=false`, then copy `linkedin_user_data` into the volume, or use a “one-off” deploy with a browser (complex on Railway). Easiest: do first login locally, zip `linkedin_user_data`, then use Railway’s volume restore or a startup script that unpacks it once.
- Deploy. The app runs in a loop; when the free tier sleeps the container stops (no cron on free tier unless you use Cron jobs add-on).

**Result:** One user per Railway project. Different users = different projects or different accounts → different IPs (Railway’s outbound IP per project).

### Render (free tier)

- [render.com](https://render.com) → New **Background Worker** (not Web Service).
- Connect repo, build: **Docker**.
- Env vars: paste from `.env`.
- **Disk:** Add a persistent disk and mount at `/app/linkedin_user_data` (if Render supports it for workers; check current docs).
- Free tier sleeps after inactivity; when it wakes, the app will run again. No separate cron needed for “run once per day” unless you switch to a cron job later.

**Result:** One deployment per user → one IP per user.

### Fly.io (free tier)

- Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/), sign up.
- In the project folder:

```bash
fly launch
# Choose org, app name, region. Do not add PostgreSQL.
```

- Create `fly.toml` (or adjust the generated one) so the app runs the same Docker image and mounts a volume for `linkedin_user_data` (see [Fly Volumes](https://fly.io/docs/reference/volumes/)).
- Set secrets (env) from `.env`:

```bash
fly secrets set GEMINI_API_KEY=xxx EASY_APPLY_EMAIL=xxx ...
```

- Deploy: `fly deploy`.

**Result:** One app per user; each app has its own outbound IP.

### Oracle Cloud Free Tier (always-on VM)

- Create a free VM (e.g. Ubuntu 22.04).
- SSH in, install Docker and Docker Compose, clone the repo, add `.env`, then:

```bash
docker compose up -d --build
```

- Use a volume or bind mount for `linkedin_user_data` so session persists across restarts.
- First-time LinkedIn login: run once with `HEADLESS=false` (e.g. with X11 forwarding or a local run and then copy `linkedin_user_data` to the VM).

**Result:** One VM per user = one IP per user. Free and always on.

---

## 3. Summary: multi-user and different IPs

| Approach              | Who runs it     | Different IP?        | Cost   |
|-----------------------|-----------------|----------------------|--------|
| Docker on your PC     | You             | Your home/office IP  | Free   |
| Docker on VPS (Oracle, etc.) | You (or one user per VM) | One IP per VM   | Free tier |
| Railway / Render / Fly | Each user deploys their own | One IP per deployment | Free tier |
| Each user runs locally | Each user       | Yes (each user’s IP) | Free   |

For a **first step**: put the repo on GitHub, add the Dockerfile and this guide, then either:

- **Option 1:** Each user clones the repo and runs `docker compose up` on their own machine (each gets their own IP), or  
- **Option 2:** Each user deploys the same repo to Railway/Render/Fly with their own `.env` (one deployment per user = one IP per user).

No code changes are required for multi-user beyond what you already have: each instance is configured by its own `.env` and its own `linkedin_user_data/` (or volume).

---

## 4. Optional: run on a schedule (cron)

On a VPS or a host with cron:

```bash
# Every day at 9:00
0 9 * * * cd /path/to/repo && docker compose run --rm linkedin-applier
```

On Railway/Render you can use their cron or “scheduled run” features if available, or a separate cron service that hits a small “trigger” endpoint (you’d add a minimal HTTP server for that).

---

## 5. Security notes

- **Never commit `.env`** to Git. Use `.env.example` as a template only.
- On cloud hosts, use **Variables** / **Secrets** for all keys and secrets.
- LinkedIn session in `linkedin_user_data/` is sensitive; restrict volume/disk access to the app only.
- For multiple users on one server (not recommended for free tier), you’d need separate directories per user and a launcher that sets `USER_DATA_DIR` and env per user; that’s the next step after you validate one user per deployment.

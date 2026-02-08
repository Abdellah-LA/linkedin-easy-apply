# Deploy LinkedIn Easy Apply to the cloud (Option B) — step by step

This guide walks you through putting the app **online for free** so anyone with the link can use it. You’ll use **Railway** (or Render / Fly.io) and **GitHub**.

---

## What you get

- A **public URL** (e.g. `https://your-app.up.railway.app`)
- **Web UI**: first-time visitors see a **Setup form** (name, email, job search, country, CV upload, etc.). After saving, they see **Start** / **Stop** and status.
- **One deployment = one LinkedIn account**. Everyone who opens the link shares the same run. For separate accounts, each user deploys their own app (see end of doc).

---

## Prerequisites

- A **GitHub** account
- A **Railway** account (free at [railway.app](https://railway.app))
- Your repo pushed to GitHub (this project: main branch with Dockerfile, `web_app.py`, `static/`, etc.)

---

## Step 1: Push the repo to GitHub

1. Create a **new repository** on GitHub (e.g. `linkedin-easy-apply`).
2. On your machine, in the project folder:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

(If the repo already exists, just push the latest code.)

**Important:** Do **not** commit `.env` or `linkedin_user_data/`. Add them to `.gitignore` (they should already be there).

---

## Step 2: Create a Railway project and deploy from GitHub

1. Go to [railway.app](https://railway.app) and sign in (e.g. with GitHub).
2. Click **New Project**.
3. Choose **Deploy from GitHub repo**.
4. Select your repository and the branch (e.g. `main`).
5. Railway will detect the **Dockerfile** and start building. Wait for the first build to finish (it may fail until you add variables and volume — that’s OK).

---

## Step 3: Add a persistent volume (for LinkedIn session + setup data)

1. In your Railway project, open your **service** (the one that was created from the repo).
2. Go to the **Variables** tab first (we’ll add env vars in the next step).
3. Go to the **Settings** tab (or **Volumes** in the left menu if available).
4. Click **Add Volume** (or **New Volume**).
5. **Mount path:**  
   `/app/linkedin_user_data`  
   (This is where the browser session is stored so you don’t have to log in to LinkedIn on every deploy.)
6. Add a **second volume** (if Railway allows multiple):  
   **Mount path:**  
   `/app/data`  
   (This stores the web form config and uploaded CV so they persist between deploys.)
7. If Railway only allows one volume, use:  
   **Mount path:**  
   `/app/linkedin_user_data`  
   and accept that form data/CV might be reset on redeploy unless you use a single volume that includes both (e.g. mount `/app/data` and store `linkedin_user_data` inside it — then set env `USER_DATA_DIR=/app/data/linkedin_user_data`).

**Summary:** At least one volume at `/app/linkedin_user_data`; ideally another at `/app/data`.

---

## Step 4: Set environment variables

In Railway: **Your service → Variables** (or **Environment**). Add variables so the app can run. You can copy these from your local `.env`; **do not** paste secrets into this doc.

**Optional: skip the Setup form** — If you set all variables here (including `RESUME_PATH` and `CV_PATH` pointing to a file inside the container), the app will show the dashboard directly and you can Start without filling the form. To do that, mount a volume with your CV (e.g. at `/app/cv_resume`) and set `RESUME_PATH=/app/cv_resume/your-resume.pdf` and `CV_PATH=/app/cv_resume/your-resume.pdf`. Otherwise, use the web form once to upload your CV.

**Required / recommended:**

| Variable | Example | Note |
|---------|--------|------|
| `HEADLESS` | `true` | Must be `true` on Railway (no display). |
| `GEMINI_API_KEY` | `your_key` | For AI answers from CV (optional if you set it in the web form). |
| `GROQ_API_KEY` | (optional) | Fallback for AI. |
| `USER_DATA_DIR` | `/app/linkedin_user_data` | So session uses the volume. |

**Optional (users can set these in the web Setup form instead):**

- `JOB_SEARCH_COUNTRY`, `JOB_SEARCH_KEYWORDS`, `EASY_APPLY_EMAIL`, `EASY_APPLY_FIRST_NAME`, `EASY_APPLY_LAST_NAME`, `DEFAULT_LOCATION_CITY`, `WORK_AUTHORIZATION_ANSWER`, `WORK_NEED_SPONSORSHIP_ANSWER`, `WORK_AUTHORIZATION_COUNTRY`, `EASY_APPLY_YEARS_DEFAULT`, `EASY_APPLY_CURRENT_COMPANY`, `EASY_APPLY_CURRENT_TITLE`, `EASY_APPLY_GENDER`, `EASY_APPLY_CERTIFICATIONS`, `EASY_APPLY_HYBRID_ANSWER`, `MIN_DELAY_SEC`, `MAX_DELAY_SEC`.

If you set them here, they are used until the user saves the Setup form; after that, form data (stored in `/app/data/config_overrides.json`) overrides them when they click **Start**.

**Security:** Never commit `.env` or paste real API keys into docs. Use only Railway’s Variables UI for secrets.

---

## Step 5: Expose the web app (public URL)

1. In Railway, open your service.
2. Go to **Settings** and find **Networking** or **Public Networking**.
3. Click **Generate Domain** (or **Add public URL**). Railway will assign a URL like `https://your-app.up.railway.app`.
4. Ensure the service listens on **port 8000** (the Dockerfile already does this).

Open the URL in your browser. You should see the **LinkedIn Easy Apply** page.

---

## Step 6: First-time setup in the web UI

1. Open your Railway URL (e.g. `https://your-app.up.railway.app`).
2. You’ll see the **Setup** form. Fill in:
   - First name, last name, email (for Easy Apply)
   - Job search country and keywords
   - Default city, work authorization answers, current company/title, gender, certifications, hybrid preference
   - **CV / Resume:** upload a **PDF** (ATS-friendly: clear headings, keywords, simple layout)
   - Optionally Gemini/Groq API keys (if not set in Railway variables)
3. Click **Save and continue**. You’ll see the **dashboard** (Start / Stop, status).

**Important:** The app uses a **persistent browser session** for LinkedIn. The first time you click **Start**, the app will open a headless browser and go to LinkedIn. On Railway there is no display, so **you must do the first LinkedIn login elsewhere** and then copy the session into the volume (see Step 7). Until then, Start may fail at “navigation” or “login”.

---

## Step 7: First-time LinkedIn login (required once)

LinkedIn needs a one-time login so the session can be saved. On Railway the app runs headless and cannot show a login page. Use one of these:

**Option A — Login on your PC, then copy session to Railway**

1. On your **local machine**, in the project folder, create or use `linkedin_user_data/` and run **once** with a visible browser:
   ```bash
   set HEADLESS=false
   python -m uvicorn web_app:app --host 0.0.0.0 --port 8000
   ```
   Or run only the main script and log in:
   ```bash
   set HEADLESS=false
   python main.py
   ```
   Log in to LinkedIn in the browser that opens; then close the app. The folder `linkedin_user_data/` will now contain the session.

2. **Zip** the `linkedin_user_data` folder and upload it to a place you can reach (e.g. a private file or Railway volume restore). On Railway, you may need to use their **volume backup/restore** or a one-off job that writes files into the volume. If Railway supports “run a command in the container”, you could run a script that downloads your zip and extracts it into `/app/linkedin_user_data`.

**Option B — Use Railway’s “one-off run” with a browser (if available)**

Some platforms let you run a one-off job with a visible browser or a different entrypoint. If Railway supports this, run the app once with `HEADLESS=false` and complete login; then switch back to the normal headless deploy.

**Option C — Deploy the same app on your PC first**

Run the app locally with Docker or uvicorn, log in once so `linkedin_user_data/` is created, then copy that folder into the server/volume used by Railway (e.g. via volume restore or a custom deploy step).

After the session is in `/app/linkedin_user_data`, the next time you click **Start** on the Railway URL, the bot should use the saved session and not ask for login again.

---

## Step 8: Use the app

1. Open the Railway URL.
2. If you haven’t completed Setup, fill the form (including CV upload) and **Save and continue**.
3. On the dashboard, click **Start** to begin the Easy Apply loop. Click **Stop** to stop it. “Applied this run” shows how many applications were sent.
4. You can click **Edit setup** to change profile or re-upload the CV; then **Save and continue** again before the next run.

---

## Render (alternative to Railway)

1. Go to [render.com](https://render.com) → **New** → **Background Worker** (or **Web Service** if you want a public URL).
2. Connect your GitHub repo. Set **Build** to **Docker**.
3. Add **environment variables** (same as in the table above: `HEADLESS=true`, `GEMINI_API_KEY`, etc.).
4. If Render supports **persistent disk**, add a disk and mount it at `/app/linkedin_user_data` (and optionally `/app/data`).
5. For a **Web Service**, set the start command to run the web app (e.g. `uvicorn web_app:app --host 0.0.0.0 --port 8000`) and expose port 8000. Render will give you a URL like `https://your-app.onrender.com`.

First-time LinkedIn login: same idea as Step 7 — do it locally and copy `linkedin_user_data` into the persistent disk if possible.

---

## Fly.io (alternative)

1. Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/) and sign in.
2. In the project folder: `fly launch` (choose org, app name, region; do not add Postgres).
3. Add a **volume** for the session:  
   `fly volumes create linkedin_data --size 1 --region YOUR_REGION`  
   Mount it in `fly.toml` at `/app/linkedin_user_data`.
4. Set secrets (env):  
   `fly secrets set HEADLESS=true GEMINI_API_KEY=your_key USER_DATA_DIR=/app/linkedin_user_data`
5. Deploy: `fly deploy`. Your URL will be like `https://your-app.fly.dev`.

Again, do the first LinkedIn login locally and copy the session into the volume (e.g. via `fly ssh` and uploading the folder).

---

## Multiple users / separate LinkedIn accounts

- **Same link, same account:** Everyone who has the link uses the same deployment and the same LinkedIn account (whoever clicks Start runs the bot for that account).
- **Different accounts:** Each user should deploy their **own** instance (their own Railway/Render/Fly project) with their own GitHub fork or repo, their own env vars, and their own volume. Then each user has their own URL and their own LinkedIn session.

---

## Summary checklist (Railway)

- [ ] Repo on GitHub (no `.env` or `linkedin_user_data` committed)
- [ ] Railway project → Deploy from GitHub (Dockerfile)
- [ ] Volume(s): `/app/linkedin_user_data`, and ideally `/app/data`
- [ ] Variables: `HEADLESS=true`, `GEMINI_API_KEY`, `USER_DATA_DIR=/app/linkedin_user_data`
- [ ] Public domain generated (port 8000)
- [ ] Open URL → complete **Setup** form (profile + CV upload) → **Save and continue**
- [ ] First-time LinkedIn login done (session in volume)
- [ ] Click **Start** on the dashboard to run the bot

After that, you can share the link so others can use the same run, or each user can deploy their own app for their own account.

---

## If the service shows "Crashed"

1. **Check the logs**  
   In Railway: open your service → **Deployments** → click the latest deployment → **View Logs** (or **Logs** tab). The last lines usually show the Python traceback or error (e.g. port in use, missing env, import error).

2. **Set these variables (required on Railway)**  
   - **`HEADLESS`** = `true` (no display in the cloud).  
   - **`PORT`** – Railway sets this automatically; the Dockerfile now uses it. You don’t need to add it unless you want to override.

3. **Fix or remove Dify variables**  
   If you see **`DIFY_API_KEY`** with a placeholder like `your_generated_app_key_here`:
   - **If you use Dify:** In [Dify](https://dify.ai), create an API key for your workflow and set **`DIFY_API_KEY`** to that value in Railway Variables.  
   - **If you don’t use Dify:** The Easy Apply bot can run without Dify (it uses Gemini for CV answers). You can **remove** `DIFY_API_KEY`, `DIFY_BASE_URL`, `DIFY_CV_FILE_ID`, and `DIFY_USER` from Railway Variables, or leave them empty. The app will skip Dify and use Gemini.

4. **Redeploy**  
   After changing variables, trigger a new deployment (e.g. **Deploy** → **Redeploy** or push a commit). The Dockerfile was updated so the app listens on Railway’s **PORT**; push that change if you haven’t already.

# Fix: "The process cannot access the file" when installing

## Option 1: Install with `--user` (avoids locked global folder)

Close **all** other terminals and any app that might be running Python (Cursor, VS Code, etc.). Then:

```powershell
pip install --user pypdf google-genai
```

Then run the test:

```powershell
python test_gemini.py
```

---

## Option 2: Use a project virtual environment (recommended)

This installs packages in the project’s `.venv` folder, so the global Python folder is not touched.

1. **Create a venv** (once):

   ```powershell
   cd "d:\Pricticing AI Agent Dify\Super Linkedin Scraper"
   python -m venv .venv
   ```

2. **Activate it** (do this in every new terminal before running the project):

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   If you get a script execution error, run:

   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

   Then run the activate command again.

3. **Install dependencies** (inside the activated venv):

   ```powershell
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Run the test**:

   ```powershell
   python test_gemini.py
   ```

From then on, always **activate** the venv (step 2) in this project’s terminal before running `python main.py` or `python test_gemini.py`.

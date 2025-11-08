# Anime URL Shortener (Flask)

Quick local Flask-based URL shortener. Uses MySQL to persist links. The UI is in `templates/index.html` and posts to `/shorten`.

Prerequisites
- Python 3.8+
- MySQL server running locally

Setup (PowerShell)

1. Create the database (run in PowerShell, adjust path to `mysql` if needed):

```powershell
mysql -u root -p2702 -e "CREATE DATABASE IF NOT EXISTS vairam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

2. Create and activate a virtual environment, install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
```

The app listens on port 3000 by default. Open http://localhost:3000/ in your browser.

Notes
- The app will create the `urls` table automatically on first shorten request. The DB credentials are in `app.py` (DB_CONFIG). Update them if your environment differs.
- The UI uses CDNs for Bootstrap and QR code generation.

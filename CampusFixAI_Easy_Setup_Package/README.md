# CampusFix AI — G.P. Purnea (Windows local demo)

## Start the project (recommended)
1. Extract this ZIP.
2. Open the **CampusFixAI_GPPurnea_Ready** folder in VS Code (the folder that directly contains `app.py` and `requirements.txt`).
3. Double-click `START_CAMPUSFIXAI.bat`.
4. Wait for package installation. The first run needs internet.
5. Enter campus coordinates/radius (Enter keeps the approximate defaults) and create the admin email/password.
6. The launcher opens **http://127.0.0.1:5000**. Keep the black terminal window open.

## Camera and GPS — important
- On the same computer, use exactly `http://127.0.0.1:5000` or `http://localhost:5000`.
- Do not use the computer's LAN IP (for example `http://192.168...`), a VS Code Live Server address, or a `file:///` address. Chrome blocks camera/GPS on ordinary HTTP network origins.
- On an online deployment, use an HTTPS URL.
- On the complaint page, click **Open camera / Retry** and allow Camera. Then click **Capture photo**.
- Click **Verify my location** and allow Location. GPS is checked against the configured campus centre/radius.
- If a permission was blocked earlier, use Chrome's site settings to change Camera and Location to Allow, then reload.
- If the device has no camera or permission is denied, select an image file instead. GPS still requires a supported secure browser context.

## Features in this prototype
Student registration/login, complaint submission, photo evidence, campus-radius GPS check, category/priority suggestion, department assignment, similar-complaint check, complaint history/tracking, admin/staff dashboard, status updates, resolution photo, CSV reports, analytics endpoint, optional email notifications, SQLite storage, password hashing and CSRF protection.

The classifier is a small sample-data ML baseline when scikit-learn is installed; otherwise it uses keyword rules. It is not a production-grade AI model.

## Admin
The first admin is created using the email/password entered in the launcher. Log in with those credentials and open **/admin**. Keep the password private.

## Manual VS Code terminal setup
Run these commands from the folder containing `app.py` and `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then set the environment variables in PowerShell (replace the example admin values) and start:

```powershell
$env:CAMPUS_LAT="25.7629"
$env:CAMPUS_LON="87.4675"
$env:CAMPUS_RADIUS_M="1000"
$env:CAMPUSFIX_ADMIN_EMAIL="admin@example.com"
$env:CAMPUSFIX_ADMIN_PASSWORD="Use-A-Strong-Password-123"
$env:SECRET_KEY=python -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000.

## Troubleshooting
- `requirements.txt not found`: open the inner `CampusFixAI_GPPurnea_Ready` folder, not its parent.
- `No module named flask`: run the pip install command above from the correct folder.
- Camera/GPS says secure origin: use exactly `http://127.0.0.1:5000` on this computer or use HTTPS online.
- Camera denied: Chrome address bar site settings → Camera → Allow.
- GPS denied: Chrome address bar site settings → Location → Allow; turn on Windows Location Services.
- Campus boundary rejected: verify the college pin coordinates and increase/decrease radius only after checking the actual campus boundary.

## Notes
The coordinates 25.7629, 87.4675 are approximate defaults and must be checked against the actual G.P. Purnea campus pin. GPS is a practical boundary check, not tamper-proof proof of physical presence. This package was checked for ZIP integrity and Python syntax; it has not been tested on your individual Windows PC, camera, GPS hardware, or network. For real college-wide use, deploy behind HTTPS with a production server, managed database, backups and stronger operational controls.

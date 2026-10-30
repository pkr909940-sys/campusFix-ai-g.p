CAMPUSFIX AI — EASY SETUP (WINDOWS)

IMPORTANT: This package does NOT include a .bat launcher, so Windows Smart App Control will not block that launcher. Do not turn off Windows security.

1) Extract this ZIP (Right-click > Extract All).
2) Open the extracted CampusFixAI folder in VS Code (File > Open Folder).
   IMPORTANT: app.py and requirements.txt must be visible directly in the opened folder.
3) In VS Code choose Terminal > New Terminal.
4) Copy and run these commands ONE BY ONE in the terminal:

   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt

5) Set local demo settings (replace the admin password with your own):

   $env:CAMPUS_LAT="25.7629"
   $env:CAMPUS_LON="87.4675"
   $env:CAMPUS_RADIUS_M="1000"
   $env:CAMPUSFIX_ADMIN_EMAIL="admin@example.com"
   $env:CAMPUSFIX_ADMIN_PASSWORD="ChangeThis-Strong-Password-123"
   $env:SECRET_KEY=py -c "import secrets; print(secrets.token_hex(32))"

6) Start the website:

   .\.venv\Scripts\python.exe app.py

7) Keep the VS Code terminal open. Open Chrome and visit:
   http://127.0.0.1:5000

STOPPING: Press Ctrl+C in the VS Code terminal when you want to stop the local website.
NEXT TIME: Open the same project folder in VS Code, open Terminal, and run only:
   .\.venv\Scripts\python.exe app.py

CAMERA/GPS: On this computer use exactly http://127.0.0.1:5000 or http://localhost:5000 and allow Camera and Location in Chrome. For a public website, HTTPS is required.

CAMPUS GPS: 25.7629, 87.4675 is an APPROXIMATE G.P. Purnea coordinate and 1000m is a demo radius. Verify the exact campus pin before relying on GPS verification.

ADMIN: Sign in with the email/password set above. Keep the password private.

LIMITATIONS: This is a local demo prototype. It uses SQLite and local photo storage; do not use it for real college-wide sensitive complaints until deployed with persistent managed database, persistent photo storage, backups, HTTPS and proper admin/security review. The optional classifier is a small baseline, not production-grade AI.

VALIDATION: The package structure and Python syntax were checked. It has NOT been tested on your Windows computer, camera, GPS hardware or network. Python 3.10+ recommended. Internet is needed for the first dependency installation.

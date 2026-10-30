import os, io, csv, math, base64, secrets, sqlite3, smtplib
from email.message import EmailMessage
from datetime import datetime
from functools import wraps
from uuid import uuid4
from difflib import SequenceMatcher
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_from_directory, Response
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    ML_AVAILABLE = True
except Exception:
    ML_AVAILABLE = False

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
COMPLAINT_UPLOADS = os.path.join(UPLOAD_ROOT, "complaints")
RESOLUTION_UPLOADS = os.path.join(UPLOAD_ROOT, "resolutions")
os.makedirs(COMPLAINT_UPLOADS, exist_ok=True)
os.makedirs(RESOLUTION_UPLOADS, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", ""),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)
if not app.config["SECRET_KEY"]:
    # Local development fallback only. Set a random SECRET_KEY in deployment.
    app.config["SECRET_KEY"] = secrets.token_hex(32)
CSRFProtect(app)
DB = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "campusfix.db"))
ALLOWED_STATUSES = {"Pending", "In Progress", "Resolved"}
CAMPUS_LAT = os.getenv("CAMPUS_LAT", "").strip()
CAMPUS_LON = os.getenv("CAMPUS_LON", "").strip()
CAMPUS_RADIUS_M = float(os.getenv("CAMPUS_RADIUS_M", "1000"))

CATEGORY_RULES = {
    "IT / Network": ["wifi", "wi-fi", "internet", "computer", "pc", "laptop", "projector", "printer", "network", "software", "keyboard", "mouse", "server"],
    "Electrical": ["fan", "light", "electricity", "switch", "socket", "ac", "air conditioner", "power", "bulb", "sparking", "shock"],
    "Maintenance": ["water", "leak", "leakage", "washroom", "toilet", "door", "window", "chair", "desk", "cleaning", "floor", "tap", "broken bench"],
    "Library": ["book", "library", "issue", "return", "card", "reading room"],
    "Safety": ["fire", "smoke", "unsafe", "emergency", "accident", "security", "fight", "harassment", "exit", "lock", "injury"],
    "Academic": ["teacher", "class", "lecture", "attendance", "exam", "timetable", "marks", "assignment", "syllabus"]
}
DEPARTMENT = {"IT / Network":"IT Department", "Electrical":"Electrical Department", "Maintenance":"Maintenance Team", "Library":"Library Department", "Safety":"Administration / Security", "Academic":"Academic Department", "Other":"Administration"}
HIGH_WORDS = ["emergency", "fire", "smoke", "accident", "unsafe", "security", "harassment", "electric shock", "sparking", "locked exit", "injury"]
MEDIUM_WORDS = ["not working", "broken", "leak", "leakage", "wifi", "internet", "projector", "computer", "fan", "water"]

# Small built-in labelled examples train a lightweight ML baseline. Expand with verified campus examples for better accuracy.
TRAINING = {
 "IT / Network": ["campus wifi is not working", "internet connection is down", "projector does not work in classroom", "computer lab pc is broken", "printer and keyboard issue", "network server software error", "laptop cannot connect to wifi"],
 "Electrical": ["classroom fan is not working", "light bulb is broken", "electric switch is sparking", "power socket has electric shock", "air conditioner has no power", "electricity problem in lab"],
 "Maintenance": ["water is leaking from tap", "washroom toilet is blocked", "classroom chair and desk are broken", "door window needs repair", "floor cleaning required", "water leakage in corridor"],
 "Library": ["library book issue and return problem", "library card is not working", "book is missing from library", "reading room is closed", "need to return a book"],
 "Safety": ["fire and smoke in the building", "emergency exit is locked", "unsafe corridor and security issue", "harassment complaint", "accident and injury on campus", "someone is fighting near gate"],
 "Academic": ["teacher did not take class", "attendance record is incorrect", "exam timetable issue", "marks are missing", "assignment submission problem", "lecture schedule needs correction"]
}
ML_MODEL = None
if ML_AVAILABLE:
    try:
        _texts, _labels = [], []
        for _label, _samples in TRAINING.items():
            _texts.extend(_samples); _labels.extend([_label] * len(_samples))
        ML_MODEL = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), stop_words="english")), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))])
        ML_MODEL.fit(_texts, _labels)
    except Exception:
        ML_MODEL = None

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def connect_db():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = connect_db()
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, location TEXT NOT NULL,
        latitude REAL, longitude REAL, campus_distance_m REAL, description TEXT NOT NULL,
        photo_filename TEXT NOT NULL, category TEXT NOT NULL, priority TEXT NOT NULL,
        department TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, resolution_photo_filename TEXT, staff_notes TEXT,
        classifier_method TEXT, confidence REAL,
        FOREIGN KEY(user_id) REFERENCES users(id))""")
    # Migrate an older prototype database without deleting existing complaint records.
    existing = {r[1] for r in con.execute("PRAGMA table_info(complaints)").fetchall()}
    additions = {
        "user_id":"INTEGER", "latitude":"REAL", "longitude":"REAL", "campus_distance_m":"REAL",
        "photo_filename":"TEXT NOT NULL DEFAULT ''", "updated_at":"TEXT NOT NULL DEFAULT ''",
        "resolution_photo_filename":"TEXT", "staff_notes":"TEXT", "classifier_method":"TEXT", "confidence":"REAL"
    }
    for col, typ in additions.items():
        if col not in existing:
            con.execute(f"ALTER TABLE complaints ADD COLUMN {col} {typ}")
    con.commit(); con.close()
    admin_email = os.getenv("CAMPUSFIX_ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("CAMPUSFIX_ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        con = connect_db()
        found = con.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
        if not found:
            con.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)", ("CampusFix Admin", admin_email, generate_password_hash(admin_password), "admin", now()))
            con.commit()
        con.close()

@app.cli.command("init-db")
def init_db_command():
    init_db(); print("Database initialized. Configure CAMPUSFIX_ADMIN_EMAIL and CAMPUSFIX_ADMIN_PASSWORD to bootstrap an admin.")

@app.cli.command("create-admin")
def create_admin_command():
    """Create an admin from environment variables: CAMPUSFIX_ADMIN_EMAIL/PASSWORD."""
    email = os.getenv("CAMPUSFIX_ADMIN_EMAIL", "").strip().lower(); password = os.getenv("CAMPUSFIX_ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        raise SystemExit("Set CAMPUSFIX_ADMIN_EMAIL and CAMPUSFIX_ADMIN_PASSWORD (at least 12 characters).")
    init_db()
    con = connect_db()
    found = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if found:
        con.execute("UPDATE users SET role='admin', password_hash=? WHERE email=?", (generate_password_hash(password), email))
        con.commit(); con.close(); print("Existing account promoted/reset as admin.")
        return
    con.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)", ("CampusFix Admin", email, generate_password_hash(password), "admin", now()))
    con.commit(); con.close(); print("Admin created.")

@app.before_request
def ensure_database():
    if not getattr(app, "_db_ready", False):
        init_db(); app._db_ready = True

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "warning"); return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles: abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def classify(description):
    text = description.lower()
    scores = {cat: sum(1 for word in words if word in text) for cat, words in CATEGORY_RULES.items()}
    rule_category = max(scores, key=scores.get) if scores else "Other"
    if scores.get(rule_category, 0) == 0: rule_category = "Other"
    category, confidence, method = rule_category, 0.0, "keyword fallback"
    if ML_MODEL is not None:
        try:
            probs = ML_MODEL.predict_proba([text])[0]
            idx = int(probs.argmax()); ml_category = str(ML_MODEL.classes_[idx]); ml_conf = float(probs[idx])
            # Safety keywords take precedence; otherwise use ML only when it is reasonably confident.
            if any(word in text for word in HIGH_WORDS) and rule_category == "Safety":
                category, confidence, method = "Safety", max(ml_conf, 0.75), "safety override + ML"
            elif ml_conf >= 0.30:
                category, confidence, method = ml_category, ml_conf, "TF-IDF + LogisticRegression baseline"
            else:
                category, confidence, method = rule_category, ml_conf, "keyword fallback"
        except Exception: pass
    if any(word in text for word in HIGH_WORDS): priority = "High"
    elif any(word in text for word in MEDIUM_WORDS): priority = "Medium"
    else: priority = "Low"
    return category, priority, DEPARTMENT.get(category, "Administration"), method, confidence

def find_similar(description, location):
    con = connect_db()
    rows = con.execute("SELECT id, description FROM complaints WHERE lower(location)=lower(?) ORDER BY id DESC LIMIT 100", (location,)).fetchall()
    con.close()
    matches = []
    for row in rows:
        score = SequenceMatcher(None, description.lower(), row["description"].lower()).ratio()
        if score >= 0.48:
            matches.append({"id": row["id"], "score": score})
    return matches

def campus_distance(lat, lon):
    if not CAMPUS_LAT or not CAMPUS_LON: return None
    try: clat, clon = float(CAMPUS_LAT), float(CAMPUS_LON)
    except ValueError: return None
    radius = 6371000
    p1, p2 = math.radians(clat), math.radians(lat)
    dp, dl = math.radians(lat - clat), math.radians(lon - clon)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def save_image_bytes(data, folder):
    try:
        image = Image.open(io.BytesIO(data)); image.verify()
        image = Image.open(io.BytesIO(data)); image = image.convert("RGB")
        image.thumbnail((1600, 1600))
        filename = f"{uuid4().hex}.jpg"
        target = os.path.join(folder, filename)
        image.save(target, format="JPEG", quality=85, optimize=True)
        return filename
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Please upload a valid JPG, PNG or WebP image.")

def get_image_from_request(data_field, file_field, folder):
    data_url = request.form.get(data_field, "").strip()
    if data_url:
        if "," not in data_url or not data_url.startswith("data:image/"):
            raise ValueError("Invalid camera image format.")
        try: raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except Exception: raise ValueError("Could not read the captured image.")
        if len(raw) > 4 * 1024 * 1024: raise ValueError("Image is too large. Please capture a smaller photo.")
        return save_image_bytes(raw, folder)
    uploaded = request.files.get(file_field)
    if uploaded and uploaded.filename:
        if len(uploaded.read()) > 4 * 1024 * 1024: raise ValueError("Image must be smaller than 4 MB.")
        uploaded.stream.seek(0)
        return save_image_bytes(uploaded.read(), folder)
    raise ValueError("A problem photo is required. Use live camera capture or choose an image.")

def send_email(to_email, subject, body):
    host = os.getenv("SMTP_HOST", "").strip(); username = os.getenv("SMTP_USERNAME", "").strip(); password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username).strip(); port = int(os.getenv("SMTP_PORT", "587"))
    if not host or not sender or not to_email:
        app.logger.info("Email not sent (SMTP not configured). To=%s Subject=%s", to_email, subject); return False
    try:
        msg = EmailMessage(); msg["Subject"] = subject; msg["From"] = sender; msg["To"] = to_email; msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if username and password: server.login(username, password)
            server.send_message(msg)
        return True
    except Exception as exc:
        app.logger.warning("Email delivery failed: %s", exc); return False

def admin_emails():
    con = connect_db(); rows = con.execute("SELECT email FROM users WHERE role IN ('admin','staff')").fetchall(); con.close()
    return [r["email"] for r in rows]

@app.route("/")
def index():
    return render_template("index.html", logged_in=bool(session.get("user_id")))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]; email = request.form.get("email", "").strip().lower(); password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 8:
            flash("Name/email valid rakhein aur password kam se kam 8 characters ka ho.", "danger"); return render_template("register.html")
        con = connect_db()
        try:
            con.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)", (name,email,generate_password_hash(password),"student",now())); con.commit()
            flash("Account created. Ab login karein.", "success"); return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Is email se account pehle se hai.", "danger")
        finally: con.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower(); password = request.form.get("password", "")
        con = connect_db(); user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone(); con.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["user_id"] = user["id"]; session["name"] = user["name"]; session["email"] = user["email"]; session["role"] = user["role"]
            flash("Welcome back!", "success")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"): return redirect(next_url)
            return redirect(url_for("admin" if user["role"] in ("admin", "staff") else "my_complaints"))
        flash("Email ya password sahi nahi hai.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear(); flash("You have been logged out.", "success"); return redirect(url_for("index"))

@app.route("/submit", methods=["GET", "POST"])
@roles_required("student", "admin", "staff")
def submit():
    if request.method == "GET": return render_template("submit.html")
    name = session.get("name", "Anonymous"); location = request.form.get("location", "").strip()[:160]; description = request.form.get("description", "").strip()[:2000]
    try: lat, lon = float(request.form.get("latitude", "nan")), float(request.form.get("longitude", "nan"))
    except ValueError: lat, lon = float("nan"), float("nan")
    if not location or not description or not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        flash("Location, description aur valid GPS coordinates zaroori hain.", "danger"); return redirect(url_for("submit"))
    distance = campus_distance(lat, lon)
    if distance is None:
        flash("Campus GPS setup nahi hua. Admin ko CAMPUS_LAT aur CAMPUS_LON configure karna hoga.", "danger"); return redirect(url_for("submit"))
    if distance > CAMPUS_RADIUS_M:
        flash(f"Aap campus boundary ke bahar lag rahe hain ({distance:.0f} m). Campus ke andar se report submit karein.", "danger"); return redirect(url_for("submit"))
    try: photo_filename = get_image_from_request("photo_data", "photo_file", COMPLAINT_UPLOADS)
    except ValueError as exc:
        flash(str(exc), "danger"); return redirect(url_for("submit"))
    category, priority, department, method, confidence = classify(description)
    similar_matches = find_similar(description, location)
    con = connect_db()
    cur = con.execute("INSERT INTO complaints(user_id,name,location,latitude,longitude,campus_distance_m,description,photo_filename,category,priority,department,status,created_at,updated_at,classifier_method,confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,'Pending',?,?,?,?)",
        (session["user_id"],name,location,lat,lon,distance,description,photo_filename,category,priority,department,now(),now(),method,confidence))
    complaint_id = cur.lastrowid; con.commit(); con.close()
    for email in admin_emails(): send_email(email, f"New CampusFix complaint #{complaint_id}", f"A new {priority} priority complaint was submitted.\nCategory: {category}\nLocation: {location}\nPlease sign in to review it.")
    send_email(session.get("email"), f"CampusFix complaint #{complaint_id} received", f"Your complaint has been received.\nTracking ID: {complaint_id}\nCategory: {category}\nPriority: {priority}\nStatus: Pending")
    return render_template("result.html", complaint_id=complaint_id, location=location, description=description, category=category, priority=priority, department=department, method=method, confidence=confidence, similar_count=len(similar_matches))

@app.route("/my-complaints")
@login_required
def my_complaints():
    con = connect_db(); rows = con.execute("SELECT * FROM complaints WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall(); con.close()
    return render_template("my_complaints.html", complaints=rows)

@app.route("/complaint/<int:complaint_id>")
@login_required
def complaint_detail(complaint_id):
    con = connect_db(); row = con.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone(); con.close()
    if not row: abort(404)
    if row["user_id"] != session.get("user_id") and session.get("role") not in ("admin", "staff"): abort(403)
    return render_template("complaint_detail.html", c=row)

@app.route("/uploads/<kind>/<filename>")
@login_required
def uploaded_image(kind, filename):
    if kind not in ("complaints", "resolutions"): abort(404)
    # Uploaded images are served only to logged-in users; complaint ownership is checked by matching filename.
    con = connect_db()
    if kind == "complaints": row = con.execute("SELECT user_id FROM complaints WHERE photo_filename=?", (filename,)).fetchone()
    else: row = con.execute("SELECT user_id FROM complaints WHERE resolution_photo_filename=?", (filename,)).fetchone()
    con.close()
    if not row: abort(404)
    if row["user_id"] != session.get("user_id") and session.get("role") not in ("admin", "staff"): abort(403)
    folder = COMPLAINT_UPLOADS if kind == "complaints" else RESOLUTION_UPLOADS
    return send_from_directory(folder, secure_filename(filename), max_age=0)

@app.route("/admin")
@roles_required("admin", "staff")
def admin():
    q = request.args.get("q", "").strip()[:100]; status_filter = request.args.get("status", "")
    con = connect_db()
    sql = "SELECT c.*, u.email AS student_email FROM complaints c LEFT JOIN users u ON c.user_id=u.id WHERE 1=1"; params=[]
    if status_filter in ALLOWED_STATUSES: sql += " AND c.status=?"; params.append(status_filter)
    if q:
        sql += " AND (CAST(c.id AS TEXT)=? OR c.location LIKE ? OR c.description LIKE ? OR c.category LIKE ?)"; params.extend([q, f"%{q}%",f"%{q}%",f"%{q}%"])
    sql += " ORDER BY CASE c.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, c.id DESC"
    complaints = con.execute(sql, params).fetchall()
    total = con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    pending = con.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'").fetchone()[0]
    progress = con.execute("SELECT COUNT(*) FROM complaints WHERE status='In Progress'").fetchone()[0]
    resolved = con.execute("SELECT COUNT(*) FROM complaints WHERE status='Resolved'").fetchone()[0]
    users = con.execute("SELECT id,name,email,role,created_at FROM users ORDER BY id DESC").fetchall() if session.get("role") == "admin" else []
    con.close()
    return render_template("admin.html", complaints=complaints, total=total, pending=pending, progress=progress, resolved=resolved, users=users, q=q, status_filter=status_filter)

@app.route("/update/<int:complaint_id>", methods=["POST"])
@roles_required("admin", "staff")
def update(complaint_id):
    status = request.form.get("status", "Pending")
    if status not in ALLOWED_STATUSES: status = "Pending"
    staff_notes = request.form.get("staff_notes", "").strip()[:2000]
    con = connect_db(); row = con.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone(); con.close()
    if not row: abort(404)
    resolution_filename = row["resolution_photo_filename"]
    uploaded = request.files.get("resolution_photo")
    if uploaded and uploaded.filename:
        try:
            raw = uploaded.read()
            if len(raw) > 4 * 1024 * 1024: raise ValueError("Resolution photo must be smaller than 4 MB.")
            resolution_filename = save_image_bytes(raw, RESOLUTION_UPLOADS)
        except ValueError as exc: flash(str(exc), "danger"); return redirect(url_for("admin"))
    if status == "Resolved" and not resolution_filename:
        flash("Resolved mark karne ke liye repair ke baad ki photo upload karein.", "danger"); return redirect(url_for("admin"))
    con = connect_db(); con.execute("UPDATE complaints SET status=?, staff_notes=?, resolution_photo_filename=?, updated_at=? WHERE id=?", (status,staff_notes,resolution_filename,now(),complaint_id)); con.commit(); con.close()
    if row["user_id"]:
        con=connect_db(); student=con.execute("SELECT email FROM users WHERE id=?",(row["user_id"],)).fetchone(); con.close()
        if student: send_email(student["email"], f"CampusFix complaint #{complaint_id} updated", f"Your complaint status is now: {status}.\nStaff notes: {staff_notes or 'No notes provided.'}")
    flash(f"Complaint #{complaint_id} updated.", "success"); return redirect(url_for("admin"))

@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@roles_required("admin")
def update_role(user_id):
    role = request.form.get("role", "student")
    if role not in ("student", "staff", "admin"): abort(400)
    if user_id == session.get("user_id") and role != "admin":
        flash("You cannot remove your own admin role here.", "danger"); return redirect(url_for("admin"))
    con=connect_db(); con.execute("UPDATE users SET role=? WHERE id=?",(role,user_id)); con.commit(); con.close()
    flash("User role updated.", "success"); return redirect(url_for("admin"))

@app.route("/seed", methods=["POST"])
@roles_required("admin")
def seed_demo_data():
    samples = [
        ("Block B", "WiFi is not working in Block B for two days."),
        ("Block B", "Block B wifi not working since yesterday."),
        ("Room 203", "Projector is not working in room 203."),
        ("Washroom 2", "There is water leakage near the washroom tap."),
        ("Main Gate", "Emergency exit is locked and this is a safety issue."),
    ]
    con = connect_db()
    for loc, desc in samples:
        category, priority, department, method, confidence = classify(desc)
        con.execute("INSERT INTO complaints(user_id,name,location,description,photo_filename,category,priority,department,status,created_at,updated_at,classifier_method,confidence) VALUES(NULL,'Demo Student',?,?, '',?,?,?,?,?,?,?,?)",
                    (loc, desc, category, priority, department, "Pending", now(), now(), method, confidence))
    con.commit(); con.close()
    flash("Demo complaints added. These sample records have no photo/GPS data.", "success")
    return redirect(url_for("admin"))

@app.route("/api/stats")
@roles_required("admin", "staff")
def stats():
    con=connect_db(); total=con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    counts={s:con.execute("SELECT COUNT(*) FROM complaints WHERE status=?",(s,)).fetchone()[0] for s in ALLOWED_STATUSES}
    priorities={p:con.execute("SELECT COUNT(*) FROM complaints WHERE priority=?",(p,)).fetchone()[0] for p in ("High","Medium","Low")}
    categories=con.execute("SELECT category,COUNT(*) c FROM complaints GROUP BY category ORDER BY c DESC").fetchall()
    locations=con.execute("SELECT location,COUNT(*) c FROM complaints GROUP BY location ORDER BY c DESC LIMIT 10").fetchall(); con.close()
    return {"total":total,"statuses":counts,"priorities":priorities,"categories":[{"name":r[0],"count":r[1]} for r in categories],"locations":[{"name":r[0],"count":r[1]} for r in locations]}

@app.route("/reports.csv")
@roles_required("admin", "staff")
def reports_csv():
    con=connect_db(); rows=con.execute("SELECT id,name,location,latitude,longitude,description,category,priority,department,status,created_at,updated_at,staff_notes,classifier_method,confidence FROM complaints ORDER BY id DESC").fetchall(); con.close()
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(rows[0].keys() if rows else ["id","name","location","latitude","longitude","description","category","priority","department","status","created_at","updated_at","staff_notes","classifier_method","confidence"])
    for row in rows: writer.writerow([row[k] for k in row.keys()])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=campusfix_report.csv"})

@app.errorhandler(403)
def forbidden(_): return render_template("error.html", code=403, message="You do not have permission to view this page."), 403
@app.errorhandler(404)
def not_found(_): return render_template("error.html", code=404, message="The requested page or complaint was not found."), 404
@app.errorhandler(413)
def too_large(_): return render_template("error.html", code=413, message="Upload too large. Keep each image under 4 MB."), 413

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)

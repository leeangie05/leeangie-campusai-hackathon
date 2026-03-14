"""
Syllabot — Integrated Flask Backend
Handles: auth, Canvas sync+caching, material matching, AI estimation,
         scheduling, timer sessions, and file storage.

Install:
    pip install flask flask-cors google-genai pypdf2 requests

Run:
    export GEMINI_API_KEY=your_key
    python server.py
"""

import os, json, time, re, io, hashlib, tempfile, shutil
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import PyPDF2
import requests as req

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "syllabot-dev-secret-2024")
CORS(app, supports_credentials=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_DIR        = Path("data")
CANVAS_CACHE    = Path("canvas_cache")
for d in [DATA_DIR, CANVAS_CACHE]:
    d.mkdir(exist_ok=True)

USERS_FILE    = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
for f in [USERS_FILE, SESSIONS_FILE]:
    if not f.exists():
        f.write_text("[]")

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}
MIME_MAP = {
    ".pdf":  "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".txt":  "text/plain",
    ".md":   "text/plain",
}

# ── Data helpers ──────────────────────────────────────────────────────────────
def load_json(path): 
    try: return json.loads(path.read_text())
    except: return []

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def load_users(): return load_json(USERS_FILE)
def save_users(u): save_json(USERS_FILE, u)
def load_sessions(): return load_json(SESSIONS_FILE)
def save_sessions(s): save_json(SESSIONS_FILE, s)

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def get_user(email):
    return next((u for u in load_users() if u["email"] == email), None)

def current_user():
    uid = session.get("user_id")
    if not uid: return None
    return next((u for u in load_users() if u["id"] == uid), None)

def require_auth():
    u = current_user()
    if not u: return jsonify({"error": "Not authenticated"}), 401
    return None

# ── PDF helpers ───────────────────────────────────────────────────────────────
def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[Could not extract PDF: {e}]"

def extract_pdf_text_from_path(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return extract_pdf_text(f.read())
    except Exception as e:
        return f"[Could not read {path}: {e}]"

# ── Gemini helper ─────────────────────────────────────────────────────────────
def gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
    return resp.text.strip()

def gemini_parse_json(prompt: str) -> any:
    raw = gemini(prompt)
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    return json.loads(raw.strip())

# ── Priority: based purely on due date and AI-estimated hours ────────────────
def calculate_priority(assignment: dict) -> float:
    """Priority score based only on urgency and AI-estimated workload."""
    days = assignment.get("due_in_days", 7) or 7
    hrs  = assignment.get("estimated_hours") or 0
    priority = 0
    if days <= 1:   priority += 10
    elif days <= 3: priority += 7
    elif days <= 7: priority += 5
    else:           priority += 2
    if hrs >= 8:    priority += 4
    elif hrs >= 5:  priority += 3
    elif hrs >= 2:  priority += 2
    elif hrs > 0:   priority += 1
    return priority

# ── Canvas helpers ────────────────────────────────────────────────────────────
def canvas_get(domain, token, path, params={}):
    results = []
    url = f"https://{domain.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        resp = req.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = resp.links.get("next", {}).get("url")
        params = {}
    return results

def canvas_download_file(canvas_file, token):
    """Download a Canvas file and return bytes."""
    url = canvas_file.get("url", "")
    if not url: return None
    headers = {"Authorization": f"Bearer {token}"}
    resp = req.get(url, headers=headers, allow_redirects=False, timeout=15)
    real_url = resp.headers.get("Location", url) if resp.status_code in (301,302,303,307,308) else url
    resp = req.get(real_url, stream=True, timeout=60)
    if resp.status_code == 403:
        resp = req.get(real_url, headers=headers, stream=True, timeout=60)
    if "text/html" in resp.headers.get("Content-Type",""):
        return None
    return resp.content

def get_canvas_cache_dir(user_id, course_id):
    d = CANVAS_CACHE / str(user_id) / str(course_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

def canvas_cache_manifest(user_id, course_id):
    p = get_canvas_cache_dir(user_id, course_id) / "manifest.json"
    if p.exists(): return json.loads(p.read_text())
    return {}

def save_canvas_cache_manifest(user_id, course_id, manifest):
    p = get_canvas_cache_dir(user_id, course_id) / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2))

# ── Material matcher ──────────────────────────────────────────────────────────
def match_assignment_to_notes(assignment_text: str, assignment_name: str,
                               notes: list[dict]) -> list[dict]:
    """
    notes: list of {"filename": str, "text": str}
    Returns list of {"filename", "relevance", "reason"} sorted by relevance.
    """
    if not notes:
        return []

    file_list = "\n".join(f"{i+1}. {n['filename']}" for i, n in enumerate(notes))
    notes_content = "\n\n".join(
        f"=== {n['filename']} ===\n{n['text'][:2000]}" for n in notes
    )

    prompt = f"""You are a study assistant. Match an assignment to relevant notes/lectures.

Assignment: {assignment_name}
Assignment content:
{assignment_text[:3000]}

Available notes files:
{file_list}

Notes content:
{notes_content}

Instructions:
- Identify which notes files are genuinely relevant to this assignment.
- Base your answer on actual content, not just filenames.
- Return ONLY valid JSON, no markdown:
[
  {{
    "filename": "exact filename from list",
    "relevance": "high" | "medium" | "low",
    "reason": "one sentence explaining why this file is relevant"
  }}
]
Only include relevant files. Order by relevance descending. Return [] if nothing is relevant."""

    try:
        return gemini_parse_json(prompt)
    except Exception as e:
        return [{"error": str(e)}]

# ── AI time estimator ─────────────────────────────────────────────────────────
def ai_estimate(assignment_text: str, assignment_name: str,
                course: str, notes_text: str, history_summary: str) -> dict:
    prompt = f"""You are an academic workload estimator for University of Michigan students.
Estimate how many minutes a prepared student needs to complete this assignment.

Key assumptions:
- The student has already attended lectures and reviewed notes — do NOT add study time.
- Only estimate time to actually DO the assignment (reading the prompt, solving problems, writing, coding, etc.).
- Be concise and realistic. Most homework assignments take 30–180 minutes. Only exceed 3 hours for large projects or exams.

Course: {course or "Unknown"}
Historical timing data: {history_summary}

Assignment: {assignment_name}
{assignment_text[:2000]}

Relevant notes summary (for context only — student already knows this material):
{notes_text[:1000] if notes_text else "None provided."}

Return ONLY valid JSON, no markdown:
{{
  "estimated_minutes": <integer, time to complete the assignment itself>,
  "low_minutes": <integer, fast student>,
  "high_minutes": <integer, slower student>,
  "primary_concept": "<3-5 word topic label>",
  "reasoning": "<1-2 sentences explaining the estimate>",
  "confidence": "low" | "medium" | "high"
}}"""
    try:
        return gemini_parse_json(prompt)
    except Exception as e:
        return {"error": str(e)}

def history_summary(course: str, sessions: list, user_id: str = "") -> str:
    """
    Build history context from ALL users' sessions (for crowd-sourced estimates)
    plus this specific user's own sessions (for personalization).
    """
    course_upper = course.upper()
    all_course   = [s for s in sessions if s.get("course","").upper() == course_upper and s.get("actual_minutes")]
    user_course  = [s for s in all_course if s.get("user_id") == user_id] if user_id else []
    all_done     = [s for s in sessions if s.get("actual_minutes")]

    lines = []

    # All users' data for this course
    if all_course:
        times = [s["actual_minutes"] for s in all_course]
        avg   = sum(times) // len(times)
        lines.append(f"All students — {len(all_course)} recorded session(s) for {course}: avg {avg} min, range {min(times)}–{max(times)} min.")
        for s in all_course[-5:]:
            lines.append(f"  - {s.get('assignment_summary','?')}: {s['actual_minutes']} min")
    else:
        lines.append(f"No sessions recorded yet for {course} by any student.")

    # This user's personal history
    if user_course:
        utimes = [s["actual_minutes"] for s in user_course]
        uavg   = sum(utimes) // len(utimes)
        lines.append(f"This student specifically — {len(user_course)} session(s) for {course}: avg {uavg} min.")

    # Cross-course context
    if all_done:
        avg_all = sum(s["actual_minutes"] for s in all_done) // len(all_done)
        lines.append(f"Overall across all courses ({len(all_done)} sessions): avg {avg_all} min.")

    return "\n".join(lines)


def run_estimate_for_assignment(user_id: str, assignment: dict) -> dict:
    """
    Run AI estimate + material matching for a single assignment.
    Uses cached canvas files for the course if available.
    Returns estimate fields to merge into the assignment dict.
    """
    course      = assignment.get("course", "")
    title       = assignment.get("title", "")
    description = assignment.get("description", "")
    course_id   = assignment.get("course_id", "")

    assignment_text = f"Assignment: {title}\n\n{description}"

    # Load cached notes for this course
    notes = []
    if course_id:
        cache_dir = get_canvas_cache_dir(user_id, course_id)
        manifest  = canvas_cache_manifest(user_id, course_id)
        for fid, meta in manifest.items():
            fpath = cache_dir / meta["filename"]
            if fpath.exists() and os.path.splitext(meta["filename"])[1].lower() in ALLOWED_EXTENSIONS:
                notes.append({
                    "filename": meta["filename"],
                    "text":     extract_pdf_text_from_path(str(fpath))
                })

    sessions = load_sessions()
    hist     = history_summary(course, sessions, user_id)

    try:
        matched  = match_assignment_to_notes(assignment_text, title, notes)
        relevant = "\n\n".join(
            f"=== {n['filename']} ===\n{n['text'][:1500]}"
            for n in notes
            if any(m.get("filename") == n["filename"] and
                   m.get("relevance") in ("high","medium") for m in matched)
        )
        result = ai_estimate(assignment_text, title, course, relevant, hist)
        result["matched_notes"] = matched
        return result
    except Exception as e:
        print(f"  Auto-estimate failed for '{title}': {e}")
        return {}

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return app.send_static_file("index.html")

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    d = request.get_json()
    email, pw = d.get("email","").strip(), d.get("password","")
    if not email or not pw:
        return jsonify({"error": "Email and password required"}), 400
    users = load_users()
    if any(u["email"] == email for u in users):
        return jsonify({"error": "Email already registered"}), 409
    user = {
        "id": hashlib.md5(email.encode()).hexdigest(),
        "email": email,
        "password": hash_pw(pw),
        "name": d.get("name", email.split("@")[0]),
        "created_at": datetime.utcnow().isoformat(),
        "courses": [],
        "assignments": [],
        "canvas": {},
        "onboarded": False,
    }
    users.append(user)
    save_users(users)
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "user": {k:v for k,v in user.items() if k!="password"}})

@app.route("/api/auth/signin", methods=["POST"])
def signin():
    d = request.get_json()
    email, pw = d.get("email","").strip(), d.get("password","")
    user = get_user(email)
    if not user or user["password"] != hash_pw(pw):
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "user": {k:v for k,v in user.items() if k!="password"},
                    "onboarded": user.get("onboarded", False)})

@app.route("/api/auth/signout", methods=["POST"])
def signout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/me")
def me():
    u = current_user()
    if not u: return jsonify({"user": None})
    return jsonify({"user": {k:v for k,v in u.items() if k!="password"}})

# ── Onboarding: save courses + assignments ────────────────────────────────────
@app.route("/api/onboarding", methods=["POST"])
def onboarding():
    err = require_auth()
    if err: return err
    u = current_user()
    d = request.get_json()

    new_assignments = d.get("assignments", [])

    # Run AI estimate for each assignment in the background
    print(f"Auto-estimating {len(new_assignments)} assignment(s)...")
    for a in new_assignments:
        est = run_estimate_for_assignment(u["id"], a)
        if est:
            a["estimated_minutes"] = est.get("estimated_minutes")
            a["estimated_hours"]   = round(est.get("estimated_minutes", 180) / 60, 2)
            a["primary_concept"]   = est.get("primary_concept", "")
            a["matched_notes"]     = est.get("matched_notes", [])
            a["ai_reasoning"]      = est.get("reasoning", "")
            print(f"  ✓ {a['title']}: {est.get('estimated_minutes')} min")

    users = load_users()
    for user in users:
        if user["id"] == u["id"]:
            user["courses"]     = d.get("courses", [])
            user["assignments"] = new_assignments
            user["onboarded"]   = True
            break
    save_users(users)
    return jsonify({"ok": True})

# ── Get user's assignments + study plan ───────────────────────────────────────
@app.route("/api/assignments")
def get_assignments():
    err = require_auth()
    if err: return err
    u = current_user()
    assignments = u.get("assignments", [])

    out = []
    for a in assignments:
        due_date = a.get("due_date", "")
        try:
            due_dt   = datetime.fromisoformat(due_date.replace("Z",""))
            due_days = max((due_dt - datetime.utcnow()).days, 0)
        except:
            due_days = 7

        est_mins = a.get("estimated_minutes")  # set by AI, or None
        est_hrs  = round(est_mins / 60, 2) if est_mins else None

        entry = {
            "id":              a.get("id", ""),
            "course":          a.get("course", ""),
            "title":           a.get("title", ""),
            "description":     a.get("description", ""),
            "due_date":        due_date,
            "due_in_days":     due_days,
            "source":          a.get("source", "manual"),
            "canvas_url":      a.get("canvas_url", ""),
            "course_id":       a.get("course_id", ""),
            "points":          a.get("points", 100),
            # AI estimate fields — None if not yet computed
            "estimated_minutes": est_mins,
            "estimated_hours":   est_hrs,
            "primary_concept":   a.get("primary_concept"),
            "matched_notes":     a.get("matched_notes", []),
            "ai_reasoning":      a.get("ai_reasoning"),
            "estimate_pending":  est_mins is None,
            "assignment_pdf":    a.get("assignment_pdf"),
        }
        entry["priority"] = calculate_priority(entry)
        out.append(entry)

    out.sort(key=lambda x: x["priority"], reverse=True)
    return jsonify({"assignments": out})

# ── Canvas: sync (server proxies all Canvas API calls) ───────────────────────
@app.route("/api/canvas/sync", methods=["POST"])
def canvas_sync():
    err = require_auth()
    if err: return err
    u = current_user()
    d = request.get_json()

    domain = d.get("domain","").strip().replace("https://","").replace("http://","").rstrip("/")
    token  = d.get("token","").strip()
    if not domain or not token:
        return jsonify({"error": "Canvas domain and token required"}), 400

    base    = f"https://{domain}"
    headers = {"Authorization": f"Bearer {token}"}

    # ── Step 1: fetch courses ─────────────────────────────────────────────────
    raw_courses = []
    debug_errors = []
    for params in [
        {"per_page": 50, "enrollment_type": "student"},
        {"per_page": 50, "enrollment_state": "active"},
        {"per_page": 50},
    ]:
        try:
            raw_courses = canvas_get(domain, token, "/api/v1/courses", params)
            if raw_courses:
                print(f"Canvas: got {len(raw_courses)} courses")
                break
            debug_errors.append(f"{params}: 0 courses returned")
        except Exception as e:
            debug_errors.append(f"{params}: {e}")

    if not raw_courses:
        # Try a raw test to give a clearer error
        try:
            test = req.get(f"{base}/api/v1/users/self", headers=headers, timeout=10)
            if test.status_code == 401:
                return jsonify({"error": "Invalid token — Canvas returned 401 Unauthorized. Check your access token."}), 400
            elif test.status_code == 200:
                return jsonify({"error": f"Token is valid but no courses found. You may not be enrolled in any active courses. Debug: {' | '.join(debug_errors)}"}), 400
            else:
                return jsonify({"error": f"Canvas returned {test.status_code}: {test.text[:200]}"}), 400
        except Exception as e:
            return jsonify({"error": f"Could not reach Canvas at {base}: {e}"}), 400

    # ── Step 2: for each course, fetch assignments + files ────────────────────
    courses_out    = []
    all_assignments = []
    total_files    = 0

    for course in raw_courses:
        if not course.get("name") or course.get("workflow_state") == "deleted":
            continue
        cid   = course["id"]
        cname = course["name"]
        ccode = course.get("course_code", "")

        # Assignments
        try:
            canvas_assignments = canvas_get(domain, token,
                f"/api/v1/courses/{cid}/assignments",
                {"per_page": 50, "order_by": "due_at"})
        except Exception as e:
            print(f"  Could not fetch assignments for {cname}: {e}")
            canvas_assignments = []

        for a in canvas_assignments:
            desc = re.sub(r"<[^>]+>", " ", a.get("description") or "").strip()

            # Download any PDFs attached directly to this assignment
            assignment_pdf_filename = None
            attachments = a.get("attachments") or []
            for att in attachments:
                fname = att.get("filename") or att.get("display_name", "")
                ext   = os.path.splitext(fname)[1].lower()
                if ext in ALLOWED_EXTENSIONS:
                    cache_dir_a = get_canvas_cache_dir(u["id"], cid)
                    dest = cache_dir_a / fname
                    if not dest.exists():
                        print(f"  Downloading assignment attachment: {fname}")
                        file_bytes = canvas_download_file(att, token)
                        if file_bytes:
                            dest.write_bytes(file_bytes)
                            manifest_a = canvas_cache_manifest(u["id"], cid)
                            manifest_a[str(att.get("id","att_"+fname))] = {
                                "filename":     fname,
                                "cached_at":    datetime.utcnow().isoformat(),
                                "size":         len(file_bytes),
                                "content_type": MIME_MAP.get(ext, "application/octet-stream"),
                            }
                            save_canvas_cache_manifest(u["id"], cid, manifest_a)
                            total_files += 1
                    if dest.exists():
                        assignment_pdf_filename = fname
                    break  # only use first attachment

            all_assignments.append({
                "id":                     f"canvas_{a['id']}",
                "title":                  a.get("name", "Unnamed"),
                "course":                 cname,
                "course_id":              cid,
                "description":            desc,
                "due_date":               a.get("due_at", ""),
                "points":                 a.get("points_possible", 100) or 100,
                "type":                   "homework",
                "difficulty":             3,
                "source":                 "canvas",
                "canvas_url":             a.get("html_url", ""),
                "assignment_pdf":         assignment_pdf_filename,
            })

        # Files — download and cache
        cache_dir = get_canvas_cache_dir(u["id"], cid)
        manifest  = canvas_cache_manifest(u["id"], cid)
        try:
            files = canvas_get(domain, token, f"/api/v1/courses/{cid}/files", {"per_page": 100})
        except Exception as e:
            print(f"  Could not fetch files for {cname}: {e}")
            files = []

        cached_files = []
        for cf in files:
            fname = cf.get("filename") or cf.get("display_name", "unknown")
            ext   = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            file_id = str(cf.get("id", ""))
            dest    = cache_dir / fname
            # Use cache if already downloaded
            if file_id in manifest and dest.exists():
                cached_files.append(fname)
                continue
            print(f"  Downloading {fname}...")
            file_bytes = canvas_download_file(cf, token)
            if file_bytes:
                dest.write_bytes(file_bytes)
                manifest[file_id] = {
                    "filename":     fname,
                    "cached_at":    datetime.utcnow().isoformat(),
                    "size":         len(file_bytes),
                    "content_type": MIME_MAP.get(ext, "application/octet-stream"),
                }
                cached_files.append(fname)
                total_files += 1

        save_canvas_cache_manifest(u["id"], cid, manifest)
        courses_out.append({
            "course_name": cname,
            "course_code": ccode,
            "canvas_id":   cid,
            "files":       cached_files,
        })

    # ── Step 3: run AI estimates for new assignments ─────────────────────────
    print(f"Auto-estimating {len(all_assignments)} Canvas assignment(s)...")
    for a in all_assignments:
        est = run_estimate_for_assignment(u["id"], a)
        if est:
            a["estimated_minutes"] = est.get("estimated_minutes")
            a["estimated_hours"]   = round(est.get("estimated_minutes", 180) / 60, 2)
            a["primary_concept"]   = est.get("primary_concept", "")
            a["matched_notes"]     = est.get("matched_notes", [])
            a["ai_reasoning"]      = est.get("reasoning", "")
            print(f"  ✓ {a['title']}: {est.get('estimated_minutes')} min")

    # ── Step 4: save to user profile ─────────────────────────────────────────
    users = load_users()
    for user in users:
        if user["id"] == u["id"]:
            user["canvas"]  = {"domain": domain, "synced_at": datetime.utcnow().isoformat()}
            user["courses"] = [{k:v for k,v in c.items() if k != "files"} for c in courses_out]
            # Replace all canvas assignments with fresh data, keep manual ones
            manual = [a for a in user.get("assignments", []) if a.get("source") != "canvas"]
            user["assignments"] = manual + all_assignments
            user["onboarded"] = True
            break
    save_users(users)

    return jsonify({
        "ok":                   True,
        "courses":              len(courses_out),
        "assignments_imported": len(all_assignments),
        "files_cached":         total_files,
    })



# ── Clear all cached Canvas files for this user ──────────────────────────────
@app.route("/api/canvas/cache/clear", methods=["POST"])
def clear_canvas_cache():
    err = require_auth()
    if err: return err
    u = current_user()
    user_cache = CANVAS_CACHE / u["id"]
    deleted_files = 0
    if user_cache.exists():
        for f in user_cache.rglob("*"):
            if f.is_file():
                f.unlink()
                deleted_files += 1
        # Remove empty dirs
        for d in sorted(user_cache.rglob("*"), reverse=True):
            if d.is_dir():
                try: d.rmdir()
                except: pass
    # Also clear canvas assignments from user profile
    users = load_users()
    for user in users:
        if user["id"] == u["id"]:
            user["assignments"] = [a for a in user.get("assignments", []) if a.get("source") != "canvas"]
            user["courses"] = []
            user["canvas"] = {}
            break
    save_users(users)
    return jsonify({"ok": True, "deleted_files": deleted_files})

# ── Get cached files for a course ────────────────────────────────────────────
@app.route("/api/canvas/files/<int:course_id>")
def canvas_files(course_id):
    err = require_auth()
    if err: return err
    u = current_user()
    cache_dir = get_canvas_cache_dir(u["id"], course_id)
    manifest  = canvas_cache_manifest(u["id"], course_id)
    files = [{"filename": v["filename"], "id": k} for k, v in manifest.items()]
    return jsonify({"files": files})

# ── Estimate: multi-assignment with material matching ─────────────────────────
@app.route("/api/estimate", methods=["POST"])
def estimate():
    err = require_auth()
    if err: return err
    u = current_user()

    course        = request.form.get("course","").strip()
    canvas_cid    = request.form.get("canvas_course_id","").strip()
    assignment_files = request.files.getlist("assignments")
    notes_files      = request.files.getlist("notes")

    if not assignment_files:
        return jsonify({"error": "At least one assignment PDF is required"}), 400

    # Build notes list from uploaded files
    notes = []
    for nf in notes_files:
        text = extract_pdf_text(nf.read())
        notes.append({"filename": nf.filename, "text": text})

    # Also load cached canvas files if a canvas_course_id was provided
    if canvas_cid:
        cache_dir = get_canvas_cache_dir(u["id"], canvas_cid)
        manifest  = canvas_cache_manifest(u["id"], canvas_cid)
        for fid, meta in manifest.items():
            fpath = cache_dir / meta["filename"]
            if fpath.exists() and os.path.splitext(meta["filename"])[1].lower() in ALLOWED_EXTENSIONS:
                notes.append({"filename": meta["filename"], "text": extract_pdf_text_from_path(str(fpath))})

    sessions  = load_sessions()
    hist_sum  = history_summary(course, sessions, u["id"])
    results   = []

    for af in assignment_files:
        aname = af.filename
        abytes = af.read()
        atext  = extract_pdf_text(abytes)

        # Material matching
        matched_notes = match_assignment_to_notes(atext, aname, notes)

        # AI time estimate — use only the matched high/medium notes
        relevant_notes_text = "\n\n".join(
            f"=== {n['filename']} ===\n{n['text'][:1500]}"
            for n in notes
            if any(m.get("filename") == n["filename"] and
                   m.get("relevance") in ("high","medium") for m in matched_notes)
        )

        estimate_result = ai_estimate(atext, aname, course, relevant_notes_text, hist_sum)
        estimate_result["assignment"] = aname
        estimate_result["matched_notes"] = matched_notes
        results.append(estimate_result)

    # Save estimates back to matching assignments in users.json
    if results:
        users = load_users()
        for user in users:
            if user["id"] == u["id"]:
                for r in results:
                    if r.get("error"): continue
                    for a in user.get("assignments", []):
                        # Match by filename (strip extension) or exact title
                        aname_base = os.path.splitext(r["assignment"])[0].lower().replace("_"," ").replace("-"," ")
                        atitle     = a.get("title","").lower().strip()
                        if aname_base in atitle or atitle in aname_base or a.get("id","") == r.get("assignment_id",""):
                            a["estimated_minutes"] = r.get("estimated_minutes")
                            a["estimated_hours"]   = round((r.get("estimated_minutes") or 180) / 60, 2)
                            a["primary_concept"]   = r.get("primary_concept", "")
                            a["matched_notes"]     = r.get("matched_notes", [])
                            a["ai_reasoning"]      = r.get("reasoning", "")
                break
        save_users(users)

    return jsonify({"results": results})


# ── Estimate using cached Canvas files (no upload needed) ────────────────────
@app.route("/api/estimate/canvas", methods=["POST"])
def estimate_canvas():
    err = require_auth()
    if err: return err
    u = current_user()

    course      = request.form.get("course", "").strip()
    canvas_cid  = request.form.get("canvas_course_id", "").strip()
    asgn_title  = request.form.get("canvas_assignment_title", "").strip()
    asgn_desc   = request.form.get("canvas_assignment_desc", "").strip()

    if not canvas_cid:
        return jsonify({"error": "canvas_course_id required"}), 400

    # Load all cached notes for this course
    cache_dir = get_canvas_cache_dir(u["id"], canvas_cid)
    manifest  = canvas_cache_manifest(u["id"], canvas_cid)

    notes = []
    assignment_text = f"Assignment: {asgn_title}\n\n{asgn_desc}"

    for fid, meta in manifest.items():
        fpath = cache_dir / meta["filename"]
        if not fpath.exists():
            continue
        ext = os.path.splitext(meta["filename"])[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        text = extract_pdf_text_from_path(str(fpath))
        notes.append({"filename": meta["filename"], "text": text})

    if not notes:
        return jsonify({"error": f"No cached files found for this course. Try syncing Canvas again."}), 400

    sessions = load_sessions()
    hist_sum = history_summary(course, sessions)

    # Match notes to assignment
    matched_notes = match_assignment_to_notes(assignment_text, asgn_title, notes)

    # Build notes text from high/medium matches
    relevant_notes_text = "\n\n".join(
        f"=== {n['filename']} ===\n{n['text'][:1500]}"
        for n in notes
        if any(m.get("filename") == n["filename"] and
               m.get("relevance") in ("high", "medium") for m in matched_notes)
    )

    estimate_result = ai_estimate(assignment_text, asgn_title, course, relevant_notes_text, hist_sum)
    estimate_result["assignment"]    = asgn_title
    estimate_result["matched_notes"] = matched_notes

    # Save back to assignment in users.json
    asgn_id = request.form.get("canvas_assignment_id", "")
    users = load_users()
    for user in users:
        if user["id"] == u["id"]:
            for a in user.get("assignments", []):
                if a.get("id") == asgn_id or a.get("title","").lower() == asgn_title.lower():
                    a["estimated_minutes"] = estimate_result.get("estimated_minutes")
                    a["estimated_hours"]   = round((estimate_result.get("estimated_minutes") or 180) / 60, 2)
                    a["primary_concept"]   = estimate_result.get("primary_concept", "")
                    a["matched_notes"]     = estimate_result.get("matched_notes", [])
                    a["ai_reasoning"]      = estimate_result.get("reasoning", "")
            break
    save_users(users)

    return jsonify({"results": [estimate_result]})

# ── Save completed timer session ──────────────────────────────────────────────


# ── Update assignment estimate ────────────────────────────────────────────────
@app.route("/api/assignments/<assignment_id>/estimate", methods=["PATCH"])
def patch_assignment_estimate(assignment_id):
    err = require_auth()
    if err: return err
    u = current_user()
    d = request.get_json()
    users = load_users()
    updated = False
    for user in users:
        if user["id"] == u["id"]:
            for a in user.get("assignments", []):
                if a.get("id") == assignment_id:
                    a["estimated_minutes"] = d.get("estimated_minutes", a.get("estimated_minutes"))
                    a["estimated_hours"]   = round((d.get("estimated_minutes") or 180) / 60, 2)
                    a["primary_concept"]   = d.get("primary_concept", a.get("primary_concept",""))
                    a["matched_notes"]     = d.get("matched_notes", a.get("matched_notes",[]))
                    a["ai_reasoning"]      = d.get("reasoning", a.get("ai_reasoning",""))
                    updated = True
            break
    save_users(users)
    return jsonify({"ok": updated})

# ── Delete an assignment ──────────────────────────────────────────────────────
@app.route("/api/assignments/<assignment_id>", methods=["DELETE"])
def delete_assignment(assignment_id):
    err = require_auth()
    if err: return err
    u = current_user()
    users = load_users()
    for user in users:
        if user["id"] == u["id"]:
            before = len(user.get("assignments", []))
            user["assignments"] = [a for a in user.get("assignments", []) if a.get("id") != assignment_id]
            after = len(user["assignments"])
            break
    save_users(users)
    return jsonify({"ok": True, "removed": before - after})

@app.route("/api/sessions", methods=["POST"])
def save_session():
    err = require_auth()
    if err: return err
    u = current_user()
    d = request.get_json()
    sessions = load_sessions()
    sessions.append({
        "id":                str(int(time.time()*1000)),
        "user_id":           u["id"],
        "email":             u["email"],
        "course":            d.get("course",""),
        "assignment_summary":d.get("assignment_summary",""),
        "primary_concept":   d.get("primary_concept",""),
        "estimated_minutes": d.get("estimated_minutes"),
        "actual_minutes":    d.get("actual_minutes"),
        "timestamp":         datetime.utcnow().isoformat(),
    })
    save_sessions(sessions)
    return jsonify({"ok": True})

@app.route("/api/sessions")
def get_sessions_route():
    err = require_auth()
    if err: return err
    u = current_user()
    sessions = [s for s in load_sessions() if s.get("user_id") == u["id"]]
    return jsonify(sessions[-50:])

# ── Serve cached canvas files directly (for PDF viewer) ──────────────────────
@app.route("/api/canvas/file/<user_id>/<course_id>/<path:filename>")
def serve_canvas_file(user_id, course_id, filename):
    u = current_user()
    if not u or u["id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 401
    cache_dir = get_canvas_cache_dir(user_id, course_id)
    ext = os.path.splitext(filename)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
    from flask import send_file
    fpath = Path(cache_dir) / filename
    if not fpath.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(fpath), mimetype=mime, as_attachment=False)

@app.route("/api/uploaded/file", methods=["POST"])
def serve_uploaded_file():
    """Temporarily store an uploaded file and return a view URL."""
    err = require_auth()
    if err: return err
    f = request.files.get("file")
    if not f: return jsonify({"error": "No file"}), 400
    u = current_user()
    upload_dir = DATA_DIR / "uploads" / u["id"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", f.filename)
    dest = upload_dir / safe_name
    f.save(str(dest))
    return jsonify({"url": f"/api/uploaded/view/{u['id']}/{safe_name}"})

@app.route("/api/uploaded/view/<user_id>/<path:filename>")
def view_uploaded_file(user_id, filename):
    u = current_user()
    if not u or u["id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 401
    upload_dir = DATA_DIR / "uploads" / user_id
    ext = os.path.splitext(filename)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
    from flask import send_file
    fpath = upload_dir / filename
    if not fpath.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(fpath), mimetype=mime, as_attachment=False)



# ══════════════════════════════════════════════════════════════════
# SOCIAL
# ══════════════════════════════════════════════════════════════════

@app.route("/api/social/leaderboard")
def social_leaderboard():
    err = require_auth()
    if err: return err
    u = current_user()

    friends_emails = u.get("friends", [])
    all_sessions   = load_sessions()
    all_users      = load_users()

    # Include self + friends
    participants = [u["email"]] + friends_emails
    leaderboard  = []

    for email in participants:
        user_obj  = next((x for x in all_users if x["email"] == email), None)
        user_sess = [s for s in all_sessions if s.get("email") == email and s.get("actual_minutes")]
        streak    = _calc_streak(user_sess)
        week_ago  = datetime.utcnow() - timedelta(days=7)
        sess_week = len([s for s in user_sess if s.get("timestamp") and
                         datetime.fromisoformat(s["timestamp"]) >= week_ago])
        total_hrs = round(sum(s["actual_minutes"] for s in user_sess) / 60, 1)
        last_sess = user_sess[-1].get("timestamp","") if user_sess else ""

        # Status
        if user_sess and last_sess:
            try:
                last_dt = datetime.fromisoformat(last_sess)
                mins_ago = (datetime.utcnow() - last_dt).total_seconds() / 60
                if mins_ago < 30:   status = "Studying now 🟢"
                elif mins_ago < 120: status = "Just finished"
                else:
                    status = f"Last active {last_dt.strftime('%b %d')}"
            except:
                status = ""
        else:
            status = "No sessions yet"

        leaderboard.append({
            "email":         email,
            "name":          (user_obj or {}).get("name", email.split("@")[0]),
            "streak":        streak,
            "sessions_week": sess_week,
            "total_hours":   total_hrs,
            "status":        status,
            "is_self":       email == u["email"],
        })

    leaderboard.sort(key=lambda x: (-x["streak"], -x["sessions_week"]))
    return jsonify({"friends": leaderboard})


@app.route("/api/social/friends", methods=["POST"])
def add_friend():
    err = require_auth()
    if err: return err
    u    = current_user()
    d    = request.get_json()
    email = d.get("email","").strip().lower()

    if not email:
        return jsonify({"error": "Email required"}), 400
    if email == u["email"]:
        return jsonify({"error": "You can't add yourself"}), 400

    # Check if user exists
    all_users = load_users()
    if not any(x["email"] == email for x in all_users):
        return jsonify({"error": f"No Syllabot account found for {email}"}), 404

    users = load_users()
    already = False
    for user in users:
        if user["id"] == u["id"]:
            friends = user.setdefault("friends", [])
            if email in friends:
                already = True
                break
            friends.append(email)
        # Also add reverse so the other user sees this user
        elif user["email"] == email:
            their_friends = user.setdefault("friends", [])
            if u["email"] not in their_friends:
                their_friends.append(u["email"])
    if already:
        return jsonify({"error": "Already friends"}), 409
    save_users(users)
    return jsonify({"ok": True})


def _calc_streak(sessions: list) -> int:
    if not sessions: return 0
    days = set()
    for s in sessions:
        ts = s.get("timestamp","")
        if ts: days.add(ts[:10])
    streak = 0
    cur    = datetime.utcnow().date()
    while str(cur) in days:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak

# ── Canvas debug endpoint ─────────────────────────────────────────────────────
@app.route("/api/canvas/debug", methods=["POST"])
def canvas_debug():
    d      = request.get_json()
    domain = d.get("domain","").strip().rstrip("/").replace("https://","").replace("http://","")
    token  = d.get("token","").strip()
    if not domain or not token:
        return jsonify({"error": "domain and token required"}), 400
    results = {}
    # Try multiple enrollment params
    for params in [
        {"per_page": 50},
        {"per_page": 50, "enrollment_type": "student"},
        {"per_page": 50, "enrollment_state": "active"},
        {"per_page": 50, "state[]": "available"},
    ]:
        try:
            courses = canvas_get(domain, token, "/api/v1/courses", params)
            key = str(params)
            results[key] = [{"id": c.get("id"), "name": c.get("name"), "workflow": c.get("workflow_state")} for c in courses[:10]]
        except Exception as e:
            results[str(params)] = f"ERROR: {e}"
    return jsonify(results)

if __name__ == "__main__":
    print("="*50)
    print("  Syllabot server starting...")
    print("  Set: export GEMINI_API_KEY=your_key")
    print("  Open: http://localhost:5000")
    print("="*50)
    app.run(debug=True, port=5000)

"""
StudyClock — Flask backend
Handles PDF uploads, Gemini AI estimation, and timing data storage.

Install:  pip install flask flask-cors google-generativeai pypdf2
Run:      python server.py
"""

import os
import json
import time
import base64
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
import PyPDF2
import io

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE = Path("data/sessions.json")
DATA_FILE.parent.mkdir(exist_ok=True)
if not DATA_FILE.exists():
    DATA_FILE.write_text("[]")

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_sessions():
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception:
        return []

def save_sessions(sessions):
    DATA_FILE.write_text(json.dumps(sessions, indent=2))

def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[Could not extract PDF text: {e}]"

def build_history_summary(course: str, sessions: list) -> str:
    """Build a concise summary of past timing data to feed to Gemini."""
    relevant = [s for s in sessions if s.get("course", "").upper() == course.upper() and s.get("actual_minutes")]
    all_completed = [s for s in sessions if s.get("actual_minutes")]

    lines = []

    if relevant:
        times = [s["actual_minutes"] for s in relevant]
        avg = sum(times) / len(times)
        lines.append(f"Past sessions for {course}: {len(relevant)} recorded, average {avg:.0f} min "
                     f"(range {min(times)}–{max(times)} min).")
        # Show last 5
        for s in relevant[-5:]:
            lines.append(f"  - {s.get('assignment_summary','?')}: {s['actual_minutes']} min")
    else:
        lines.append(f"No past sessions recorded for {course} yet.")

    if all_completed:
        avg_all = sum(s["actual_minutes"] for s in all_completed) / len(all_completed)
        lines.append(f"Across all courses ({len(all_completed)} sessions), average time is {avg_all:.0f} min.")

    return "\n".join(lines)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/estimate", methods=["POST"])
def estimate():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not set. Add it to your environment."}), 500

    course     = request.form.get("course", "").strip()
    uniqname   = request.form.get("uniqname", "anonymous").strip()
    assignment_file = request.files.get("assignment")
    notes_files     = request.files.getlist("notes")

    if not assignment_file:
        return jsonify({"error": "Assignment PDF is required."}), 400

    assignment_text = extract_pdf_text(assignment_file.read())

    notes_parts = []
    for i, nf in enumerate(notes_files):
        text = extract_pdf_text(nf.read())
        notes_parts.append(f"--- Notes file {i+1}: {nf.filename} ---\n{text}")
    notes_text = "\n\n".join(notes_parts) if notes_parts else ""

    sessions = load_sessions()
    history  = build_history_summary(course, sessions)

    # Build prompt
    prompt = f"""You are an academic workload estimator for University of Michigan students.

Your job: estimate how many minutes a typical UMich student should spend to complete this assignment well.

## Course
{course if course else "Unknown"}

## Historical timing data from other students
{history}

## Assignment content
{assignment_text[:4000]}

## Student's notes / course materials
{notes_text[:3000] if notes_text else "No notes provided."}

## Instructions
1. Analyze the assignment's scope, complexity, and number of parts.
2. Consider the course subject and how demanding it traditionally is at UMich.
3. Use the historical data above as a strong signal if available; fall back to subject knowledge if not.
4. Give a single realistic time estimate in minutes for a prepared student working steadily.
5. Also give a short 2-3 sentence explanation of your reasoning.
6. Identify the primary concept/topic this assignment covers.

Respond in this exact JSON format (no markdown, no extra text):
{{
  "estimated_minutes": <integer>,
  "low_minutes": <integer, optimistic end>,
  "high_minutes": <integer, pessimistic end>,
  "primary_concept": "<short topic label>",
  "reasoning": "<2-3 sentence explanation>",
  "confidence": "<low|medium|high>"
}}"""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        result["course"] = course
        result["assignment_summary"] = assignment_text[:120].replace("\n", " ").strip()
        return jsonify(result)
    except json.JSONDecodeError:
        return jsonify({"error": "AI returned unexpected format.", "raw": response.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    uniqname = request.args.get("uniqname", "")
    sessions = load_sessions()
    if uniqname:
        sessions = [s for s in sessions if s.get("uniqname") == uniqname]
    # Return most recent 50
    return jsonify(sessions[-50:])


@app.route("/api/sessions", methods=["POST"])
def save_session():
    data = request.get_json()
    required = ["uniqname", "course", "actual_minutes"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    sessions = load_sessions()
    session = {
        "id": str(int(time.time() * 1000)),
        "uniqname":          data["uniqname"],
        "course":            data.get("course", ""),
        "assignment_summary": data.get("assignment_summary", ""),
        "primary_concept":   data.get("primary_concept", ""),
        "estimated_minutes": data.get("estimated_minutes"),
        "actual_minutes":    data["actual_minutes"],
        "timestamp":         datetime.utcnow().isoformat(),
    }
    sessions.append(session)
    save_sessions(sessions)
    return jsonify({"ok": True, "session": session})


if __name__ == "__main__":
    print("=" * 50)
    print("  StudyClock server starting...")
    print("  Set your API key: export GEMINI_API_KEY=your_key")
    print("  Then open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)

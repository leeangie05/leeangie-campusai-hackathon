from google import genai
from google.genai import types
import requests
import json
import os
import re
import time
import tempfile

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Canvas credentials
CANVAS_DOMAIN = "canvas.instructure.com/"   # e.g. umich.instructure.com
CANVAS_TOKEN  = ""   # Canvas > Account > Settings > New Access Token

# Gemini API key (free at https://aistudio.google.com/app/apikey)
GEMINI_API_KEY = ""

# How many upcoming days of assignments to fetch
DAYS_AHEAD = 30

# Only download these file types from Canvas
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
BASE    = f"https://{CANVAS_DOMAIN}"
 
MIME_MAP = {
    ".pdf":  "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".txt":  "text/plain",
    ".md":   "text/plain",
}
 
 
# ── CANVAS HELPERS ────────────────────────────────────────────────────────────
 
def canvas_get(path: str, params: dict = {}) -> list | dict:
    results = []
    url = f"{BASE}{path}"
    while url:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = resp.links.get("next", {}).get("url")
        params = {}
    return results
 
 
def get_active_courses() -> list[dict]:
    seen_ids = set()
    all_courses = []
    for state in ["active", "current", None]:
        try:
            params = {"per_page": 50}
            if state:
                params["enrollment_state"] = state
            courses = canvas_get("/api/v1/courses", params)
            for c in courses:
                if c.get("id") and c["id"] not in seen_ids and c.get("name"):
                    seen_ids.add(c["id"])
                    all_courses.append(c)
        except Exception:
            continue
    return all_courses
 
 
def get_upcoming_assignments(course_id: int) -> list[dict]:
    try:
        assignments = canvas_get(
            f"/api/v1/courses/{course_id}/assignments",
            {"bucket": "upcoming", "per_page": 50, "order_by": "due_at"}
        )
        if assignments:
            return [a for a in assignments if a.get("due_at")]
    except Exception:
        pass
    try:
        assignments = canvas_get(
            f"/api/v1/courses/{course_id}/assignments",
            {"per_page": 50, "order_by": "due_at"}
        )
        return [a for a in assignments if a.get("due_at")]
    except Exception:
        return []
 
 
def get_course_files(course_id: int) -> list[dict]:
    try:
        files = canvas_get(f"/api/v1/courses/{course_id}/files", {"per_page": 100})
        return [
            f for f in files
            if os.path.splitext(f.get("filename", ""))[1].lower() in ALLOWED_EXTENSIONS
        ]
    except Exception:
        return []
 
 
def download_file(canvas_file: dict, dest_path: str) -> bool:
    """
    Canvas file URLs redirect to a signed S3 URL.
    Step 1: follow the redirect to get the real URL.
    Step 2: download from the real URL.
    """
    try:
        url = canvas_file.get("url")
        if not url:
            print(f"      ⚠️  No URL in file metadata")
            return False
 
        # Follow Canvas redirect to get the real S3 signed URL
        resp = requests.get(url, headers=HEADERS, allow_redirects=False, timeout=15)
        if resp.status_code in (301, 302, 303, 307, 308):
            real_url = resp.headers.get("Location", "")
        else:
            real_url = url
 
        # Download from the real URL (S3 signed URLs don't need auth headers)
        resp = requests.get(real_url, stream=True, timeout=60)
 
        # If 403, retry with auth
        if resp.status_code == 403:
            resp = requests.get(real_url, headers=HEADERS, stream=True, timeout=60)
 
        resp.raise_for_status()
 
        # Reject HTML error pages
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            print(f"      ⚠️  Got HTML instead of file content")
            return False
 
        # Write bytes to disk
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
 
        # Verify the file is not empty and looks like a real file (not an error page)
        size = os.path.getsize(dest_path)
        if size == 0:
            print(f"      ⚠️  File is empty after download")
            return False
 
        # Quick sanity check: PDFs should start with %PDF
        ext = os.path.splitext(dest_path)[1].lower()
        if ext == ".pdf":
            with open(dest_path, "rb") as f:
                header = f.read(5)
            if not header.startswith(b"%PDF"):
                print(f"      ⚠️  File doesn't look like a valid PDF (got: {header})")
                return False
 
        return True
 
    except Exception as e:
        print(f"      ⚠️  Download failed: {e}")
        return False
 
 
# ── GEMINI HELPERS ────────────────────────────────────────────────────────────
 
def upload_to_gemini(client, path: str):
    """Upload a local file to Gemini using a file path (not raw bytes)."""
    ext  = os.path.splitext(path)[1].lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")
 
    for attempt in range(3):
        try:
            # Pass the file path directly — Gemini SDK opens it internally
            uploaded = client.files.upload(
                file=path,
                config=types.UploadFileConfig(
                    display_name=os.path.basename(path),
                    mime_type=mime,
                )
            )
            time.sleep(0.4)
            return uploaded
        except Exception as e:
            if attempt == 2:
                raise
            print(f"      Retry {attempt+1}/3 after error: {e}")
            time.sleep(2)
 
 
def match_assignment_to_files(
    client,
    course_file_refs: list,
    course_fnames: list[str],
    assignment_name: str,
    assignment_desc: str,
) -> list[dict]:
 
    file_list = "\n".join(f"{i+1}. {f}" for i, f in enumerate(course_fnames))
 
    prompt = f"""You are a study assistant. A student has the following assignment:
 
Assignment: {assignment_name}
Description: {assignment_desc or "No description provided."}
 
The following course files have been provided for you to read:
{file_list}
 
Instructions:
- Read the assignment and identify each topic or problem it covers.
- Read the actual content of each course file provided.
- Match each topic to the files whose content is genuinely relevant.
- Do NOT guess based on file names — base your answer only on actual file content.
 
Return ONLY valid JSON — no markdown, no explanation:
[
  {{
    "topic": "brief topic or problem",
    "matches": [
      {{ "filename": "exact filename", "reason": "one sentence citing specific content", "relevance": "high" | "medium" | "low" }}
    ]
  }}
]
 
Only include files whose actual content is relevant. Order by relevance descending.
Empty matches array if nothing is relevant."""
 
    contents = [
        types.Part.from_uri(file_uri=ref.uri, mime_type=ref.mime_type)
        for ref in course_file_refs
    ] + [prompt]
 
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=contents
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
 
 
# ── OUTPUT ────────────────────────────────────────────────────────────────────
 
def print_results(all_results: list[dict]) -> None:
    for result in all_results:
        print("\n" + "═" * 62)
        print(f"  📚 {result['course']}")
        print(f"  📝 {result['assignment']}")
        if result.get("due"):
            print(f"  🗓  Due: {result['due']}")
        print("═" * 62)
        for item in result["topics"]:
            print(f"\n  📌 {item.get('topic', 'General')}")
            print("  " + "─" * 50)
            matches = item.get("matches", [])
            if not matches:
                print("    No relevant files found.")
                continue
            for i, m in enumerate(matches, 1):
                relevance = m.get("relevance", "low").upper()
                tag = {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "⬜"}.get(relevance, "⬜")
                print(f"\n    {i}. {tag} [{relevance}]  {m['filename']}")
                print(f"       → {m['reason']}")
    print("\n" + "═" * 62 + "\n")
 
 
# ── MAIN ──────────────────────────────────────────────────────────────────────
 
def main():
    print("╔════════════════════════════════════════╗")
    print("║      CANVAS MATERIAL MATCHER           ║")
    print("╚════════════════════════════════════════╝")
 
    if "your-canvas" in CANVAS_TOKEN or "your-gemini" in GEMINI_API_KEY:
        print("\n⚠️  Fill in your credentials at the top of this file:")
        print("   CANVAS_DOMAIN  — e.g. umich.instructure.com")
        print("   CANVAS_TOKEN   — Canvas > Account > Settings > New Access Token")
        print("   GEMINI_API_KEY — https://aistudio.google.com/app/apikey\n")
        return
 
    client = genai.Client(api_key=GEMINI_API_KEY)
 
    print("\n🔗 Connecting to Canvas...")
    try:
        courses = get_active_courses()
    except Exception as e:
        print(f"❌ Could not connect to Canvas: {e}")
        return
 
    if not courses:
        print("❌ No courses found. Check CANVAS_DOMAIN and CANVAS_TOKEN.")
        return
 
    print(f"  ✓ Found {len(courses)} course(s):")
    for c in courses:
        print(f"    • {c['name']}")
 
    all_results = []
 
    with tempfile.TemporaryDirectory() as tmpdir:
        for course in courses:
            cid   = course["id"]
            cname = course["name"]
            print(f"\n{'─'*55}")
            print(f"📖 {cname}")
 
            assignments = get_upcoming_assignments(cid)
            if not assignments:
                print("   No assignments found.")
                continue
            print(f"  ✓ {len(assignments)} assignment(s)")
 
            print("  📂 Fetching course files...")
            canvas_files = get_course_files(cid)
            if not canvas_files:
                print("  ⚠️  No downloadable files found. Skipping.")
                continue
            print(f"  ✓ {len(canvas_files)} file(s) — downloading...")
 
            course_dir = os.path.join(tmpdir, str(cid))
            os.makedirs(course_dir, exist_ok=True)
 
            downloaded = []
            for cf in canvas_files:
                fname = cf.get("filename") or cf.get("display_name", "unknown")
                dest  = os.path.join(course_dir, fname)
                if download_file(cf, dest):
                    downloaded.append((fname, dest))
                    print(f"    ✓ {fname}")
 
            if not downloaded:
                print("  ⚠️  No files downloaded successfully. Skipping.")
                continue
 
            print(f"\n  ⬆️  Uploading {len(downloaded)} file(s) to Gemini...")
            course_file_refs = []
            course_fnames    = []
            for fname, fpath in downloaded:
                try:
                    ref = upload_to_gemini(client, fpath)
                    course_file_refs.append(ref)
                    course_fnames.append(fname)
                    print(f"    ✓ {fname}")
                except Exception as e:
                    print(f"    ⚠️  Could not upload {fname}: {e}")
 
            if not course_file_refs:
                print("  ⚠️  No files uploaded. Skipping.")
                continue
 
            for asgn in assignments:
                aname = asgn.get("name", "Unnamed Assignment")
                adesc = re.sub(r"<[^>]+>", " ", asgn.get("description") or "").strip()
                due   = asgn.get("due_at", "")[:10] if asgn.get("due_at") else ""
 
                print(f"\n  ⏳ Matching: {aname}")
                try:
                    topics = match_assignment_to_files(
                        client, course_file_refs, course_fnames, aname, adesc
                    )
                    all_results.append({
                        "course":     cname,
                        "assignment": aname,
                        "due":        due,
                        "topics":     topics,
                    })
                except json.JSONDecodeError:
                    print(f"    ❌ Could not parse response. Skipping.")
                except Exception as e:
                    print(f"    ❌ Error: {e}")
 
    if all_results:
        print_results(all_results)
    else:
        print("\n  No results to display.")
 
 
if __name__ == "__main__":
    main()
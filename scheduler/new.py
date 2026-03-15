"""
╔══════════════════════════════════════════════════════════════╗
║       MATERIAL MATCHER — Canvas LMS (All Courses)           ║
║  Auto-discovers every active course, fetches lecture files  ║
║  + assignments (incl. linked PDFs), and matches with Gemini ║
╚══════════════════════════════════════════════════════════════╝

Setup:
  1. pip install google-generativeai requests pypdf

  2. CANVAS_API_TOKEN — Canvas → Account → Settings →
       Approved Integrations → + New Access Token

  3. CANVAS_BASE_URL  — your school's Canvas URL,

  4. GEMINI_API_KEY   — https://aistudio.google.com/app/apikey (free)

"""

import os
import re
import json
import time
import tempfile
import urllib.parse


import requests
import google.generativeai as genai

# ── CONFIG ────────────────────────────────────────────────────────────────────
CANVAS_API_TOKEN = "7~wraGkmG3kPc92BECTUXvUfKx3FUFKTY47zMXJa9n9LxPEKX4NMyQvfZZKxH8Lumm"
CANVAS_BASE_URL  = "https://canvas.instructure.com"   # no trailing slash

GEMINI_API_KEY   = "AIzaSyBovGVXBEHCxmsuyOB9i-m8SsbMOcmQTUI"

# Only process courses whose enrollment_state is one of these
ACTIVE_STATES = {"active"}

# Optionally restrict to courses whose name contains one of these strings
# (case-insensitive). Leave empty [] to process ALL active courses.
COURSE_NAME_FILTER: list[str] = []

# Canvas assignment submission types to skip
SKIP_ASSIGNMENT_TYPES = {"online_quiz", "discussion_topic"}

# File extensions accepted as course material
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}


# ─────────────────────────────────────────────────────────────────────────────


# ── CANVAS API HELPERS ────────────────────────────────────────────────────────

def canvas_get(path: str, params: dict = None) -> any:
    """Paginated GET from Canvas REST API."""
    headers = {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    results = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        params = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


def canvas_download(url: str, dest_path: str) -> bool:
    """Stream-download a file (Canvas-auth aware)."""
    headers = {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    ⚠️  Download failed ({url}): {e}")
        return False


# ── COURSE DISCOVERY ──────────────────────────────────────────────────────────

def fetch_active_courses() -> list[dict]:
    """Return all courses the user is actively enrolled in."""
    print("\n🔍 Discovering courses...")
    try:
        enrollments = canvas_get("/courses", {
            "enrollment_state": "active",
            "per_page": 100,
            "include[]": ["term", "total_students"],
        })
    except Exception as e:
        print(f"  ❌ Could not fetch courses: {e}")
        return []

    courses = []
    for c in enrollments:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        if c.get("workflow_state") in ("completed", "deleted"):
            continue
        if COURSE_NAME_FILTER:
            name_lower = c["name"].lower()
            if not any(kw.lower() in name_lower for kw in COURSE_NAME_FILTER):
                continue
        courses.append(c)

    print(f"  ✓ Found {len(courses)} active course(s):")
    for c in courses:
        print(f"    • [{c['id']}] {c['name']}")
    return courses


# ── PER-COURSE FILE + ASSIGNMENT FETCHERS ─────────────────────────────────────

def fetch_course_files(course_id: int, course_dir: str) -> list[str]:
    """Download all supported files from a course's Files section."""
    try:
        files = canvas_get(f"/courses/{course_id}/files", {"per_page": 100})
    except Exception as e:
        print(f"    ⚠️  Could not fetch files: {e}")
        return []

    local_paths = []
    for f in files:
        fname = f.get("display_name") or f.get("filename") or "unknown"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        url = f.get("url") or f.get("download_url")
        if not url:
            continue
        dest = os.path.join(course_dir, "course_" + _safe(fname))
        if os.path.exists(dest):
            local_paths.append(dest)
            continue
        print(f"      ↓ {fname}")
        if canvas_download(url, dest):
            local_paths.append(dest)
        time.sleep(0.25)
    return local_paths


def fetch_assignments(course_id: int, course_dir: str) -> list[dict]:
    """
    Fetch all assignments and resolve content via 4-tier fallback:
      1. Direct Canvas file attachment
      2. Canvas file link in description HTML
      3. External PDF link in description
      4. Plain-text from description
    """
    try:
        raw = canvas_get(
            f"/courses/{course_id}/assignments",
            {"per_page": 100, "include[]": "submission"},
        )
    except Exception as e:
        print(f"    ⚠️  Could not fetch assignments: {e}")
        return []

    results = []
    for asgn in raw:
        sub_types = asgn.get("submission_types") or []
        if any(t in SKIP_ASSIGNMENT_TYPES for t in sub_types):
            continue

        name = asgn.get("name") or "Untitled"
        desc = asgn.get("description") or ""
        print(f"      📝 {name}")
        local_path = None

        # 1 — Native attachment list
        for att in asgn.get("attachments") or []:
            url = att.get("url") or att.get("download_url")
            fname = att.get("display_name") or att.get("filename") or "attachment"
            ext = os.path.splitext(fname)[1].lower()
            if url and ext in ALLOWED_EXTENSIONS:
                dest = os.path.join(course_dir, f"asgn_{_safe(name)}_{_safe(fname)}")
                if canvas_download(url, dest):
                    local_path = dest
                    print(f"        ✓ Attached file: {fname}")
                    break

        # 2 — Canvas file links inside description HTML
        if not local_path and desc:
            paths = _extract_canvas_file_links(desc, course_id, course_dir, name)
            if paths:
                local_path = paths[0]
                print(f"        ✓ Canvas-linked file: {os.path.basename(local_path)}")

        # 3 — External PDF link
        if not local_path and desc:
            local_path = _try_download_linked_pdf(desc, course_dir, name)
            if local_path:
                print(f"        ✓ External PDF downloaded.")

        # 4 — Plain-text fallback
        if not local_path and desc:
            txt = os.path.join(course_dir, f"asgn_{_safe(name)}.txt")
            plain = re.sub(r"<[^>]+>", " ", desc)
            plain = re.sub(r"\s+", " ", plain).strip()
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(f"Assignment: {name}\n\n{plain}")
            local_path = txt
            print(f"        ✓ Saved description as text fallback.")

        if local_path:
            results.append({"name": name, "local_path": local_path})
        else:
            print(f"        ⚠️  No content — skipping.")

    return results


def _extract_canvas_file_links(html: str, course_id: int, dest_dir: str, asgn_name: str) -> list[str]:
    pattern = r'href="([^"]*?/(?:courses/\d+/)?files/(\d+)[^"]*?)"'
    found = re.findall(pattern, html)
    paths = []
    for _, file_id in found:
        try:
            meta = canvas_get(f"/courses/{course_id}/files/{file_id}")
            fname = meta.get("display_name") or f"file_{file_id}.pdf"
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            url = meta.get("url") or meta.get("download_url")
            if not url:
                continue
            dest = os.path.join(dest_dir, f"asgn_{_safe(asgn_name)}_{_safe(fname)}")
            if canvas_download(url, dest):
                paths.append(dest)
        except Exception:
            pass
    return paths


def _try_download_linked_pdf(html: str, dest_dir: str, asgn_name: str) -> str | None:
    urls = re.findall(r'href=["\']([^"\']+)["\']', html)
    urls += re.findall(r'https?://[^\s"\'<>]+', html)
    headers = {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}

    for raw_url in dict.fromkeys(urls):
        if "/courses/" in raw_url and "/files/" not in raw_url and "download" not in raw_url:
            continue
        try:
            resp = requests.head(raw_url, headers=headers, allow_redirects=True, timeout=10)
            ct = resp.headers.get("Content-Type", "")
            final_url = resp.url
            is_pdf = ".pdf" in final_url.lower() or "application/pdf" in ct

            if not is_pdf:
                r2 = requests.get(raw_url, headers=headers, stream=True, timeout=15)
                first = next(r2.iter_content(256), b"")
                if not first.startswith(b"%PDF"):
                    continue
                dest = os.path.join(dest_dir, f"asgn_{_safe(asgn_name)}_linked.pdf")
                with open(dest, "wb") as f:
                    f.write(first)
                    for chunk in r2.iter_content(8192):
                        f.write(chunk)
                return dest

            fname = os.path.basename(urllib.parse.urlparse(final_url).path) or f"{_safe(asgn_name)}.pdf"
            dest = os.path.join(dest_dir, f"asgn_{_safe(asgn_name)}_{fname}")
            if canvas_download(final_url, dest):
                return dest
        except Exception:
            continue
    return None


# ── GEMINI HELPERS ────────────────────────────────────────────────────────────

def upload_to_gemini(file_paths: list[str]) -> dict[str, any]:
    uploaded = {}
    for path in file_paths:
        fname = os.path.basename(path)
        try:
            uploaded[fname] = genai.upload_file(path)
            time.sleep(0.4)
        except Exception as e:
            print(f"    ⚠️  Gemini upload failed for {fname}: {e}")
    return uploaded


def match_assignment(model, course_uploads: dict, asgn_upload, asgn_name: str) -> dict:
    content = [asgn_upload]
    lines = []
    for i, (fname, uf) in enumerate(course_uploads.items(), 1):
        content.append(uf)
        lines.append(f"{i}. {fname}")

    prompt = f"""You are a study assistant. The first document is a student's assignment.
The remaining documents are their course lecture/material files.

Course files:
{chr(10).join(lines)}

Instructions:
- Identify each individual problem or question in the assignment (use its number/label).
- Read the actual text of every course file.
- For each problem, list the course files whose content is genuinely relevant.
- Base matches ONLY on file content, not file names.

Return ONLY valid JSON, no markdown, no explanation:
[
  {{
    "topic": "Problem N — brief description",
    "matches": [
      {{"filename": "exact filename", "reason": "one sentence from that file's content", "relevance": "high"|"medium"|"low"}}
    ]
  }}
]
Order matches by relevance descending. Empty matches array if nothing relevant."""

    content.append(prompt)
    resp = model.generate_content(content)
    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return {"assignment": asgn_name, "topics": json.loads(raw.strip())}


# ── OUTPUT ────────────────────────────────────────────────────────────────────

def print_course_results(course_name: str, results: list[dict]) -> None:
    bar = "═" * 70
    print(f"\n{bar}")
    print(f"  COURSE: {course_name}")
    print(bar)
    for r in results:
        print(f"\n  ── Assignment: {r['assignment']}")
        for item in r["topics"]:
            print(f"\n    📌 {item.get('topic', '?')}")
            print("    " + "─" * 48)
            for i, m in enumerate(item.get("matches") or [], 1):
                rel = m.get("relevance", "low").upper()
                tag = {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "⬜"}.get(rel, "⬜")
                print(f"      {i}. {tag} [{rel}]  {m['filename']}")
                print(f"         → {m['reason']}")



def _safe(s: str) -> str:
    return re.sub(r"[^\w.\-]", "_", s)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║   MATERIAL MATCHER — Canvas All-Courses Mode    ║")
    print("╚══════════════════════════════════════════════════╝")

    if CANVAS_API_TOKEN == "YOUR_CANVAS_TOKEN_HERE":
        print("\n⚠️  Set CANVAS_API_TOKEN at the top of this file.")
        print("   Canvas → Account → Settings → Approved Integrations → + New Access Token\n")
        return
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n⚠️  Set GEMINI_API_KEY at the top of this file.")
        print("   Get a free key at: https://aistudio.google.com/app/apikey\n")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # ── 1. Discover all active courses ────────────────────────────────────────
    courses = fetch_active_courses()
    if not courses:
        print("\n❌ No active courses found.")
        return

    with tempfile.TemporaryDirectory() as tmp_root:
        for ci, course in enumerate(courses, 1):
            course_id   = course["id"]
            course_name = course["name"]
            print(f"\n{'▓' * 65}")
            print(f"  Course {ci}/{len(courses)}: {course_name}  (ID {course_id})")
            print(f"{'▓' * 65}")

            course_dir = os.path.join(tmp_root, str(course_id))
            os.makedirs(course_dir, exist_ok=True)

            # ── 2. Fetch course material files ────────────────────────────────
            print(f"\n  📂 Fetching course files...")
            course_paths = fetch_course_files(course_id, course_dir)
            if not course_paths:
                print(f"  ⚠️  No course files — skipping matching for this course.")
                continue
            print(f"  ✓ {len(course_paths)} file(s) downloaded.")

            # ── 3. Fetch assignments ──────────────────────────────────────────
            print(f"\n  📋 Fetching assignments...")
            assignments = fetch_assignments(course_id, course_dir)
            if not assignments:
                print(f"  ⚠️  No assignments found — skipping.")
                continue
            print(f"  ✓ {len(assignments)} assignment(s) collected.")

            # ── 4. Upload course files to Gemini (once per course) ────────────
            print(f"\n  ⬆️  Uploading {len(course_paths)} file(s) to Gemini...")
            course_uploads = upload_to_gemini(course_paths)
            if not course_uploads:
                print("  ❌ No files uploaded — skipping.")
                continue
            print(f"  ✓ Done.")

            # ── 5. Match each assignment ──────────────────────────────────────
            course_results = []
            for ai, asgn in enumerate(assignments, 1):
                aname = asgn["name"]
                apath = asgn["local_path"]
                print(f"\n  ⏳ [{ai}/{len(assignments)}] Matching: {aname}")
                try:
                    asgn_upload = genai.upload_file(apath)
                    result = match_assignment(model, course_uploads, asgn_upload, aname)
                    course_results.append(result)
                except json.JSONDecodeError:
                    print(f"    ❌ Non-JSON response for '{aname}' — skipping.")
                except Exception as e:
                    print(f"    ❌ Error: {e}")

            # ── 6. Print results ──────────────────────────────────────────────
            if course_results:
                print_course_results(course_name, course_results)

    print(f"\n{'═' * 70}")
    print("  ✅ All done!")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
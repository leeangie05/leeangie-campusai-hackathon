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

  3. CANVAS_BASE_URL  — your school's Canvas URL, e.g.
       "https://canvas.ucdavis.edu"  (must start with https://)

  4. GEMINI_API_KEY   — https://aistudio.google.com/app/apikey (free)
"""

import os
import re
import json
import time
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import google.generativeai as genai

# ── CONFIG ────────────────────────────────────────────────────────────────────
CANVAS_API_TOKEN = "7~wraGkmG3kPc92BECTUXvUfKx3FUFKTY47zMXJa9n9LxPEKX4NMyQvfZZKxH8Lumm"
CANVAS_BASE_URL  = "https://canvas.instructure.com"  # must start with https://

GEMINI_API_KEY   = "AIzaSyBovGVXBEHCxmsuyOB9i-m8SsbMOcmQTUI"

# Optionally restrict by course name substring (case-insensitive). [] = all.
COURSE_NAME_FILTER: list[str] = []

# Canvas assignment submission types to skip
SKIP_ASSIGNMENT_TYPES = {"online_quiz", "discussion_topic"}

# File extensions accepted as course material
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}

# Concurrency limits — tune down if you hit rate limits
CANVAS_DOWNLOAD_WORKERS = 6   # parallel Canvas file downloads
# ─────────────────────────────────────────────────────────────────────────────


# ── CANVAS API HELPERS ────────────────────────────────────────────────────────

import threading
_local = threading.local()

def _get_session() -> requests.Session:
    """Thread-local session — each thread gets its own SSL context."""
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {CANVAS_API_TOKEN}"})
        _local.session = s
    return _local.session


def canvas_get(path: str, params: dict = None) -> any:
    """Paginated GET from Canvas REST API."""
    sess = _get_session()
    url = f"{CANVAS_BASE_URL}/api/v1{path}"
    results = []
    while url:
        resp = sess.get(url, params=params, timeout=30)
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
    """Stream-download using a thread-local session."""
    sess = _get_session()
    try:
        with sess.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    ⚠️  Download failed ({url}): {e}")
        return False


# ── COURSE DISCOVERY ──────────────────────────────────────────────────────────

def fetch_active_courses() -> list[dict]:
    print("\n🔍 Discovering courses...")
    try:
        enrollments = canvas_get("/courses", {
            "enrollment_state": "active",
            "per_page": 100,
            "include[]": ["term"],
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
            if not any(kw.lower() in c["name"].lower() for kw in COURSE_NAME_FILTER):
                continue
        courses.append(c)

    print(f"  ✓ Found {len(courses)} active course(s):")
    for c in courses:
        print(f"    • [{c['id']}] {c['name']}")
    return courses


# ── FILE + ASSIGNMENT FETCHERS ────────────────────────────────────────────────

def _download_one_course_file(f: dict, course_dir: str) -> str | None:
    """Download a single Canvas file entry; return local path or None."""
    fname = f.get("display_name") or f.get("filename") or "unknown"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    url = f.get("url") or f.get("download_url")
    if not url:
        return None
    dest = os.path.join(course_dir, "course_" + _safe(fname))
    if os.path.exists(dest):
        return dest
    print(f"      ↓ {fname}")
    return dest if canvas_download(url, dest) else None


def fetch_course_files(course_id: int, course_dir: str) -> list[str]:
    """Download all supported course files in parallel."""
    try:
        files = canvas_get(f"/courses/{course_id}/files", {"per_page": 100})
    except Exception as e:
        print(f"    ⚠️  Could not fetch files: {e}")
        return []

    local_paths = []
    with ThreadPoolExecutor(max_workers=CANVAS_DOWNLOAD_WORKERS) as ex:
        futures = {ex.submit(_download_one_course_file, f, course_dir): f for f in files}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                local_paths.append(result)
    return local_paths


def fetch_assignments(course_id: int, course_dir: str) -> list[dict]:
    """
    Fetch all assignments and resolve content via 4-tier fallback.
    Canvas API calls are sequential (metadata); file downloads are parallel.
    """
    try:
        raw = canvas_get(
            f"/courses/{course_id}/assignments",
            {"per_page": 100, "include[]": "submission"},
        )
    except Exception as e:
        print(f"    ⚠️  Could not fetch assignments: {e}")
        return []

    # Build list of (name, desc, resolved_path) — resolutions run in parallel
    pending = []
    for asgn in raw:
        sub_types = asgn.get("submission_types") or []
        if any(t in SKIP_ASSIGNMENT_TYPES for t in sub_types):
            continue
        name = asgn.get("name") or "Untitled"
        desc = asgn.get("description") or ""
        attachments = asgn.get("attachments") or []
        pending.append((name, desc, attachments))

    results = []
    with ThreadPoolExecutor(max_workers=CANVAS_DOWNLOAD_WORKERS) as ex:
        futures = {
            ex.submit(_resolve_assignment, name, desc, atts, course_id, course_dir): name
            for name, desc, atts in pending
        }
        for fut in as_completed(futures):
            aname = futures[fut]
            local_path = fut.result()
            print(f"      📝 {aname}  →  {'✓' if local_path else '⚠️  no content'}")
            if local_path:
                results.append({"name": aname, "local_path": local_path})

    # Sort to match original assignment order
    order = {name: i for i, (name, _, __) in enumerate(pending)}
    results.sort(key=lambda r: order.get(r["name"], 999))
    return results


def _resolve_assignment(name: str, desc: str, attachments: list,
                         course_id: int, dest_dir: str) -> str | None:
    """Resolve one assignment to a local file path (4-tier fallback)."""
    # 1 — Native attachment
    for att in attachments:
        url = att.get("url") or att.get("download_url")
        fname = att.get("display_name") or att.get("filename") or "attachment"
        if url and os.path.splitext(fname)[1].lower() in ALLOWED_EXTENSIONS:
            dest = os.path.join(dest_dir, f"asgn_{_safe(name)}_{_safe(fname)}")
            if canvas_download(url, dest):
                return dest

    # 2 — Canvas file link in description
    if desc:
        paths = _extract_canvas_file_links(desc, course_id, dest_dir, name)
        if paths:
            return paths[0]

    # 3 — External PDF link
    if desc:
        path = _try_download_linked_pdf(desc, dest_dir, name)
        if path:
            return path

    # 4 — Plain-text fallback
    if desc:
        txt = os.path.join(dest_dir, f"asgn_{_safe(name)}.txt")
        plain = re.sub(r"<[^>]+>", " ", desc)
        plain = re.sub(r"\s+", " ", plain).strip()
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(f"Assignment: {name}\n\n{plain}")
        return txt

    return None


def _extract_canvas_file_links(html: str, course_id: int, dest_dir: str, asgn_name: str) -> list[str]:
    pattern = r'href="([^"]*?/(?:courses/\d+/)?files/(\d+)[^"]*?)"'
    found = re.findall(pattern, html)
    paths = []
    for _, file_id in found:
        try:
            meta = canvas_get(f"/courses/{course_id}/files/{file_id}")
            fname = meta.get("display_name") or f"file_{file_id}.pdf"
            if os.path.splitext(fname)[1].lower() not in ALLOWED_EXTENSIONS:
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
    for raw_url in dict.fromkeys(urls):
        if "/courses/" in raw_url and "/files/" not in raw_url and "download" not in raw_url:
            continue
        try:
            resp = _get_session().head(raw_url, allow_redirects=True, timeout=10)
            ct = resp.headers.get("Content-Type", "")
            final_url = resp.url
            is_pdf = ".pdf" in final_url.lower() or "application/pdf" in ct
            if not is_pdf:
                r2 = _get_session().get(raw_url, stream=True, timeout=15)
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
    """Upload all files to Gemini sequentially with retry on SSL errors."""
    uploaded = {}
    for path in file_paths:
        fname = os.path.basename(path)
        for attempt in range(1, 4):
            try:
                uploaded[fname] = genai.upload_file(path)
                print(f"    ⬆ {fname}")
                break
            except Exception as e:
                if attempt < 3:
                    wait = attempt * 2
                    print(f"    ⚠️  Upload attempt {attempt} failed for {fname} ({e}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"    ⚠️  Gemini upload failed for {fname}: {e}")
    return uploaded


def _build_match_prompt(lines: list[str]) -> str:
    return f"""You are a study assistant. The first document is a student's assignment.
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


def match_assignment(model, course_uploads: dict, asgn_upload, asgn_name: str) -> dict:
    content = [asgn_upload]
    lines = []
    for i, (fname, uf) in enumerate(course_uploads.items(), 1):
        content.append(uf)
        lines.append(f"{i}. {fname}")
    content.append(_build_match_prompt(lines))

    resp = model.generate_content(content)
    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return {"assignment": asgn_name, "topics": json.loads(raw.strip())}


def match_all_assignments(model, course_uploads: dict, assignments: list[dict]) -> list[dict]:
    """Run all assignment matches sequentially with retry on SSL errors."""
    results = []
    for asgn in assignments:
        aname = asgn["name"]
        apath = asgn["local_path"]
        print(f"    ⏳ Matching: {aname}")
        for attempt in range(1, 4):  # up to 3 attempts
            try:
                asgn_upload = genai.upload_file(apath)
                result = match_assignment(model, course_uploads, asgn_upload, aname)
                results.append(result)
                break
            except json.JSONDecodeError:
                print(f"    ❌ Non-JSON response for '{aname}' — skipping.")
                break
            except Exception as e:
                if attempt < 3:
                    wait = attempt * 2
                    print(f"    ⚠️  Attempt {attempt} failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"    ❌ All attempts failed for '{aname}': {e}")
    return results


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
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

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

            # ── Fetch files + assignments in parallel ─────────────────────────
            print(f"\n  📂 Fetching course files & assignments in parallel...")
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_files   = ex.submit(fetch_course_files, course_id, course_dir)
                f_asgns   = ex.submit(fetch_assignments,  course_id, course_dir)
                course_paths = f_files.result()
                assignments  = f_asgns.result()

            if not course_paths:
                print(f"  ⚠️  No course files — skipping.")
                continue
            if not assignments:
                print(f"  ⚠️  No assignments — skipping.")
                continue
            print(f"  ✓ {len(course_paths)} course file(s), {len(assignments)} assignment(s).")

            # ── Upload course files to Gemini (parallel) ──────────────────────
            print(f"\n  ⬆️  Uploading {len(course_paths)} course file(s) to Gemini...")
            course_uploads = upload_to_gemini(course_paths)
            if not course_uploads:
                print("  ❌ No files uploaded — skipping.")
                continue
            print(f"  ✓ {len(course_uploads)} file(s) uploaded.")

            # ── Match all assignments (parallel Gemini calls) ─────────────────
            print(f"\n  🔗 Matching {len(assignments)} assignment(s)...")
            course_results = match_all_assignments(model, course_uploads, assignments)

            if course_results:
                print_course_results(course_name, course_results)

    print(f"\n{'═' * 70}")
    print("  ✅ All done!")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
import google.generativeai as genai
import json
import os
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Get a FREE API key at: https://aistudio.google.com/app/apikey
API_KEY = ""

# Folder containing your course files (lectures, notes, slides, etc.)
FILES_FOLDER = "/Users/yichenghuang/hackathon/material_matching/course_files/Lecture notes"

# Folder containing your assignment PDFs
ASSIGNMENTS_FOLDER = "/Users/yichenghuang/hackathon/material_matching/course_files/Assignments"

# Only include these course file types
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}
# ─────────────────────────────────────────────────────────────────────────────


def read_files_from_folder(folder: str) -> list[str]:
    if not os.path.exists(folder):
        print(f"❌ Folder not found: {os.path.abspath(folder)}")
        return []
    files = []
    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            files.append(fname)
    return files


def read_assignments_from_folder(folder: str) -> list[str]:
    if not os.path.exists(folder):
        print(f"❌ Assignments folder not found: {os.path.abspath(folder)}")
        return []
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    ])


def upload_files(file_paths: list[str]) -> dict[str, any]:
    """Upload all files to Gemini and return a dict of filename -> uploaded file object."""
    uploaded = {}
    for path in file_paths:
        fname = os.path.basename(path)
        print(f"    Uploading {fname}...")
        try:
            uploaded[fname] = genai.upload_file(path)
            time.sleep(0.5)  # avoid rate limiting
        except Exception as e:
            print(f"    ⚠️  Could not upload {fname}: {e}")
    return uploaded


def match_one_assignment(
    model,
    course_uploads: dict[str, any],
    assignment_upload,
    assignment_name: str
) -> dict:

    # Build the content list: assignment PDF first, then all course files
    content = [assignment_upload]
    file_list_lines = []
    for i, (fname, uploaded) in enumerate(course_uploads.items(), 1):
        content.append(uploaded)
        file_list_lines.append(f"{i}. {fname}")

    file_list = "\n".join(file_list_lines)

    prompt = f"""You are a study assistant. The first document is a student's assignment.
The remaining documents are their course lecture files — you have access to the full text of each one.

Course files provided:
{file_list}

Instructions:
- Read the assignment carefully and identify each topic or problem it covers.
- Read the actual content of each course file.
- Match each assignment topic to the course files whose content is genuinely relevant.
- Do NOT guess based on file names — base your answer only on what is actually written in each file.

Return ONLY valid JSON — no markdown fences, no explanation — in this exact format:
[
  {{
    "topic": "brief topic or problem from the assignment",
    "matches": [
      {{ "filename": "exact filename from list", "reason": "one sentence citing specific content from that file that is relevant", "relevance": "high" | "medium" | "low" }}
    ]
  }}
]

Only include files whose actual content is relevant. Order by relevance descending.
If nothing matches a topic, return an empty matches array."""

    content.append(prompt)
    response = model.generate_content(content)
    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    topics = json.loads(raw.strip())
    return {"assignment": assignment_name, "topics": topics}


def print_results(all_results: list[dict]) -> None:
    for result in all_results:
        print("\n" + "═" * 60)
        print(f"  {result['assignment']}")
        print("═" * 60)

        for item in result["topics"]:
            print(f"\n  📌 {item.get('topic', 'General')}")
            print("  " + "─" * 48)

            matches = item.get("matches", [])
            if not matches:
                print("    No relevant files found.")
                continue

            for i, m in enumerate(matches, 1):
                relevance = m.get("relevance", "low").upper()
                tag = {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "⬜"}.get(relevance, "⬜")
                print(f"\n    {i}. {tag} [{relevance}]  {m['filename']}")
                print(f"       → {m['reason']}")

    print("\n" + "═" * 60 + "\n")


def main():
    print("╔══════════════════════════════════════╗")
    print("║        MATERIAL MATCHER              ║")
    print("║   Powered by Google Gemini (free)    ║")
    print("╚══════════════════════════════════════╝")

    if API_KEY == "your-gemini-api-key-here":
        print("\n⚠️  Add your free Gemini API key at the top of this file.")
        print("   Get one at: https://aistudio.google.com/app/apikey\n")
        return

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

    # Read course file names
    print(f"\n📂 Course files: {os.path.abspath(FILES_FOLDER)}")
    course_fnames = read_files_from_folder(FILES_FOLDER)
    if not course_fnames:
        print("  No supported course files found. Check FILES_FOLDER.")
        return
    print(f"  ✓ Found {len(course_fnames)} course file(s):")
    for f in course_fnames:
        print(f"    • {f}")

    # Read assignment paths
    print(f"\n📁 Assignments: {os.path.abspath(ASSIGNMENTS_FOLDER)}")
    assignment_paths = read_assignments_from_folder(ASSIGNMENTS_FOLDER)
    if not assignment_paths:
        print("  No PDF assignments found. Check ASSIGNMENTS_FOLDER.")
        return
    print(f"  ✓ Found {len(assignment_paths)} assignment(s):")
    for a in assignment_paths:
        print(f"    • {os.path.basename(a)}")

    # Upload all course files once (reused across all assignments)
    print(f"\n⬆️  Uploading {len(course_fnames)} course file(s) to Gemini...")
    course_paths = [os.path.join(FILES_FOLDER, f) for f in course_fnames]
    course_uploads = upload_files(course_paths)
    print(f"  ✓ Done uploading course files.")

    # Process each assignment
    all_results = []
    for i, pdf_path in enumerate(assignment_paths, 1):
        aname = os.path.basename(pdf_path)
        print(f"\n⏳ Processing assignment {i}/{len(assignment_paths)}: {aname}")
        try:
            print(f"    Uploading {aname}...")
            asgn_upload = genai.upload_file(pdf_path)
            result = match_one_assignment(model, course_uploads, asgn_upload, aname)
            all_results.append(result)
        except json.JSONDecodeError:
            print(f"  ❌ Could not parse response for {aname}. Skipping.")
        except Exception as e:
            print(f"  ❌ Error processing {aname}: {e}")

    if all_results:
        print_results(all_results)


if __name__ == "__main__":
    main()
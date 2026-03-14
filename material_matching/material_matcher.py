import google.generativeai as genai
import json
import os

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Get a FREE API key at: https://aistudio.google.com/app/apikey
API_KEY = "AIzaSyD4iqAQK3gMKQRPkPXOSlANK96IePgi_80"

# Folder containing your course files (lectures, notes, slides, etc.)
# Examples:
#   Windows: r"C:\Users\YourName\Downloads\CS280 Files"
#   Mac/Linux: "/Users/yourname/Downloads/CS280 Files"
FILES_FOLDER = "/Users/yichenghuang/hackathon/material_matching/course_files/Lecture notes"

# Folder containing your assignment PDFs (one PDF per assignment)
# Examples:
#   Windows: r"C:\Users\YourName\Downloads\Assignments"
#   Mac/Linux: "/Users/yourname/Downloads/Assignments"
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
    pdfs = []
    for fname in sorted(os.listdir(folder)):
        if fname.lower().endswith(".pdf"):
            pdfs.append(os.path.join(folder, fname))
    return pdfs


def match_one_assignment(model, files: list[str], assignment_path: str) -> dict:
    assignment_name = os.path.basename(assignment_path)

    print(f"  Uploading {assignment_name}...")
    uploaded = genai.upload_file(assignment_path)

    file_list = "\n".join(f"{i+1}. {f}" for i, f in enumerate(files))

    prompt = f"""You are a study assistant. A student has uploaded an assignment PDF.
Read the assignment carefully and identify all the topics, concepts, and subject areas it covers.

Then, from the following list of course files, identify which ones are most relevant to study for this assignment:
{file_list}

Return ONLY valid JSON — no markdown fences, no explanation — in this exact format:
[
  {{
    "topic": "brief topic or problem from the assignment",
    "matches": [
      {{ "filename": "exact filename from list", "reason": "one sentence why relevant", "relevance": "high" | "medium" | "low" }}
    ]
  }}
]

Group matches by topic or problem from the assignment. Only include files that are genuinely relevant.
Order matches by relevance descending. If nothing matches a topic, return an empty matches array."""

    response = model.generate_content([uploaded, prompt])
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

    # Read course files
    print(f"\n📂 Course files: {os.path.abspath(FILES_FOLDER)}")
    files = read_files_from_folder(FILES_FOLDER)
    if not files:
        print("  No supported course files found. Check FILES_FOLDER.")
        return
    print(f"  ✓ Found {len(files)} course file(s):")
    for f in files:
        print(f"    • {f}")

    # Read assignment PDFs
    print(f"\n📁 Assignments folder: {os.path.abspath(ASSIGNMENTS_FOLDER)}")
    assignment_pdfs = read_assignments_from_folder(ASSIGNMENTS_FOLDER)
    if not assignment_pdfs:
        print("  No PDF assignments found. Check ASSIGNMENTS_FOLDER.")
        return
    print(f"  ✓ Found {len(assignment_pdfs)} assignment(s):")
    for a in assignment_pdfs:
        print(f"    • {os.path.basename(a)}")

    # Process each assignment
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

    all_results = []
    for i, pdf_path in enumerate(assignment_pdfs, 1):
        print(f"\n⏳ Processing assignment {i}/{len(assignment_pdfs)}: {os.path.basename(pdf_path)}")
        try:
            result = match_one_assignment(model, files, pdf_path)
            all_results.append(result)
        except json.JSONDecodeError:
            print(f"  ❌ Could not parse response for {os.path.basename(pdf_path)}. Skipping.")
        except Exception as e:
            print(f"  ❌ Error processing {os.path.basename(pdf_path)}: {e}")

    if all_results:
        print_results(all_results)


if __name__ == "__main__":
    main()
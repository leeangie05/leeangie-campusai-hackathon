"""
╔══════════════════════════════════════════════════════════════╗
║     MATERIAL MATCHER — Canvas LMS + RAG Edition             ║
║                                                             ║
║  First run:  embeds all course files → persists to disk     ║
║  Later runs: skips re-embedding, only processes assignments ║
╚══════════════════════════════════════════════════════════════╝

Setup:
  pip install google-genai requests pypdf chromadb

  CANVAS_API_TOKEN — Canvas → Account → Settings →
    Approved Integrations → + New Access Token
  CANVAS_BASE_URL  — e.g. "https://canvas.ucdavis.edu"
  GEMINI_API_KEY   — https://aistudio.google.com/app/apikey (free)
"""

import os
import re
import json
import time
import hashlib
import tempfile
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import chromadb
from chromadb.config import Settings
from google import genai
from google.genai import types
from pypdf import PdfReader

# ── CONFIG ────────────────────────────────────────────────────────────────────
CANVAS_API_TOKEN = "7~wraGkmG3kPc92BECTUXvUfKx3FUFKTY47zMXJa9n9LxPEKX4NMyQvfZZKxH8Lumm"
CANVAS_BASE_URL  = "https://canvas.instructure.com"  # must start with https://
GEMINI_API_KEY   = "AIzaSyBovGVXBEHCxmsuyOB9i-m8SsbMOcmQTUI"

# Where to persist the vector DB between runs
CHROMA_DIR = "./material_matcher_db"

# How many top chunks to retrieve per problem
TOP_K = 6

# Chunk size in characters when splitting PDFs
CHUNK_SIZE    = 1500
CHUNK_OVERLAP = 200

# Models
GENERATION_MODEL = "gemini-3.1-flash-lite-preview"
EMBEDDING_MODEL  = "models/gemini-embedding-001"   # 768-dim, stable in new SDK

# Canvas assignment submission types to skip
SKIP_ASSIGNMENT_TYPES = {"online_quiz", "discussion_topic"}

# File extensions accepted as course material
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".txt", ".md"}

# Optionally restrict by course name substring (case-insensitive). [] = all.
COURSE_NAME_FILTER: list[str] = []

# Parallel Canvas downloads
CANVAS_DOWNLOAD_WORKERS = 6
# ─────────────────────────────────────────────────────────────────────────────


# ── GEMINI CLIENT (new SDK) ───────────────────────────────────────────────────

_gemini: genai.Client | None = None

def get_gemini() -> genai.Client:
    global _gemini
    if _gemini is None:
        _gemini = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini


# ── THREAD-LOCAL CANVAS SESSION ───────────────────────────────────────────────

_local = threading.local()

def _get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {CANVAS_API_TOKEN}"})
        _local.session = s
    return _local.session


def canvas_get(path: str, params: dict = None) -> any:
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
    sess = _get_session()
    try:
        with sess.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    ⚠️  Download failed: {e}")
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


# ── FILE FETCHERS ─────────────────────────────────────────────────────────────

def _download_one_course_file(f: dict, course_dir: str) -> str | None:
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
    try:
        raw = canvas_get(
            f"/courses/{course_id}/assignments",
            {"per_page": 100, "include[]": "submission"},
        )
    except Exception as e:
        print(f"    ⚠️  Could not fetch assignments: {e}")
        return []

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

    order = {name: i for i, (name, _, __) in enumerate(pending)}
    results.sort(key=lambda r: order.get(r["name"], 999))
    return results


def _resolve_assignment(name, desc, attachments, course_id, dest_dir) -> str | None:
    for att in attachments:
        url = att.get("url") or att.get("download_url")
        fname = att.get("display_name") or att.get("filename") or "attachment"
        if url and os.path.splitext(fname)[1].lower() in ALLOWED_EXTENSIONS:
            dest = os.path.join(dest_dir, f"asgn_{_safe(name)}_{_safe(fname)}")
            if canvas_download(url, dest):
                return dest
    if desc:
        paths = _extract_canvas_file_links(desc, course_id, dest_dir, name)
        if paths:
            return paths[0]
    if desc:
        path = _try_download_linked_pdf(desc, dest_dir, name)
        if path:
            return path
    if desc:
        txt = os.path.join(dest_dir, f"asgn_{_safe(name)}.txt")
        plain = re.sub(r"<[^>]+>", " ", desc)
        plain = re.sub(r"\s+", " ", plain).strip()
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(f"Assignment: {name}\n\n{plain}")
        return txt
    return None


def _extract_canvas_file_links(html, course_id, dest_dir, asgn_name) -> list[str]:
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


def _try_download_linked_pdf(html, dest_dir, asgn_name) -> str | None:
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


# ── TEXT EXTRACTION + CHUNKING ────────────────────────────────────────────────

def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext in (".txt", ".md"):
            with open(path, encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            with open(path, "rb") as f:
                return f.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    ⚠️  Could not extract text from {os.path.basename(path)}: {e}")
        return ""


def chunk_text(text: str, source: str) -> list[dict]:
    chunks = []
    start = 0
    text = re.sub(r"\s+", " ", text).strip()
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append({
                "text": chunk,
                "source": source,
                "chunk_id": f"{source}::{start}",
            })
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── GEMINI EMBEDDING (new SDK) ────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    client = get_gemini()
    embeddings = []
    for text in texts:
        for attempt in range(1, 4):
            try:
                resp = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
                )
                embeddings.append(resp.embeddings[0].values)
                break
            except Exception as e:
                if attempt < 3:
                    time.sleep(attempt * 2)
                else:
                    print(f"    ⚠️  Embedding failed: {e}")
                    embeddings.append([0.0] * 768)
    return embeddings


def embed_query(text: str) -> list[float]:
    client = get_gemini()
    for attempt in range(1, 4):
        try:
            resp = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )
            return resp.embeddings[0].values
        except Exception as e:
            if attempt < 3:
                time.sleep(attempt * 2)
            else:
                raise
    return [0.0] * 768


# ── VECTOR STORE (ChromaDB) ───────────────────────────────────────────────────

def get_or_create_collection(course_id: int) -> chromadb.Collection:
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=f"course_{course_id}",
        metadata={"hnsw:space": "cosine"},
    )


def file_fingerprint(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def index_course_files(course_id: int, file_paths: list[str]) -> chromadb.Collection:
    collection = get_or_create_collection(course_id)

    existing = collection.get(include=["metadatas"])
    indexed_fingerprints = {
        m["fingerprint"]
        for m in existing["metadatas"]
        if m and "fingerprint" in m
    }

    new_files = 0
    for path in file_paths:
        fname = os.path.basename(path)
        fp = file_fingerprint(path)

        if fp in indexed_fingerprints:
            print(f"    ✓ Cached: {fname}")
            continue

        print(f"    📄 Indexing: {fname}")
        text = extract_text(path)
        if not text.strip():
            print(f"      ⚠️  No text extracted.")
            continue

        chunks = chunk_text(text, fname)
        if not chunks:
            continue

        batch_size = 10
        for i in range(0, len(chunks), batch_size):
            batch  = chunks[i:i + batch_size]
            texts  = [c["text"] for c in batch]
            embeds = embed_texts(texts)
            collection.add(
                ids=[c["chunk_id"] for c in batch],
                embeddings=embeds,
                documents=texts,
                metadatas=[{"source": c["source"], "fingerprint": fp} for c in batch],
            )
        new_files += 1

    cached = len(file_paths) - new_files
    print(f"    ✓ Index ready  ({new_files} new, {cached} cached).")
    return collection


# ── RAG MATCHING (new SDK) ────────────────────────────────────────────────────

def _generate(prompt: str) -> str:
    """Call Gemini generation with retry."""
    client = get_gemini()
    for attempt in range(1, 4):
        try:
            resp = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            if attempt < 3:
                time.sleep(attempt * 2)
            else:
                raise


def _parse_json(raw: str) -> any:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def extract_problems(assignment_text: str) -> list[dict]:
    prompt = f"""You are a study assistant. Below is the text of a student assignment.
Identify each individual problem or question. For each one, write a short search query
capturing the key concepts needed to solve it.

Assignment text:
{assignment_text[:4000]}

Return ONLY valid JSON, no markdown:
[
  {{"problem": "Problem N — brief description", "query": "key concepts and topics for this problem"}}
]"""
    try:
        return _parse_json(_generate(prompt))
    except Exception as e:
        print(f"    ⚠️  Could not parse problems: {e}")
        return [{"problem": "General", "query": assignment_text[:500]}]


def retrieve_chunks(query: str, collection: chromadb.Collection) -> list[dict]:
    q_embed = embed_query(query)
    n = min(TOP_K, collection.count())
    if n == 0:
        return []
    results = collection.query(
        query_embeddings=[q_embed],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "score": round(1 - dist, 3),
        })
    return chunks


def synthesize_match(problem: str, chunks: list[dict]) -> dict:
    by_source: dict[str, list] = {}
    for c in chunks:
        by_source.setdefault(c["source"], []).append(c)

    context_parts = []
    for src, cs in by_source.items():
        combined = " ... ".join(c["text"] for c in cs[:3])
        context_parts.append(f"[{src}]\n{combined[:800]}")
    context = "\n\n".join(context_parts)

    prompt = f"""You are a study assistant. A student has this problem:

"{problem}"

Here are the most relevant excerpts from their course materials:

{context}

Based ONLY on the content above, list which files are relevant and why.

Return ONLY valid JSON, no markdown:
[
  {{"filename": "exact filename", "reason": "one sentence explaining relevance", "relevance": "high"|"medium"|"low"}}
]
Order by relevance descending. Only include files with genuinely relevant content."""

    try:
        matches = _parse_json(_generate(prompt))
        return {"topic": problem, "matches": matches}
    except Exception as e:
        print(f"      ⚠️  Synthesis failed: {e}")
        return {"topic": problem, "matches": []}


def match_assignment_rag(
    assignment_path: str,
    assignment_name: str,
    collection: chromadb.Collection,
) -> dict:
    text = extract_text(assignment_path)
    if not text.strip():
        return {"assignment": assignment_name, "topics": []}

    problems = extract_problems(text)
    print(f"      Found {len(problems)} problem(s).")

    topics = []
    for p in problems:
        chunks = retrieve_chunks(p["query"], collection)
        if not chunks:
            topics.append({"topic": p["problem"], "matches": []})
            continue
        result = synthesize_match(p["problem"], chunks)
        topics.append(result)

    return {"assignment": assignment_name, "topics": topics}


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
    print("║   MATERIAL MATCHER — Canvas + RAG Edition       ║")
    print("╚══════════════════════════════════════════════════╝")

    if CANVAS_API_TOKEN == "YOUR_CANVAS_TOKEN_HERE":
        print("\n⚠️  Set CANVAS_API_TOKEN at the top of this file.")
        return
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n⚠️  Set GEMINI_API_KEY at the top of this file.")
        return

    courses = fetch_active_courses()
    if not courses:
        print("\n❌ No active courses found.")
        return

    os.makedirs(CHROMA_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_root:
        for ci, course in enumerate(courses, 1):
            course_id   = course["id"]
            course_name = course["name"]
            print(f"\n{'▓' * 65}")
            print(f"  Course {ci}/{len(courses)}: {course_name}  (ID {course_id})")
            print(f"{'▓' * 65}")

            course_dir = os.path.join(tmp_root, str(course_id))
            os.makedirs(course_dir, exist_ok=True)

            # Fetch files + assignments in parallel
            print(f"\n  📂 Fetching course files & assignments...")
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_files = ex.submit(fetch_course_files, course_id, course_dir)
                f_asgns = ex.submit(fetch_assignments,  course_id, course_dir)
                course_paths = f_files.result()
                assignments  = f_asgns.result()

            if not course_paths:
                print(f"  ⚠️  No course files — skipping.")
                continue
            if not assignments:
                print(f"  ⚠️  No assignments — skipping.")
                continue
            print(f"  ✓ {len(course_paths)} course file(s), {len(assignments)} assignment(s).")

            # Index into vector store (skips already-indexed files)
            print(f"\n  🗄️  Indexing course files...")
            collection = index_course_files(course_id, course_paths)

            # Match each assignment via RAG
            print(f"\n  🔗 Matching {len(assignments)} assignment(s)...")
            course_results = []
            for ai, asgn in enumerate(assignments, 1):
                print(f"\n    ⏳ [{ai}/{len(assignments)}] {asgn['name']}")
                result = match_assignment_rag(asgn["local_path"], asgn["name"], collection)
                course_results.append(result)

            if course_results:
                print_course_results(course_name, course_results)

    print(f"\n{'═' * 70}")
    print(f"  ✅ All done!  Vector DB cached at: {os.path.abspath(CHROMA_DIR)}/")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    main()
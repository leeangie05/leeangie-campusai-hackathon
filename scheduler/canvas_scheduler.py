"""
Canvas + Gemini + Google Calendar Scheduler
============================================
1. Fetches upcoming assignments from Canvas LMS
2. Uses Gemini AI to estimate hours needed per assignment
3. Builds a proposed study schedule around due dates
4. Reads your existing Google Calendar and prints everything together

Setup:
  pip install requests google-auth google-auth-oauthlib google-api-python-client google-generativeai python-dotenv

.env file (place in same folder as this script):
  CANVAS_API_URL      = https://canvas.instructure.com
  CANVAS_API_TOKEN    = your_token
  GEMINI_API_KEY      = your_key
  GOOGLE_CREDS_FILE   = credentials.json
  CALENDAR_ID         = primary
  TIMEZONE            = America/Detroit
  WORK_START_HOUR     = 9
  WORK_END_HOUR       = 22
"""

import os
import re
import sys
import json
import math
import datetime
from zoneinfo import ZoneInfo

# Must be set before importing oauthlib
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from dotenv import load_dotenv
load_dotenv()

import requests
import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ── Config ─────────────────────────────────────────────────────────────────────

CANVAS_URL    = os.getenv("CANVAS_API_URL", "https://canvas.instructure.com").rstrip("/")
CANVAS_TOKEN  = os.getenv("CANVAS_API_TOKEN", "")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
CREDS_FILE    = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
TOKEN_FILE    = "token.json"
CALENDAR_ID   = os.getenv("CALENDAR_ID", "primary")
WORK_START    = int(os.getenv("WORK_START_HOUR", 9))
WORK_END      = int(os.getenv("WORK_END_HOUR", 22))
TZ_STR        = os.getenv("TIMEZONE", "America/Detroit")
TZ            = ZoneInfo(TZ_STR)
SCOPES        = ["https://www.googleapis.com/auth/calendar.readonly"]


# ── Canvas ─────────────────────────────────────────────────────────────────────

def canvas_get(endpoint: str, params: dict = None) -> list:
    """GET from Canvas API with automatic pagination."""
    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    url = f"{CANVAS_URL}/api/v1/{endpoint}"
    results = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url, params = None, None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


def fetch_assignments(days_ahead: int) -> list[dict]:
    """Return upcoming assignments with due dates within days_ahead."""
    now    = datetime.datetime.now(tz=datetime.timezone.utc)
    cutoff = now + datetime.timedelta(days=days_ahead)

    courses = [
        c for c in canvas_get("courses", {"enrollment_state": "active", "per_page": 50})
        if isinstance(c, dict) and c.get("id")
    ]

    assignments = []
    for course in courses:
        cid   = course["id"]
        cname = course.get("name", f"Course {cid}")
        try:
            raw = canvas_get(f"courses/{cid}/assignments", {"per_page": 100, "order_by": "due_at"})
        except requests.HTTPError:
            continue

        for a in raw:
            due_raw = a.get("due_at")
            if not due_raw:
                continue
            due_dt = datetime.datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            if due_dt < now or due_dt > cutoff:
                continue
            desc = re.sub(r"<[^>]+>", " ", a.get("description") or "").strip()[:500]
            assignments.append({
                "id":               a["id"],
                "name":             a["name"],
                "course":           cname,
                "due_at":           due_dt,
                "description":      desc,
                "points":           a.get("points_possible"),
                "submission_types": a.get("submission_types", []),
            })

    assignments.sort(key=lambda x: x["due_at"])
    return assignments


# ── Gemini ─────────────────────────────────────────────────────────────────────

def estimate_hours(assignments: list[dict]) -> list[dict]:
    """Use Gemini to estimate completion hours for each assignment."""
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

    lines = []
    for i, a in enumerate(assignments):
        due_str = a["due_at"].strftime("%A %b %d %H:%M")
        lines.append(
            f'{i+1}. [{a["course"]}] "{a["name"]}" — due {due_str}\n'
            f'   Points: {a["points"]} | Types: {", ".join(a["submission_types"])}\n'
            f'   Description: {a["description"] or "N/A"}'
        )

    prompt = (
        "You are an academic workload estimator. For each assignment below, "
        "estimate the total hours a typical college student needs to complete it "
        "(reading, research, writing, coding, studying, etc). "
        "A short quiz is about 0.5 h, a homework set about 2-4 h, a research paper about 8-15 h.\n\n"
        "Reply ONLY with a JSON array of objects with keys "
        '"index" (1-based int) and "hours" (float). No markdown, no explanation.\n\n'
        + "\n\n".join(lines)
    )

    response = model.generate_content(prompt)
    raw = response.text.strip().strip("```json").strip("```").strip()

    try:
        hour_map = {e["index"]: float(e["hours"]) for e in json.loads(raw)}
    except Exception as exc:
        print(f"  ⚠️  Gemini parse error ({exc}) — defaulting to 2 h each.")
        hour_map = {}

    for i, a in enumerate(assignments):
        a["estimated_hours"] = hour_map.get(i + 1, 2.0)

    return assignments


# ── Scheduler ──────────────────────────────────────────────────────────────────

def build_schedule(assignments: list[dict]) -> list[dict]:
    """
    Create study blocks (max 2 h each) placed before each due date.
    Blocks are scheduled as late as possible within WORK_START-WORK_END.
    """
    day_cursor: dict[datetime.date, int] = {}
    MAX_BLOCK  = 120
    today      = datetime.datetime.now(tz=TZ).date()
    events     = []

    for a in assignments:
        remaining  = math.ceil(a["estimated_hours"] * 60)
        due_date   = a["due_at"].astimezone(TZ).date()
        days_range = (due_date - today).days
        work_days  = [today + datetime.timedelta(days=d) for d in range(days_range)] or [today]

        for date in reversed(work_days):
            if remaining <= 0:
                break
            block_min = min(remaining, MAX_BLOCK)
            start_min = max(day_cursor.get(date, WORK_START * 60), WORK_START * 60)
            end_min   = start_min + block_min
            if end_min > WORK_END * 60:
                continue

            start_dt = datetime.datetime(date.year, date.month, date.day,
                                         start_min // 60, start_min % 60, tzinfo=TZ)
            end_dt   = datetime.datetime(date.year, date.month, date.day,
                                         end_min   // 60, end_min   % 60, tzinfo=TZ)
            day_cursor[date] = end_min

            events.append({
                "summary":   f"📚 {a['name']}",
                "course":    a["course"],
                "due_at":    a["due_at"],
                "est_total": a["estimated_hours"],
                "block_min": block_min,
                "start":     start_dt,
                "end":       end_dt,
            })
            remaining -= block_min

    events.sort(key=lambda e: e["start"])
    return events


# ── Google Calendar ────────────────────────────────────────────────────────────

def get_calendar_service():
    """Authenticate with read-only scope and return a Google Calendar service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("   🔄 Refreshing Google token…")
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080, prompt="consent")

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def read_calendar(service, days_ahead: int) -> list[dict]:
    """Fetch upcoming events from Google Calendar."""
    now    = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    cutoff = (datetime.datetime.now(tz=datetime.timezone.utc)
              + datetime.timedelta(days=days_ahead)).isoformat()
    try:
        return service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now,
            timeMax=cutoff,
            singleEvents=True,
            orderBy="startTime",
            maxResults=100,
        ).execute().get("items", [])
    except HttpError as e:
        print(f"  ❌ Calendar read error: {e}")
        return []


# ── Output ─────────────────────────────────────────────────────────────────────

def print_output(assignments: list[dict], study_blocks: list[dict], cal_events: list[dict]):
    W = 68

    print("\n" + "═" * W)
    print("  📅  YOUR GOOGLE CALENDAR")
    print("═" * W)
    if not cal_events:
        print("  (no upcoming events found)")
    else:
        for ev in cal_events:
            raw = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
            if "T" in raw:
                dt_str = datetime.datetime.fromisoformat(raw).astimezone(TZ).strftime("%a %b %d  %I:%M %p")
            else:
                dt_str = raw
            print(f"  {dt_str:<22}  {ev.get('summary', '(no title)')}")

    print("\n" + "═" * W)
    print("  📚  PROPOSED STUDY SCHEDULE")
    print("═" * W)
    if not study_blocks:
        print("  (no blocks generated)")
    else:
        current_date = None
        for b in study_blocks:
            if b["start"].date() != current_date:
                current_date = b["start"].date()
                print(f"\n  ▸ {b['start'].strftime('%A, %B %d')}")
                print(f"    {'─' * 58}")
            due_str = b["due_at"].astimezone(TZ).strftime("%b %d")
            print(
                f"    {b['start'].strftime('%I:%M %p')} – {b['end'].strftime('%I:%M %p')}"
                f"  ({b['block_min']} min)  {b['summary']}  [due {due_str}]"
            )

    print("\n" + "═" * W)
    print("  📊  ASSIGNMENT SUMMARY")
    print("═" * W)
    for a in assignments:
        due_str = a["due_at"].astimezone(TZ).strftime("%a %b %d %I:%M %p")
        print(f"  {a['name'][:42]:<42}  {a['estimated_hours']:>4.1f} h  due {due_str}")
        print(f"    └ {a['course']}")
    print("═" * W + "\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ("CANVAS_API_TOKEN", "GEMINI_API_KEY") if not os.getenv(v)]
    if missing:
        sys.exit(f"❌ Missing env vars: {', '.join(missing)}\n   Add them to your .env file.")

    days_ahead = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    print(f"\n🎓 Canvas Assignment Scheduler")
    print(f"   Lookahead: {days_ahead} days  |  Timezone: {TZ_STR}\n")

    print("📥 Fetching assignments from Canvas…")
    assignments = fetch_assignments(days_ahead)
    if not assignments:
        print("   No upcoming assignments found. Exiting.")
        return
    print(f"   Found {len(assignments)} assignment(s).\n")

    print("🤖 Estimating time with Gemini…")
    assignments = estimate_hours(assignments)
    for a in assignments:
        print(f"   {a['name'][:48]:<48}  {a['estimated_hours']:>4.1f} h")

    print("\n📅 Building study schedule…")
    study_blocks = build_schedule(assignments)
    print(f"   {len(study_blocks)} study block(s) generated.\n")

    print("📆 Connecting to Google Calendar (read-only)…")
    if not os.path.exists(CREDS_FILE):
        sys.exit(f"❌ Credentials file not found: {CREDS_FILE}")
    service    = get_calendar_service()
    cal_events = read_calendar(service, days_ahead)
    print(f"   {len(cal_events)} existing event(s) found.\n")

    print_output(assignments, study_blocks, cal_events)


if __name__ == "__main__":
    main()
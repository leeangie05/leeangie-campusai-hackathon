# Tempo
AI-powered study planner for college students.
Syncs with Canvas to import your courses, assignments, and lecture files — then uses Gemini AI to estimate how long each assignment will take, match your notes to specific problems, and schedule study blocks around your Google Calendar.

🔗 **Live at:** https://tempo-6gpu.onrender.com

---

## Features
- **Canvas Sync** — import all courses, assignments, and lecture files with one token paste
- **AI Time Estimation** — Gemini reads your actual assignment PDF and estimates completion time with reasoning
- **Problem-Level Material Matching** — matches each problem in an assignment to the specific lecture notes that cover it
- **Focus Timer** — counts down from your AI estimate with matched materials available in the same panel
- **Smart Scheduling** — connects to Google Calendar and auto-schedules study blocks in your free time
- **Social Accountability** — daily streaks, friend leaderboards, and session history

---

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Get a free Gemini API key:
   https://aistudio.google.com/apikey

3. Set your environment variables:
   ```bash
   # Mac/Linux
   export GEMINI_API_KEY=your_key_here
   export SECRET_KEY=any_random_string

   # Windows (PowerShell)
   $env:GEMINI_API_KEY="your_key_here"
   $env:SECRET_KEY="any_random_string"

   # Windows (CMD)
   set GEMINI_API_KEY=your_key_here
   set SECRET_KEY=any_random_string
   ```

4. Run the server:
   ```
   python server.py
   ```

5. Open your browser to:
   ```
   http://localhost:5000
   ```

---

## How it works

1. **Sign up** and paste your Canvas domain + access token to sync your semester automatically
2. Tempo downloads all your courses, upcoming assignments, and lecture files from Canvas
3. **Gemini AI** reads each assignment PDF and estimates how long it will take, with a reasoning explanation
4. Each assignment is matched to relevant lecture notes **problem by problem** — HIGH, MEDIUM, or LOW relevance
5. Connect **Google Calendar** to see your real schedule and generate suggested study blocks in free time slots
6. Open any assignment to start a **focus timer** that counts down from your estimate, with matched notes right there in the panel
7. Hit Complete — your session is logged, streaks update, and the assignment moves to your completed list

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Gunicorn |
| AI | Google Gemini 2.5 Flash (via google-genai SDK) |
| LMS Integration | Canvas LMS REST API |
| Calendar | Google Calendar API, Google OAuth 2.0 |
| PDF Processing | PyPDF2 |
| Frontend | Vanilla JavaScript, HTML/CSS (single-page app) |
| Hosting | Render.com |
| Storage | JSON flat-file (users, sessions, Canvas file cache) |

---

## Data

All session data is stored locally in `data/sessions.json` on the server. Canvas course files are cached in `canvas_cache/` per user per course. No data is shared with third parties.

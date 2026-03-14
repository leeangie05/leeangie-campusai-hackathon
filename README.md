# StudyClock

AI-powered assignment timer for UMich students.
Estimates how long you should spend on an assignment based on past student data,
then times you as you work.

## Setup

1. Install dependencies:
   pip install -r requirements.txt

2. Get a free Gemini API key:
   https://aistudio.google.com/apikey

3. Set your API key:
   # Mac/Linux
   export GEMINI_API_KEY=your_key_here

   # Windows (PowerShell)
   $env:GEMINI_API_KEY="your_key_here"

   # Windows (CMD)
   set GEMINI_API_KEY=your_key_here

4. Run the server:
   python server.py

5. Open your browser to:
   http://localhost:5000

## How it works

1. Enter your uniqname and course (e.g. EECS 281)
2. Upload your assignment PDF (and optionally your notes)
3. Gemini analyzes the assignment content + historical timing data
   from other students to estimate how long it should take
4. Start the timer and work — it tracks time vs. estimate in real time
5. When done, hit Done — your session is saved and improves future estimates

## Data

All session data is stored locally in data/sessions.json on the server.
All users' completed sessions are used (anonymously by course) to improve estimates.

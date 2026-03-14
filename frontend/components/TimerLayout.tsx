"use client";

import { useEffect, useState } from "react";

export default function TimerLayout() {
  const focusSeconds = 25 * 60;
  const breakSeconds = 5 * 60;

  const [timeLeft, setTimeLeft] = useState(focusSeconds);
  const [isRunning, setIsRunning] = useState(false);
  const [isBreak, setIsBreak] = useState(false);

  useEffect(() => {
    if (!isRunning) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev > 1) return prev - 1;

        if (!isBreak) {
          setIsBreak(true);
          setIsRunning(false);
          return breakSeconds;
        } else {
          setIsBreak(false);
          setIsRunning(false);
          return focusSeconds;
        }
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isRunning, isBreak]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };

  const handleStartPause = () => {
    setIsRunning((prev) => !prev);
  };

  const handleReset = () => {
    setIsRunning(false);
    setIsBreak(false);
    setTimeLeft(focusSeconds);
  };

  return (
    <main className="min-h-screen bg-[#f7f8fb] flex items-center justify-center px-6 py-8">
      <div className="w-full max-w-2xl rounded-[32px] border border-slate-200 bg-white p-10 shadow-sm">
        <h1 className="text-4xl font-bold text-slate-900">
          {isBreak ? "Break Time" : "Focus Session"}
        </h1>

        <p className="mt-4 text-slate-600">
          {isBreak
            ? "Take a 5-minute break."
            : "Work for 25 minutes with full focus."}
        </p>

        <div className="mt-10 text-center">
          <div className="text-7xl font-bold text-slate-900">
            {formatTime(timeLeft)}
          </div>
        </div>

        <div className="mt-10 flex justify-center gap-4">
          <button
            onClick={handleStartPause}
            className="rounded-2xl bg-blue-600 px-6 py-3 text-lg font-semibold text-white transition hover:bg-blue-700"
          >
            {isRunning ? "Pause" : "Start"}
          </button>

          <button
            onClick={handleReset}
            className="rounded-2xl bg-slate-200 px-6 py-3 text-lg font-semibold text-slate-800 transition hover:bg-slate-300"
          >
            Reset
          </button>
        </div>
      </div>
    </main>
  );
}
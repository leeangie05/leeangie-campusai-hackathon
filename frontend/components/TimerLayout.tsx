"use client";

import Link from "next/link";
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
    <main
      className={`min-h-screen flex items-center justify-center px-6 py-8 transition-colors duration-500 ${
        isRunning ? "bg-emerald-100" : "bg-[#f7f8fb]"
      }`}
    >
      <div className="w-full max-w-2xl rounded-[32px] border border-emerald-100 bg-white p-10 shadow-sm">
        <h1 className="text-4xl font-bold text-emerald-900">
          {isBreak ? "Break Time" : "Focus Session"}
        </h1>

        <p className="mt-4 text-emerald-700">
          {isBreak
            ? "Take a 5-minute break."
            : "Work for 25 minutes with full focus."}
        </p>

        <div className="mt-10 text-center">
          <div className="rounded-[28px] bg-white px-8 py-10 shadow-md border border-emerald-100">
            <div className="text-7xl font-bold tracking-wide text-emerald-700">
              {formatTime(timeLeft)}
            </div>
          </div>
        </div>

        <div className="mt-10 flex justify-center gap-4">
          <button
            onClick={handleStartPause}
            className="rounded-2xl bg-emerald-600 px-6 py-3 text-lg font-semibold text-white transition hover:bg-emerald-700"
          >
            {isRunning ? "Pause" : "Start"}
          </button>

          <button
            onClick={handleReset}
            className="rounded-2xl bg-emerald-50 px-6 py-3 text-lg font-semibold text-emerald-800 transition hover:bg-emerald-100"
          >
            Reset
          </button>
        </div>

        <div className="mt-8 flex justify-center">
          <Link href="/materials">
            <button className="rounded-2xl border border-emerald-200 bg-white px-6 py-3 text-lg font-semibold text-emerald-700 transition hover:bg-emerald-50">
              Access Relevant Materials
            </button>
          </Link>
        </div>
      </div>
    </main>
  );
}
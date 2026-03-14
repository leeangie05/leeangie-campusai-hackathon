import { StudySession } from "@/lib/data";
import Link from "next/link";

type TodayPlanProps = {
  time: string;
  title: string;
  description: string;
};

export function TodayPlanCard({ time, title, description }: TodayPlanProps) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-2xl font-semibold text-slate-900">Today’s Study Plan</h3>

      <div className="mt-5 rounded-2xl bg-slate-50 p-4">
        <p className="text-sm font-medium text-slate-500">{time}</p>
        <h4 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h4>
        <p className="mt-3 text-slate-600">{description}</p>
      </div>
    </div>
  );
}

type WeeklyProps = {
  sessions: StudySession[];
};

export function WeeklyScheduleCard({ sessions }: WeeklyProps) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-2xl font-semibold text-slate-900">Weekly Study Schedule</h3>

      <div className="mt-5 space-y-4">
        {sessions.map((session) => (
          <div key={session.id} className="rounded-2xl bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-500">{session.day}</p>
            <p className="mt-2 text-sm text-slate-500">{session.time}</p>

            <div className="mt-2 flex items-center justify-between gap-3">
              <h4 className="text-lg font-semibold text-slate-900">{session.title}</h4>
              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                {session.duration}
              </span>
            </div>

            <p className="mt-2 text-sm text-slate-600">{session.note}</p>
          </div>
        ))}
      </div>

      <Link href="/timer" className="block">
        <div className="w-full rounded-2xl bg-blue-600 px-6 py-5 text-center text-lg font-semibold text-white transition hover:bg-blue-700">
          Start Next Session
        </div>
      </Link>
    </div>
  );
}
import { StudySession } from "@/lib/data";

type TodayPlanProps = {
  time: string;
  title: string;
  description: string;
};

export function TodayPlanCard({ time, title, description }: TodayPlanProps) {
  return (
    <div className="rounded-3xl border border-emerald-100 bg-emerald-50/60 p-6 shadow-sm">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-700">
        Next Focus
      </p>

      <div className="mt-4 rounded-2xl bg-white p-5">
        <p className="text-sm font-medium text-slate-500">{time}</p>
        <h3 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h3>
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
      <h3 className="text-2xl font-semibold text-slate-900">This Week</h3>
      <p className="mt-2 text-slate-600">
        A simple view of your upcoming study sessions.
      </p>

      <div className="mt-5 space-y-4">
        {sessions.map((session) => (
          <div key={session.id} className="rounded-2xl bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-slate-500">{session.day}</p>
                <p className="mt-1 text-sm text-slate-500">{session.time}</p>
              </div>

              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                {session.duration}
              </span>
            </div>

            <h4 className="mt-3 text-lg font-semibold text-slate-900">{session.title}</h4>
            <p className="mt-2 text-sm text-slate-600">{session.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
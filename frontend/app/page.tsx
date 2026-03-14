import Link from "next/link";
import AssignmentCard from "@/components/AssignmentCard";
import { TodayPlanCard, WeeklyScheduleCard } from "@/components/StudyPlanCard";
import { assignments, todayPlan, weeklySchedule } from "@/lib/data";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#f4f7f3] px-6 py-8 md:px-10">
      <div className="mx-auto max-w-7xl">
        <div className="rounded-[32px] border border-emerald-100 bg-white p-6 shadow-sm md:p-10">
          <div className="mb-10 flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="mb-6 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-100 text-xl">
                  📘
                </div>
                <span className="text-3xl font-bold tracking-tight text-slate-900">
                  Syllabot
                </span>
              </div>

              <h1 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl">
                Good afternoon, Angie
              </h1>
              <p className="mt-3 max-w-2xl text-lg text-slate-600">
                Your study plan is ready. Start your next session or review what’s coming up.
              </p>
            </div>

            <Link href="/timer" className="shrink-0">
              <div className="rounded-2xl bg-emerald-600 px-6 py-4 text-lg font-semibold text-white transition hover:bg-emerald-700">
                Start Next Session
              </div>
            </Link>
          </div>

          <div className="grid gap-8 xl:grid-cols-[1.7fr_1fr]">
            <section>
              <h2 className="mb-5 text-3xl font-semibold tracking-tight text-slate-900">
                Upcoming Assignments
              </h2>

              <div className="grid gap-5 md:grid-cols-2">
                {assignments.map((assignment) => (
                  <AssignmentCard key={assignment.id} assignment={assignment} />
                ))}
              </div>
            </section>

            <aside className="space-y-5">
              <TodayPlanCard
                time={todayPlan.time}
                title={todayPlan.title}
                description={todayPlan.description}
              />
              <WeeklyScheduleCard sessions={weeklySchedule} />
            </aside>
          </div>
        </div>
      </div>
    </main>
  );
}
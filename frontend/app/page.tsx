import AssignmentCard from "@/components/AssignmentCard";
import StatCard from "@/components/StatCard";
import { TodayPlanCard, WeeklyScheduleCard } from "@/components/StudyPlanCard";
import { assignments, todayPlan, weeklySchedule } from "@/lib/data";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#f7f8fb] px-6 py-8 md:px-10">
      <div className="mx-auto max-w-7xl">
        <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm md:p-10">
          <div className="mb-10 flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="mb-6 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-xl">
                  📘
                </div>
                <span className="text-3xl font-bold tracking-tight text-slate-900">
                  Syllabot
                </span>
              </div>

              <h1 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl">
                Good afternoon, Angie
              </h1>
              <p className="mt-3 text-lg text-slate-600">
                Here’s what you should focus on this week.
              </p>
            </div>

            <button className="rounded-2xl bg-blue-600 px-6 py-4 text-lg font-semibold text-white transition hover:bg-blue-700">
              Generate Study Plan
            </button>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <StatCard
              icon="📝"
              title="Assignments Due Soon"
              subtitle="Next: History 101 Discussion in 1 day"
              tone="blue"
            />
            <StatCard
              icon="⏰"
              title="6.5 hours"
              subtitle="Planned Study Time"
              footer="Today"
              tone="amber"
            />
            <StatCard
              icon="🚩"
              title="Upcoming"
              subtitle="Stats 250 Homework 8"
              footer="Due in 23h"
              tone="rose"
            />
          </div>

          <div className="mt-10 grid gap-8 lg:grid-cols-[1.7fr_1fr]">
            <div>
              <h2 className="mb-5 text-3xl font-semibold tracking-tight text-slate-900">
                Upcoming Assignments
              </h2>

              <div className="grid gap-5 md:grid-cols-2">
                {assignments.map((assignment) => (
                  <AssignmentCard key={assignment.id} assignment={assignment} />
                ))}
              </div>
            </div>

            <div className="space-y-5">
              <TodayPlanCard
                time={todayPlan.time}
                title={todayPlan.title}
                description={todayPlan.description}
              />
              <WeeklyScheduleCard sessions={weeklySchedule} />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
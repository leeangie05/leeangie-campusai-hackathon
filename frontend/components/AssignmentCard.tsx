import { Assignment } from "@/lib/data";

type Props = {
  assignment: Assignment;
};

function getPriorityStyles(priority: Assignment["priority"]) {
  switch (priority) {
    case "Urgent":
      return "bg-rose-100 text-rose-700";
    case "Medium":
      return "bg-amber-100 text-amber-700";
    case "Low Effort":
      return "bg-sky-100 text-sky-700";
    default:
      return "bg-slate-100 text-slate-700";
  }
}

function getCourseStyles(course: string) {
  if (course.includes("STATS")) return "bg-rose-500";
  if (course.includes("EECS")) return "bg-blue-500";
  if (course.includes("HISTORY")) return "bg-teal-500";
  if (course.includes("BIOL")) return "bg-sky-500";
  return "bg-slate-500";
}

export default function AssignmentCard({ assignment }: Props) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-3">
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold tracking-wide text-white ${getCourseStyles(
            assignment.course
          )}`}
        >
          {assignment.course}
        </span>

        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${getPriorityStyles(
              assignment.priority
            )}`}
          >
            {assignment.priority}
          </span>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
            {assignment.estimate}
          </span>
        </div>
      </div>

      <h3 className="text-3xl font-semibold tracking-tight text-slate-900">
        {assignment.title}
      </h3>

      <p className="mt-2 text-lg text-slate-600">{assignment.dueDate}</p>

      <p className="mt-4 min-h-[60px] text-slate-600">{assignment.description}</p>

      <div className="mt-5 flex gap-3">
        <button className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-medium text-slate-700 transition hover:bg-slate-100">
          View Study Plan
        </button>
        <button className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 font-medium text-blue-700 transition hover:bg-blue-100">
          Related Materials
        </button>
      </div>
    </div>
  );
}
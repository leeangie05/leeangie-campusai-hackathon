const assignments = [
  {
    id: 1,
    course: "EECS 281",
    title: "Project 3",
    dueDate: "Mar 15, 11:59 PM",
    description: "Implement graph algorithms and submit a short report.",
  },
  {
    id: 2,
    course: "Stats 250",
    title: "Homework 8",
    dueDate: "Mar 14, 5:00 PM",
    description: "Complete probability and confidence interval problems.",
  },
  {
    id: 3,
    course: "History 101",
    title: "Discussion Post",
    dueDate: "Mar 16, 9:00 AM",
    description: "Write a response to this week’s reading.",
  },
];

function estimateMinutes(title: string, description: string) {
  const text = `${title} ${description}`.toLowerCase();

  if (text.includes("discussion")) return 30;
  if (text.includes("quiz")) return 45;
  if (text.includes("homework")) return 90;
  if (text.includes("project")) return 180;
  if (text.includes("essay")) return 240;

  return 60;
}

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="mb-2 text-4xl font-bold text-slate-900">Study Planner</h1>
        <p className="mb-8 text-slate-600">
          Your upcoming assignments and estimated study time.
        </p>

        <div className="grid gap-4">
          {assignments.map((assignment) => (
            <div
              key={assignment.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="mb-2 flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-indigo-600">
                    {assignment.course}
                  </p>
                  <h2 className="text-xl font-semibold text-slate-900">
                    {assignment.title}
                  </h2>
                </div>
                <div className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">
                  {estimateMinutes(assignment.title, assignment.description)} min
                </div>
              </div>

              <p className="mb-3 text-slate-600">{assignment.description}</p>
              <p className="text-sm text-slate-500">Due: {assignment.dueDate}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
export default function MaterialsPage() {
  return (
    <main className="min-h-screen bg-emerald-50 flex items-center justify-center px-6 py-8">
      <div className="w-full max-w-3xl rounded-[32px] bg-white p-10 shadow-sm">
        <h1 className="text-4xl font-bold text-emerald-900">
          Relevant Materials
        </h1>

        <p className="mt-4 text-emerald-700">
          Here are the lectures and study resources recommended for this assignment.
        </p>

        <div className="mt-8 space-y-4">
          <div className="rounded-2xl border border-emerald-100 p-5">
            <h2 className="text-xl font-semibold text-emerald-800">Lecture 5</h2>
            <p className="text-slate-600">Introduction to the topic you should review.</p>
          </div>

          <div className="rounded-2xl border border-emerald-100 p-5">
            <h2 className="text-xl font-semibold text-emerald-800">Lecture 6</h2>
            <p className="text-slate-600">More detailed examples and concepts for this assignment.</p>
          </div>

          <div className="rounded-2xl border border-emerald-100 p-5">
            <h2 className="text-xl font-semibold text-emerald-800">Practice Problems</h2>
            <p className="text-slate-600">Extra practice to help you prepare before submitting.</p>
          </div>
        </div>
      </div>
    </main>
  );
}
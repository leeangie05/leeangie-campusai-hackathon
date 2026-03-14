"use client";

import { estimateTime } from "@/lib/scheduler";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

type Course = {
  course_name: string;
  course_code: string;
};

type Assignment = {
  courseIndex: number;
  title: string;
  due_date: string;
  description: string;
};

function getDueInDays(dueDate: string): number {
  if (!dueDate) return 7;

  const now = new Date();
  const due = new Date(dueDate);
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  return Math.max(diffDays, 0);
}

export default function OnboardingPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [userId, setUserId] = useState<string | null>(null);

  const [courses, setCourses] = useState<Course[]>([
    { course_name: "", course_code: "" },
  ]);

  const [assignments, setAssignments] = useState<Assignment[]>([
    {
      courseIndex: 0,
      title: "",
      due_date: "",
      description: "",
    },
  ]);

  useEffect(() => {
    const getUser = async () => {
      const { data, error } = await supabase.auth.getUser();

      if (error || !data.user) {
        router.push("/auth");
        return;
      }

      setUserId(data.user.id);
    };

    getUser();
  }, [router]);

  const updateCourse = (
    index: number,
    field: keyof Course,
    value: string
  ) => {
    const updated = [...courses];
    updated[index][field] = value;
    setCourses(updated);
  };

  const addCourse = () => {
    setCourses([...courses, { course_name: "", course_code: "" }]);
  };

  const updateAssignment = (
    index: number,
    field: keyof Assignment,
    value: string | number
  ) => {
    const updated = [...assignments];
    updated[index][field] = value as never;
    setAssignments(updated);
  };

  const addAssignment = () => {
    setAssignments([
      ...assignments,
      {
        courseIndex: 0,
        title: "",
        due_date: "",
        description: "",
      },
    ]);
  };

  const handleSubmit = async () => {
    if (!userId) {
      setMessage("User not loaded yet.");
      return;
    }

    const validCourses = courses.filter(
      (course) => course.course_name.trim() !== ""
    );

    if (validCourses.length === 0) {
      setMessage("Please add at least one course.");
      return;
    }

    const validAssignments = assignments.filter(
      (assignment) => assignment.title.trim() !== ""
    );

    setLoading(true);
    setMessage("");

    try {
      const { data: insertedCourses, error: courseError } = await supabase
        .from("courses")
        .insert(
          validCourses.map((course) => ({
            user_id: userId,
            course_name: course.course_name,
            course_code: course.course_code,
          }))
        )
        .select();

      if (courseError) throw courseError;

      if (!insertedCourses || insertedCourses.length === 0) {
        throw new Error("Courses were not saved.");
      }

      if (validAssignments.length > 0) {
        const assignmentRows = validAssignments.map((assignment) => {
          const matchedCourse = insertedCourses[assignment.courseIndex];

          return {
            user_id: userId,
            course_id: matchedCourse.id,
            title: assignment.title,
            description: assignment.description,
            due_date: assignment.due_date || null,
            estimated_minutes: Math.round(
            estimateTime({
                course: matchedCourse.course_name,
                assignment_name: assignment.title,
                type: "homework",
                points: 100,
                difficulty: 3,
                due_in_days: getDueInDays(assignment.due_date),
            }) * 60
            ),
          };
        });

        const { error: assignmentError } = await supabase
          .from("assignments")
          .insert(assignmentRows);

        if (assignmentError) throw assignmentError;
      }

      router.push("/dashboard");
    } catch (err: any) {
      setMessage(err.message || "Something went wrong while saving.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f7f8fb] px-6 py-10">
      <div className="mx-auto max-w-4xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-4xl font-bold text-slate-900">Welcome to Syllabot</h1>
        <p className="mt-3 text-slate-600">
          Let’s set up your courses and assignments.
        </p>

        <section className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-2xl font-semibold text-slate-900">Courses</h2>
            <button
              type="button"
              onClick={addCourse}
              className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
            >
              + Add Course
            </button>
          </div>

          <div className="space-y-4">
            {courses.map((course, index) => (
              <div
                key={index}
                className="grid gap-4 rounded-2xl border border-slate-200 p-4 md:grid-cols-2"
              >
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Course Name
                  </label>
                  <input
                    type="text"
                    value={course.course_name}
                    onChange={(e) =>
                      updateCourse(index, "course_name", e.target.value)
                    }
                    placeholder="e.g. EECS 281"
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Course Code
                  </label>
                  <input
                    type="text"
                    value={course.course_code}
                    onChange={(e) =>
                      updateCourse(index, "course_code", e.target.value)
                    }
                    placeholder="e.g. Data Structures & Algorithms"
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-2xl font-semibold text-slate-900">Assignments</h2>
            <button
              type="button"
              onClick={addAssignment}
              className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
            >
              + Add Assignment
            </button>
          </div>

          <div className="space-y-4">
            {assignments.map((assignment, index) => (
              <div
                key={index}
                className="space-y-4 rounded-2xl border border-slate-200 p-4"
              >
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Course
                  </label>
                  <select
                    value={assignment.courseIndex}
                    onChange={(e) =>
                      updateAssignment(index, "courseIndex", Number(e.target.value))
                    }
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  >
                    {courses.map((course, courseIndex) => (
                      <option key={courseIndex} value={courseIndex}>
                        {course.course_name || `Course ${courseIndex + 1}`}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Assignment Title
                  </label>
                  <input
                    type="text"
                    value={assignment.title}
                    onChange={(e) =>
                      updateAssignment(index, "title", e.target.value)
                    }
                    placeholder="e.g. Homework 5"
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Due Date
                  </label>
                  <input
                    type="datetime-local"
                    value={assignment.due_date}
                    onChange={(e) =>
                      updateAssignment(index, "due_date", e.target.value)
                    }
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Description
                  </label>
                  <textarea
                    value={assignment.description}
                    onChange={(e) =>
                      updateAssignment(index, "description", e.target.value)
                    }
                    placeholder="What is this assignment about?"
                    className="min-h-[110px] w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500"
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="mt-10 flex items-center justify-between gap-4">
          <p className="text-sm text-slate-600">{message}</p>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className="rounded-2xl bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Saving..." : "Save & Continue"}
          </button>
        </div>
      </div>
    </main>
  );
}
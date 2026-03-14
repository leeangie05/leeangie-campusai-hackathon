export type Assignment = {
  id: number;
  course: string;
  title: string;
  dueDate: string;
  description: string;
  priority: "Urgent" | "Medium" | "Low Effort";
  estimate: string;
};

export type StudySession = {
  id: number;
  day: string;
  time: string;
  title: string;
  duration: string;
  note: string;
};

export const assignments: Assignment[] = [
  {
    id: 1,
    course: "STATS 250",
    title: "Homework 8",
    dueDate: "Mar 14, 5:00 PM",
    description: "Review probability and confidence interval problems before submission.",
    priority: "Urgent",
    estimate: "90 min",
  },
  {
    id: 2,
    course: "EECS 281",
    title: "Project 3",
    dueDate: "Mar 16, 11:59 PM",
    description: "Prepare graph algorithm implementation and finish the write-up.",
    priority: "Medium",
    estimate: "3 hours",
  },
  {
    id: 3,
    course: "HISTORY 101",
    title: "Discussion Post",
    dueDate: "Mar 17, 9:00 AM",
    description: "Write a thoughtful response to this week’s reading and reply to one peer.",
    priority: "Low Effort",
    estimate: "45 min",
  },
  {
    id: 4,
    course: "BIOL 120",
    title: "Quiz 2",
    dueDate: "Mar 18, 3:00 PM",
    description: "Study lecture concepts and review the cell structure diagrams.",
    priority: "Medium",
    estimate: "1 hour",
  },
];

export const todayPlan = {
  time: "Tonight: 7:00 PM – 8:00 PM",
  title: "Stats 250 Homework 8",
  description:
    "Review probability and confidence interval problems before it’s due tomorrow at 5:00 PM.",
};

export const weeklySchedule: StudySession[] = [
  {
    id: 1,
    day: "Saturday",
    time: "4:00 PM – 5:30 PM",
    title: "EECS 281 Project 3",
    duration: "90 min",
    note: "Start early because this is the highest-effort assignment this week.",
  },
  {
    id: 2,
    day: "Saturday",
    time: "2:00 PM – 3:00 PM",
    title: "History 101 Discussion Post",
    duration: "60 min",
    note: "Quick lower-effort block before larger assignments later in the weekend.",
  },
  {
    id: 3,
    day: "Sunday",
    time: "6:00 PM – 7:00 PM",
    title: "Biol 120 Quiz 2",
    duration: "60 min",
    note: "Review lecture concepts and diagrams while material is still fresh.",
  },
];
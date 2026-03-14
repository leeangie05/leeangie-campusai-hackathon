export type SchedulerAssignment = {
  course: string;
  assignment_name: string;
  type: string;
  points: number;
  difficulty: number;
  due_in_days: number;
};

export type StudyBlock = {
  course: string;
  assignment_name: string;
  block_number: number;
  hours: number;
};

export function estimateTime(assignment: SchedulerAssignment): number {
  const assignmentType = assignment.type;
  const points = assignment.points;
  const difficulty = assignment.difficulty;

  let hours: number;

  if (assignmentType === "quiz") {
    hours = 1.5;
  } else if (assignmentType === "homework") {
    hours = 3;
  } else if (assignmentType === "lab") {
    hours = 2.5;
  } else if (assignmentType === "essay") {
    hours = 6;
  } else if (assignmentType === "project") {
    hours = 8;
  } else if (assignmentType === "exam") {
    hours = 10;
  } else {
    hours = 3;
  }

  if (points >= 200) {
    hours += 2;
  } else if (points >= 100) {
    hours += 1;
  } else if (points >= 50) {
    hours += 0.5;
  }

  if (difficulty === 2) {
    hours += 0.5;
  } else if (difficulty === 3) {
    hours += 1;
  } else if (difficulty === 4) {
    hours += 2;
  } else if (difficulty === 5) {
    hours += 3;
  }

  return hours;
}

export function calculatePriority(assignment: SchedulerAssignment): number {
  const dueInDays = assignment.due_in_days;
  const points = assignment.points;
  const difficulty = assignment.difficulty;
  const estimatedHours = estimateTime(assignment);

  let priority = 0;

  if (dueInDays <= 1) {
    priority += 10;
  } else if (dueInDays <= 3) {
    priority += 7;
  } else if (dueInDays <= 7) {
    priority += 5;
  } else {
    priority += 2;
  }

  if (estimatedHours >= 8) {
    priority += 4;
  } else if (estimatedHours >= 5) {
    priority += 3;
  } else if (estimatedHours >= 3) {
    priority += 2;
  } else {
    priority += 1;
  }

  priority += difficulty;

  if (points >= 200) {
    priority += 4;
  } else if (points >= 100) {
    priority += 3;
  } else if (points >= 50) {
    priority += 2;
  } else {
    priority += 1;
  }

  return priority;
}

export function generateStudyBlocks(
  assignment: SchedulerAssignment
): StudyBlock[] {
  const totalHours = estimateTime(assignment);
  const blocks: StudyBlock[] = [];

  let remainingHours = totalHours;
  let blockNumber = 1;

  while (remainingHours > 0) {
    const blockLength = remainingHours >= 2 ? 2 : remainingHours;

    blocks.push({
      course: assignment.course,
      assignment_name: assignment.assignment_name,
      block_number: blockNumber,
      hours: blockLength,
    });

    remainingHours -= blockLength;
    blockNumber += 1;
  }

  return blocks;
}

export function buildStudyPlan(assignments: SchedulerAssignment[]): StudyBlock[] {
  const assignmentsWithPriority = assignments.map((assignment) => ({
    ...assignment,
    priority: calculatePriority(assignment),
  }));

  const sortedAssignments = assignmentsWithPriority.sort(
    (a, b) => b.priority - a.priority
  );

  let studyPlan: StudyBlock[] = [];

  for (const assignment of sortedAssignments) {
    const blocks = generateStudyBlocks(assignment);
    studyPlan = studyPlan.concat(blocks);
  }

  return studyPlan;
}
def estimate_time(assignment):
    assignment_type = assignment["type"]
    points = assignment["points"]
    difficulty = assignment["difficulty"]

    if assignment_type == "quiz":
        hours = 1.5
    elif assignment_type == "homework":
        hours = 3
    elif assignment_type == "lab":
        hours = 2.5
    elif assignment_type == "essay":
        hours = 6
    elif assignment_type == "project":
        hours = 8
    elif assignment_type == "exam":
        hours = 10
    else:
        hours = 3

    if points >= 200:
        hours += 2
    elif points >= 100:
        hours += 1
    elif points >= 50:
        hours += 0.5

    if difficulty == 2:
        hours += 0.5
    elif difficulty == 3:
        hours += 1
    elif difficulty == 4:
        hours += 2
    elif difficulty == 5:
        hours += 3

    return hours

def calculate_priority(assignment):
    due_in_days = assignment["due_in_days"]
    points = assignment["points"]
    difficulty = assignment["difficulty"]
    estimated_hours = estimate_time(assignment)

    priority = 0

    # Due date urgency
    if due_in_days <= 1:
        priority += 10
    elif due_in_days <= 3:
        priority += 7
    elif due_in_days <= 7:
        priority += 5
    else:
        priority += 2

    # Time needed
    if estimated_hours >= 8:
        priority += 4
    elif estimated_hours >= 5:
        priority += 3
    elif estimated_hours >= 3:
        priority += 2
    else:
        priority += 1

    # Difficulty
    priority += difficulty

    # Points / weight
    if points >= 200:
        priority += 4
    elif points >= 100:
        priority += 3
    elif points >= 50:
        priority += 2
    else:
        priority += 1

    return priority


def generate_study_blocks(assignment):
    total_hours = estimate_time(assignment)
    blocks = []

    remaining_hours = total_hours
    block_number = 1

    while remaining_hours > 0:
        if remaining_hours >= 2:
            block_length = 2
        else:
            block_length = remaining_hours

        blocks.append({
            "course": assignment["course"],
            "assignment_name": assignment["assignment_name"],
            "block_number": block_number,
            "hours": block_length
        })

        remaining_hours -= block_length
        block_number += 1

    return blocks



def build_study_plan(assignments):
    for assignment in assignments:
        assignment["priority"] = calculate_priority(assignment)

    sorted_assignments = sorted(
        assignments,
        key=lambda x: x["priority"],
        reverse=True
    )

    study_plan = []

    for assignment in sorted_assignments:
        blocks = generate_study_blocks(assignment)
        study_plan.extend(blocks)

    return study_plan


def main():
    assignments = [
        {
            "course": "STATS 413",
            "assignment_name": "Homework 6",
            "type": "homework",
            "points": 100,
            "difficulty": 3,
            "due_in_days": 2
        },
        {
            "course": "EECS 281",
            "assignment_name": "Project 2",
            "type": "project",
            "points": 200,
            "difficulty": 5,
            "due_in_days": 5
        },
        {
            "course": "UX 320",
            "assignment_name": "Reflection Essay",
            "type": "essay",
            "points": 50,
            "difficulty": 2,
            "due_in_days": 1
        }
    ]

    study_plan = build_study_plan(assignments)

    print("Study Plan:")
    for block in study_plan:
        print(block)


if __name__ == "__main__":
    main()

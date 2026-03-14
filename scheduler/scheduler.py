def estimate_time(assignment):
    assignment_type = assignment["type"]
    points = assignment["points"]
    difficulty = assignment["difficulty"]

    hours = 0

    # base time by assignment type

    # adjust based on points

    # adjust based on difficulty

    return hours

def calculate_priority(assignment):
    pass

def generate_study_blocks(assignment):
    pass

def build_study_plan(assignments):
    pass


def main():
    assignment = {
        "course": "STATS 413",
        "assignment_name": "Homework 6",
        "type": "homework",
        "points": 100,
        "difficulty": 3
    }

    result = estimate_time(assignment)
    print("Estimated hours:", result)


if __name__ == "__main__":
    main()
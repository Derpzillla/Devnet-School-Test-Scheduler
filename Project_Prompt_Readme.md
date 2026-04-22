# Final Exam Scheduling Project

## Overview

This project is about scheduling university final exams in available rooms while respecting student enrollment, room capacity, and exam timing constraints. Students, classes, and room availability are stored as RDF data, and your scheduler should produce a JSON schedule of exams.

The goal is to create a schedule that:

- Assigns every student to each of their enrolled exams.
- Ensures no student has overlapping exams.
- Ensures no room is double-booked.
- Respects room capacities and availability windows.

## Project Files

- **RDF Data**: Contains students, classes, room capacities, and room availability.
- **Scheduler Script**: Your Python code (or whatever language you choose to use) that generates the exam schedule.
- **Output JSON**: A valid schedule assigning every student to an exam in a specific room, as JSON.

Example output structure:

```json
{
  "group_0001": {
    "students": [
      "http://example.org/_StudentA",
      "http://example.org/_StudentB"
    ],
    "room": {
      "room_iri": "http://example.org/RoomA",
      "time_slot": "2026-05-11T08:00:00 - 2026-05-11T11:00:00"
    },
    "class_iri": "http://example.org/MATH101"
  }
}
```

> Note: `"group_0001"` can be any unique ID. Each group contains the students for a single exam session.

---

## Step-by-Step Instructions

1. **Read the Input Data**

   - Load the RDF graph containing students, classes, and room data.
   - Use `rdflib` (or any language-specific package that can parse RDF) to query student enrollments, room capacities, and available times.

2. **Plan Your Scheduling Algorithm**

   - Compute which students are enrolled in each class.
   - Generate available room slots dynamically.
   - Schedule exams while respecting:

     - Room capacity
     - Student conflicts
     - Room availability

3. **Generate JSON Output**

   - Produce a JSON object where each group represents a scheduled exam.
   - Include the following information:

     - `students`: list of student IRIs (as strings)
     - `room`: room IRI (as string)
     - `time slot`: the specific time slot the exam would start/end at (do **_not_** confuse this with the room's availability time slot)
     - `class`: the class being scheduled

4. **Verify Your Schedule**

_Note: There is a specific JSON format expected of your data for the verification script to run._

- Run verification functions to ensure correctness:

  - `verify_room_capacity`: No room is over capacity.
  - `verify_student_exam_conflicts`: No student has overlapping exams.
  - `verify_all_students_have_all_finals`: Every student is scheduled for all enrolled exams.
  - `verify_exam_room_fit`: Exams fit within the room's availability.
  - `verify_no_room_overlaps`: No room hosts two exams at the same time.
  - `verify_no_student_duplicate_in_class`: No student appears more than once in the same class.
  - `verify_all_student_exams_are_accounted_for`: Check all student exams are included.

5. **Submit Your Work**

   - Include:

     - Python (or whatever language you use) scheduler script(s)
     - Output JSON schedule
     - Optional: README explaining your algorithm and any assumptions

6. **Extra Credit:** Visualize room availability and exam placement

Create a visual representation that shows how exams are placed within each room’s available time windows. The goal is to make it easy to see when rooms are free, when exams are scheduled, and how time is being used.

## Additional Tips

- Start with scheduling the largest classes first to avoid splitting students unnecessarily.
- Always update room availability and student busy times dynamically after assigning each exam.
- Test your schedule on small subsets before generating the full schedule for all students.

# DocBooker flow map

This diagram is a plan for the Botpress workflows and for the Flask state machine. It is not a screenshot of a published bot.

```mermaid
flowchart TD
  startNode([Welcome]) --> menu[Main menu]
  menu --> book[Book appointment]
  menu --> findDoc[Find a doctor]
  menu --> manage[Manage appointment]
  menu --> info[Hospital information]
  menu --> finishNode([Finish])

  book --> consent{Consent to a simulated booking?}
  consent -->|No| menu
  consent -->|Yes| dept[Choose department]
  dept --> doctor[Choose a doctor in that department]
  doctor --> apptDate[Choose a date in the next 14 days]
  apptDate --> apptTime[Choose an exact open time]
  apptTime --> identity[Fictional name and synthetic contact]
  identity --> review{Review: department, doctor, date, time, America/New_York}
  review -->|Edit| dept
  review -->|Cancel, nothing saved| menu
  review -->|Confirm and slot still open| saved[Demo appointment saved. Show reference and management code]
  saved --> menu
  review -->|Slot taken| apptTime

  findDoc --> findDept[Choose department]
  findDept --> results[Doctors, specialties, and seeded open times from the database]
  results -->|Book with this doctor| consent
  results --> menu

  manage --> codes{Reference and management code}
  codes -->|Invalid, generic reply| manage
  codes -->|Valid| action{Reschedule or cancel}
  action --> newSlot[Choose a new open slot]
  newSlot --> moveReview{Confirm the new time}
  moveReview -->|New slot taken: original unchanged| newSlot
  moveReview -->|Confirmed| menu
  moveReview -->|Back| action
  action --> cancelAsk{Confirm cancellation}
  cancelAsk -->|No| action
  cancelAsk -->|Yes, slot freed| menu

  info --> facts[Answer only from the fictional knowledge file]
  facts -->|Missing fact: say so and give reception| menu
  facts --> menu

  emergency([Emergency phrase]) -.-> menu
  medical([Other medical question: no advice]) -.-> menu
```

Emergency phrases interrupt every flow, including an in-progress booking, and return to the menu. The review nodes are gates: Confirm is the only path that writes a booking, and the cancel gate is the only path that frees a slot.

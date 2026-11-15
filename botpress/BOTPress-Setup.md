# Botpress setup for DocBooker

This is a manual setup guide. It does not import a bot, and nothing here has been configured or published in a Botpress account. Botpress Cloud cannot call the localhost Flask app, so this class demo keeps its own simulated doctors and slots inside Botpress.

Official pages checked on November 15, 2026:

- [Studio introduction](https://botpress.com/docs/studio/introduction/)
- [Workflows](https://botpress.com/docs/studio/concepts/workflows/)
- [Nodes](https://botpress.com/docs/studio/concepts/nodes/introduction/)
- [Emulator](https://botpress.com/docs/studio/concepts/emulator/)
- [Knowledge Bases](https://botpress.com/docs/studio/concepts/knowledge-base/introduction/)
- [Capture Information](https://botpress.com/docs/studio/concepts/cards/capture-information/)
- [AI Task](https://botpress.com/docs/studio/concepts/cards/ai/ai-task/)
- [Execute Code](https://botpress.com/docs/studio/concepts/cards/execute-code/)
- [Workflow variables](https://botpress.com/docs/studio/concepts/variables/scopes/workflow/)
- [Variables in code](https://www.botpress.com/docs/studio/concepts/variables/in-code/)
- [Tables](https://www.botpress.com/docs/studio/concepts/tables/)
- [Table cards](https://www.botpress.com/docs/studio/concepts/cards/tables/)

Menu labels in Studio can move. If a label below does not match your screen, follow the documentation page and mark your screenshot with the label you actually used. This guide does not invent an export file you can upload.

## What a workflow is

A workflow is a multi-step service, not one node. Each DocBooker service is its own workflow: several nodes, with an Entry node and an Exit node. The Main workflow greets the person and sends them into one of those workflows. When a service finishes, its Exit returns to Main, which shows the menu again. Finish uses the End node in Main and stops the conversation.

Create these workflows:

1. Main
2. Book Appointment
3. Find a Doctor
4. Manage Appointment
5. Hospital Information
6. Emergency

## Instructions and knowledge

1. Open your bot in Botpress Studio.
2. Paste `docbooker-instructions.md` into the bot instructions or agent instructions field. Confirm the current field name in Studio. The important part is that the text is the bot's standing behavior, not a single node message.
3. Create a Knowledge Base named `Northshore Demo Hospital`. Add `hospital-demo-knowledge.md` as a source. The docs describe this under Knowledge Base → New Knowledge Base, then add a source.
4. Do not put insurance, prices, symptoms, or live doctor schedules in that knowledge base.

## Variables

Workflow variables exist only inside one workflow. Booking details have to survive the jump from Find a Doctor into Book Appointment, so store them where Studio's variable picker shows a conversation scope. The code docs show this shape: `conversation.cartTotal`. Use that scope if the picker still calls it conversation. If the picker uses another name, use the picker name and write it on your diagram.

Suggested variables:

| Variable | Holds |
| --- | --- |
| `department` | One of the five department names |
| `doctorName` | Fictional doctor |
| `slotDate` | Exact date |
| `slotTime` | Exact time such as 9:00 AM |
| `patientName` | Fictional name |
| `contact` | Synthetic phone or email |
| `reference` | Booking reference |
| `managementCode` | Shown once, then used only to find the row |
| `consent` | Yes or no |
| `attempts` | Failed manage attempts |

Do not ask for symptoms, age, date of birth, Social Security number, or insurance.

## Simulated slots

Keep the class demo self-contained.

1. In the explorer, Add Table. The tables doc shows this path and a free-plan limit of 10 tables.
2. Create `Doctors` with string fields `name`, `department`, and `specialty`. Enter the ten fictional doctors from `hospital-demo-knowledge.md`.
3. Create `Slots` with string fields `doctorName`, `slotDate`, `slotTime`, and `status`. Status is `open` or `booked`.
4. Create `Bookings` with `reference`, `managementCode`, `doctorName`, `slotDate`, `slotTime`, `patientName`, `contact`, and `status`.
5. Generate slot rows for the next 14 days from the day you demo, America/New_York. Weekdays: 9:00 AM, 10:30 AM, 1:00 PM, 2:30 PM, 4:00 PM. Saturday: 9:00 AM and 10:30 AM. No Sunday rows. Replace those rows if the demo date moves, so you are not showing expired times. The Flask app does this refresh itself. Botpress tables do not.

The table card doc documents **Insert Record**: add the card, choose the table, and set each field from a variable or a fixed value. Use the same card page for the find and update cards that your Studio version shows. Confirm those labels in the card picker before you rely on them.

A table update in this class bot is a simulation. It is not the same guarantee as the Flask app's SQLite transaction. In the Flask app, a partial unique index makes two confirms fail closed. In Botpress, check that the slot row is still `open` immediately before you mark it `booked`. If it is already booked, show other open times and do not create a second booking. Say that limitation if someone asks whether the Botpress demo is race-proof.

`client.findTableRows` and `client.createTableRows` appear in the current tables docs. Confirm the helpers in the code editor before pasting them. Do not point Execute Code at `http://127.0.0.1:5000`. Botpress Cloud cannot reach that address.

## Main workflow

1. Start node. Leave it as the conversation entrance.
2. Text card: welcome to DocBooker at Northshore Demo Hospital, fictional demo, no medical advice.
3. Capture Information card. Type: **Single Choice**. Variable: a conversation variable such as `menuChoice`. Prompt: the five options below. The capture doc says a typed message can match a button label.
   - Book an appointment
   - Find a doctor
   - Manage an appointment
   - Hospital information
   - Finish
4. Branch on `menuChoice` into the four workflows, or to the End node for Finish.
5. When a child workflow exits, send the person back to the menu node. Finish does not return to the menu.

Also accept the words menu, help, and restart. Help can be a Text card that repeats the four services and returns to the menu node. Restart asks "Discard the in-progress booking?" before it clears variables. Confirm the transition control in the card you use. The docs call these transitions out of a node.

## Book Appointment workflow

This workflow is the whole booking service.

1. Entry node.
2. Text: this creates a simulated booking only. Ask for consent. Capture Information, type **Confirmation** or **Boolean**, into `consent`. No returns to Main and saves nothing.
3. Single Choice for department: General Medicine, Cardiology, Pediatrics, Dermatology, Orthopedics.
4. Execute Code or a table find: keep only doctors whose department matches. Single Choice those names into `doctorName`.
5. Build dates for the next 14 days, skip Sunday, and skip a date that has no open slot for that doctor. Single Choice into `slotDate`. Reject a typed past date or a date outside the window with a Text card and the same choice again.
6. Single Choice of exact open times into `slotTime`. If the person types "morning" or another vague word, say you need an exact time such as 9:00 AM, and ask again.
7. Raw Input for a fictional patient name into `patientName`. The prompt must say not to use a real name. If the text mentions symptoms, a diagnosis, a date of birth, or a Social Security number, refuse and ask again. Do not add those as capture fields.
8. Raw Input for a synthetic phone or email into `contact`, with the example `555-010-0142` or `demo@example.com`.
9. Text review: department, doctor, exact date, exact time, timezone America/New_York, fictional name, synthetic contact. Say nothing is saved yet.
10. Single Choice: Confirm, Edit, Cancel.
    - Edit goes back to the department, doctor, date, time, name, or contact node the person picks.
    - Cancel clears the draft variables and exits to Main. Do not insert a booking row.
    - Confirm checks the slot is still `open`. Only then insert a `Bookings` row and set the slot to `booked`.
11. Generate a reference like `NS-` plus 6 letters and a separate 8-character management code. Show both. Say "Demo appointment saved" and that a real appointment was not created. Say both codes are required later.
12. Exit to Main.

If the slot is taken between the review and confirm, do not overwrite the other booking. Show other open times.

## Find a Doctor workflow

1. Single Choice or a typed department.
2. Read matching doctors from the `Doctors` table and their open rows from `Slots`. Do not let the model invent a doctor or a time.
3. Show name, specialty, and up to three upcoming open slots.
4. Single Choice "Book with {doctor}". Set `department` and `doctorName`, then transition into Book Appointment at the consent step, or at the date step if you already asked consent. Do not skip consent on the first booking.

## Manage Appointment workflow

1. Ask for the booking reference and the management code together.
2. Find a `Bookings` row where both values match and status is active. Use one generic miss message: "Those details do not match an active demo booking." Do not say which field was wrong. Do not search by name or phone.
3. Count misses in `attempts`. After 5, stop and tell the person to restart. Still do not show booking details.
4. On a match, offer Reschedule or Cancel.
5. Reschedule: pick an open slot, show the old time and the new time, and require an explicit confirm. Check the new slot is still open. Only then move the booking and release the old slot. If the new slot is taken, say the original booking is unchanged and show other times.
6. Cancel: show the booking and ask "Yes, cancel it" or "No, keep it". Only the yes path sets status to cancelled and frees the slot. A cancelled row must not appear in a later manage lookup.

## Hospital Information workflow

1. Single Choice: Hours, Address, Phone, Departments, Parking, Main menu.
2. Preferred path: standard nodes with the exact paragraphs from `hospital-demo-knowledge.md`. This keeps the demo from inventing prices or insurance rules.
3. Optional paraphrase, and the only planned use of an AI Task: retrieve the matching approved paragraph first, then an AI Task may rephrase that paragraph in simpler words. Task instructions must say: use only the supplied paragraph, say it is fictional, and do not add insurance, prices, doctors, availability, or medical advice. Store the task output in a variable and show that variable. If the knowledge base has no match, do not call the AI Task. Show the fictional reception number `(555) 010-0199` instead.
4. The Flask app does not do this paraphrase. Its baseline is keyword matching. Do not describe that baseline as generative AI.

The knowledge-base docs say an Autonomous node searches knowledge by default, while a Standard node does not. For this class bot, prefer Standard nodes for booking and for facts that must stay inside the file. If you turn on an Autonomous node, keep the instructions in `docbooker-instructions.md` and do not let it collect medical history.

## Emergency workflow

From every capture step, also check the raw user text against this explicit list before you continue the service:

- chest pain
- heart attack
- stroke
- can't breathe, cannot breathe, difficulty breathing, short of breath, not breathing
- unconscious
- overdose
- suicidal, kill myself, want to die, end my life
- severe bleeding, bleeding heavily
- 911

The incoming text variable has to be confirmed in Studio's variable picker. Do not guess the name if the picker shows a different one.

On a match, transition to the Emergency workflow and clear the unsaved booking draft. Text, exactly this idea:

"If this may be a medical emergency, call 911 in the United States or your local emergency number. DocBooker only schedules simulated appointments and cannot help in an emergency. This check looks for a few explicit phrases only. It is not medical screening."

Then return to Main. For other medical questions, a Text card says the bot cannot give medical advice and points to a licensed clinician and the fictional reception number. Do not name a medicine or a dose.

## Human handoff

Handoff in this prototype is the fictional reception line `(555) 010-0199`. Do not add a live-agent node that pretends a person is waiting.

## Test each path in the emulator

The emulator doc says the panel opens with Ctrl+E or Cmd+E. Conversations there are not saved as production traffic. Use **New Conversation** between tests. **Start as new user** is in the emulator's more menu when you need a second person.

For each path below, capture a screenshot of the emulator and, if the debugger shows it, the node name. These screenshots are your evidence. This markdown file is not evidence that you already ran them.

| Path | Do this | Evidence |
| --- | --- | --- |
| Book success | Consent, department, doctor, exact date and time, fake name, fake contact, review, confirm | Both codes and the words "Demo appointment saved" |
| Edit | Reach review, edit the time, confirm the new time | Review shows the new time |
| Cancel before save | Reach review, choose Cancel | No new bookings row |
| Vague time | Type morning | Bot asks for an exact slot |
| Find | Ask for cardiologists | Only cardiology doctors, with times from the table |
| Book from find | Book with one of those doctors | Department and doctor stay selected |
| Bad codes | Wrong reference or wrong code | Generic miss, no patient name |
| Reschedule conflict | Two bookings, move one onto the other's time | Original time still booked |
| Reschedule success | Move to an open time and confirm | Booking shows the new time |
| Cancel | Confirm cancel, then try the old codes | Slot open, codes no longer manage it |
| Hours | Ask for hours | Text matches the knowledge file |
| Missing fact | Ask about insurance | Refusal plus reception phone, no invented plan |
| Emergency | Type "I have chest pain" during booking | 911 message, draft cleared |
| Medical | Ask what medicine to take | Refusal, no drug name |
| Unknown | Type "purple elephant" | Fallback and the menu |
| Finish | Choose Finish | Conversation ends |
| Restart mid-booking | Restart before confirm | Bot asks before discarding |

Check the table after confirm, cancel, and the conflict path so the screenshots show the rows, not only the chat text.

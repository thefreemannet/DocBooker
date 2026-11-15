# Sample conversations

These are scripts for a manual demo. They are not executed test evidence. They were not run inside Botpress. The Flask automated results are in `TEST-RESULTS.md`.

Times below are examples. Use whatever open slot the demo database shows that day. Timezone is America/New_York.

## Successful booking

User: I want to book a doctor

Bot: This creates a simulated booking only. A real appointment will not be made. Use a made-up name and a fake phone or email. Do you consent to continue?

User: I consent

Bot: Which department should I use?

User: Cardiology

Bot: Fictional doctors in Cardiology: Dr. Helen Cho — Preventive cardiology. Dr. Luis Ortega — Heart rhythm.

User: Dr. Helen Cho

Bot: Choose an available date in the next 14 days.

User: tomorrow

Bot: Open times. Choose an exact time such as 9:00 AM.

User: 9:00 AM

Bot: Enter a fictional patient name. Do not enter real personal information.

User: Jamie Rivera

Bot: Enter a synthetic phone or email, such as 555-010-0142 or demo@example.com.

User: 555-010-0142

Bot: Please review this simulated booking. Nothing is saved until you confirm. Department: Cardiology. Doctor: Dr. Helen Cho. Date: the chosen date. Time: 9:00 AM. Timezone: America/New_York. Fictional patient name: Jamie Rivera. Synthetic contact: 555-010-0142.

User: Confirm

Bot: Demo appointment saved. This is a simulated record only. A real appointment was not created. Booking reference: NS-A1B2C3. Management code: H7K2P9QM. You need both codes to manage this demo booking.

## Correction before save

User reaches the review, then: Edit

Bot: What should I change? Nothing is saved until you confirm the review.

User: Change time

Bot: Open times for that doctor.

User: 10:30 AM

Bot shows the review again with 10:30 AM.

User: Cancel

Bot: No booking was saved.

## Reschedule

User: Can I change my appointment?

Bot: Enter the booking reference and the management code together.

User: NS-A1B2C3 H7K2P9QM

Bot shows the active demo booking and offers Reschedule or Cancel.

User: Reschedule

Bot: Choose an available date.

User picks a new date and 2:30 PM.

Bot: Review this change. The original time stays reserved unless this change succeeds. From: the old time. To: 2:30 PM America/New_York.

User: Confirm new time

Bot: The demo booking now uses the new time. This is still a simulated record.

## Reschedule when the new slot is taken

User confirms a move onto a time that was just reserved.

Bot: That time is no longer open. Your original demo booking is unchanged.

The original time is still theirs.

## Cancellation

User: Cancel my booking

Bot asks for both codes. After a match:

Bot: Cancel this demo booking? The time is freed only after you confirm.

User: No, keep it

Bot: The demo booking is still active.

User: Yes, cancel it

Bot: The demo booking is cancelled and that time is free again. A cancelled booking cannot be rescheduled.

A later attempt with the same codes gets the generic miss in the next script.

## Unknown input

User: purple elephant

Bot: I can help with simulated appointment booking, finding a fictional doctor, managing a demo booking, or hospital information. I did not understand that. Choose a service.

## Invalid credentials

User: NS-A1B2C3 WRONGCODE

Bot: Those details do not match an active demo booking. Check the booking reference and management code and try again.

The bot does not show the patient name, and it does not say whether the reference exists.

## Emergency interruption

User, during department selection: I have chest pain

Bot: If this may be a medical emergency, call 911 in the United States or your local emergency number. DocBooker only schedules simulated appointments and cannot help in an emergency. This check looks for a few explicit phrases only. It is not medical screening, and other wording may not be detected.

The unsaved booking is dropped. The menu returns.

## Medical question

User: What medicine should I take for a fever?

Bot: I cannot provide medical advice, diagnoses, or treatment suggestions. Please talk with a licensed clinician. For fictional hospital questions, reception is listed as (555) 010-0199. This is not a real clinic.

## Hospital information and a missing fact

User: What are your hours?

Bot: Reception hours at Northshore Demo Hospital (fictional demo details): Monday through Friday, 8:00 AM to 5:00 PM, America/New_York. Saturday, 9:00 AM to 1:00 PM. Sunday, closed.

User: Do you accept insurance?

Bot: I don't have that in the fictional hospital information, so I will not guess. Fictional reception phone: (555) 010-0199.

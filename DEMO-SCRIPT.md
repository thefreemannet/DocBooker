# DocBooker demo script

This is a first-person script for a solo five-minute demonstration. It is a speaking script, not test evidence. The checks that were actually run are in `TEST-RESULTS.md`.

## 0:00 – What this is

I built DocBooker for Northshore Demo Hospital. The hospital, the doctors, and the appointments are fictional. The banner on the screen says this is a classroom simulation. I do not enter real names, real phone numbers, symptoms, or payment information. The bot does not diagnose anyone, and I am not claiming it is HIPAA compliant or ready for a real clinic.

The local version is a Flask app with a SQLite database. The Botpress version is a setup guide I still have to click through in Botpress Studio. A custom app does not replace that Botpress requirement.

## 0:40 – Book a demo appointment

I choose Book an appointment. The bot says this is simulated and asks for consent. I consent.

I choose Cardiology, then Dr. Helen Cho. I pick a date in the next 14 days and an exact time, such as 9:00 AM. I do not type "morning," because the bot only accepts a concrete slot.

For the patient I type Jamie Rivera. For contact I type 555-010-0142. The bot told me both of those should be fake.

## 2:10 – Recovery: fix the review before anything is saved

The review shows the department, doctor, date, time, and America/New_York. Nothing is in the database yet. I choose Edit, change the time, and come back to the review. If I chose Cancel instead, no row would be saved. I confirm only after the review looks right.

## 3:10 – Two codes

The bot says "Demo appointment saved" and shows a booking reference and a management code. I say clearly that both are required later, that this is not a real appointment, and that the code is not stored in the browser. I leave both codes visible long enough to read them, or I write them on a note for the next step.

## 3:50 – One more check, if time remains

I type "What are your hours?" and point out that the answer comes from the fictional hospital file. If I still have half a minute, I type "What medicine should I take for a fever?" and show the refusal, or I type "I have chest pain" and show the 911 interruption. I say that the emergency check is a short phrase list, not medical screening.

## 4:30 – Close

I point to `botpress/BOTPress-Setup.md` and say that the same four flows — book, find a doctor, manage, and hospital information, plus Finish — still need to be built in Botpress from that guide. The keyword matcher in this Flask app is the no-key baseline. It is not generative AI. An AI Task in Botpress is only suggested for paraphrasing approved hospital information, not for booking decisions or medical advice.

"""Conversation state machine for the four service flows."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from . import db, knowledge, nlp, safety
from .timeutil import TZ, format_date, format_stamp, format_time, hospital_now

BOOKING_STATES = {
    "book_consent",
    "book_department",
    "book_doctor",
    "book_date",
    "book_time",
    "book_name",
    "book_contact",
    "book_review",
    "book_edit",
}
CHANGE_STATES = {
    "manage_date",
    "manage_time",
    "manage_review",
    "manage_cancel_confirm",
}
IN_PROGRESS = BOOKING_STATES | CHANGE_STATES | {"discard_confirm"}
MAX_AUTH_FAILURES = 5

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,59}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+().\-\s]{7,20}$")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SENSITIVE_RE = re.compile(
    r"\b(ssn|social security|symptom|symptoms|diagnosis|insurance|date of birth|dob)\b",
    re.IGNORECASE,
)
VAGUE_TIMES = {"morning", "afternoon", "evening", "night", "noon", "later", "sometime"}
YES_WORDS = {"yes", "y", "yeah", "yep", "confirm", "i consent", "i agree", "agree", "consent"}
NO_WORDS = {"no", "n", "nope"}

HELP_TEXT = (
    "You can type or use the buttons. Say menu, help, or restart at any time. "
    "I book simulated appointments only. I do not take symptoms, insurance, payment, "
    "age, date of birth, or real personal details."
)
PRIVACY_TEXT = (
    "Use a made-up name and a fake phone or email. Do not enter real personal, "
    "medical, or payment information."
)
MENU_BUTTONS = (
    {"id": "menu:book", "label": "Book an appointment"},
    {"id": "menu:find", "label": "Find a doctor"},
    {"id": "menu:manage", "label": "Manage an appointment"},
    {"id": "menu:info", "label": "Hospital information"},
    {"id": "menu:finish", "label": "Finish"},
)
GREETING = (
    "Hello. I am DocBooker for Northshore Demo Hospital.",
    "This is a classroom simulation with fictional doctors and appointments. "
    "I can book a demo appointment, find a doctor, manage a demo booking, or share "
    "fictional hospital information. I cannot give medical advice.",
    "Choose a service.",
)


def load_conversation(conn, session_id: str) -> dict:
    row = conn.execute(
        "SELECT state, data_json FROM conversations WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return {"state": "menu", "data": {}}
    return {"state": row["state"], "data": json.loads(row["data_json"])}


def save_conversation(conn, session_id: str, conv: dict, now: datetime) -> None:
    if "management_code" in conv["data"]:
        raise RuntimeError("management code must not be stored in conversation state")
    payload = json.dumps(conv["data"], separators=(",", ":"))
    conn.execute(
        """
        INSERT INTO conversations (session_id, state, data_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            state = excluded.state,
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """,
        (session_id, conv["state"], payload, now.astimezone(TZ).isoformat()),
    )


def opening(conn, conv: dict, now: datetime | None = None) -> dict:
    now = now or hospital_now()
    if not conv["data"].get("greeted"):
        conv["data"]["greeted"] = True
        conv["state"] = "menu"
        return _pack(conv, list(GREETING), list(MENU_BUTTONS), now)
    texts, buttons = _view(conn, conv, now)
    return _pack(conv, texts, buttons, now)


def handle_turn(conn, conv: dict, message: str, button: str, sections: dict, now=None) -> dict:
    now = now or hospital_now()
    message = (message or "").strip()
    button = (button or "").strip()
    if len(message) > 500:
        message = message[:500]

    if message and safety.is_emergency(message):
        _clear_draft(conv, keep_failures=True)
        conv["state"] = "menu"
        return _pack(conv, [safety.EMERGENCY_TEXT, "Choose a service."], list(MENU_BUTTONS), now)

    if message and not button and safety.is_medical(message):
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [safety.MEDICAL_TEXT, *texts], buttons, now)

    if button == "help" or (not button and nlp.is_command(message, "help")):
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [HELP_TEXT, *texts], buttons, now)

    if button == "restart" or (not button and nlp.is_command(message, "restart")):
        return _begin_exit(conn, conv, "restart", now)

    if button == "nav:menu" or (not button and nlp.is_command(message, "menu")):
        return _begin_exit(conn, conv, "menu", now)

    if button == "menu:finish" or (not button and nlp.is_finish(message)):
        return _begin_exit(conn, conv, "finish", now)

    handler = {
        "menu": _menu,
        "finished": _menu,
        "discard_confirm": _discard,
        "book_consent": _consent,
        "book_department": _department,
        "book_doctor": _doctor,
        "book_date": _date,
        "book_time": _time,
        "book_name": _name,
        "book_contact": _contact,
        "book_review": _review,
        "book_edit": _edit,
        "find_department": _find_department,
        "find_results": _find_results,
        "manage_auth": _manage_auth,
        "manage_actions": _manage_actions,
        "manage_date": _manage_date,
        "manage_time": _manage_time,
        "manage_review": _manage_review,
        "manage_cancel_confirm": _manage_cancel,
        "info": _info,
    }.get(conv["state"], _menu)
    return handler(conn, conv, message, button, sections, now)


def _menu(conn, conv, message, button, sections, now):
    intent = nlp.Intent("unknown") if button else nlp.detect_intent(message)
    if button == "menu:book" or intent.name == "book":
        department = None if button else intent.department
        return _start_book(conv, now, department=department)
    if button == "menu:find" or intent.name == "find":
        if intent.department:
            conv["data"]["department"] = intent.department
            conv["state"] = "find_results"
            return _pack_view(conn, conv, now)
        conv["state"] = "find_department"
        return _pack_view(conn, conv, now)
    if button == "menu:manage" or intent.name == "manage":
        conv["state"] = "manage_auth"
        conv["data"].pop("pending_reference", None)
        conv["data"].pop("booking_id", None)
        return _pack_view(conn, conv, now)
    if button == "menu:info" or intent.name == "info":
        conv["state"] = "info"
        if button == "menu:info" or not message:
            return _pack_view(conn, conv, now)
        answer = knowledge.answer_question(message, sections)
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [answer, *texts], buttons, now)
    if button.startswith("dept:") or button.startswith("doctor:") or button.startswith("findbook:"):
        return _unexpected(conn, conv, now)
    if not button and re.search(r"\b(insurance|price|prices|cost|payment)\b", message.lower()):
        conv["state"] = "info"
        answer = knowledge.answer_question(message, sections)
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [answer, *texts], buttons, now)
    return _pack(
        conv,
        [
            "I can help with simulated appointment booking, finding a fictional doctor, "
            "managing a demo booking, or hospital information. I did not understand that.",
            "Choose a service.",
        ],
        list(MENU_BUTTONS),
        now,
    )


def _start_book(conv, now, doctor_id=None, department=None):
    failures = conv["data"].get("auth_failures", 0)
    conv["data"] = {"greeted": True, "auth_failures": failures}
    if department:
        conv["data"]["department"] = department
    if doctor_id:
        conv["data"]["doctor_id"] = doctor_id
    conv["state"] = "book_consent"
    return _pack_view(None, conv, now)


def _consent(conn, conv, message, button, sections, now):
    if button == "consent:yes" or _word(message) in YES_WORDS:
        if conv["data"].get("doctor_id"):
            conv["state"] = "book_date"
        elif conv["data"].get("department"):
            conv["state"] = "book_doctor"
        else:
            conv["state"] = "book_department"
        return _pack_view(conn, conv, now)
    if button == "consent:no" or _word(message) in NO_WORDS:
        _clear_draft(conv, keep_failures=True)
        conv["state"] = "menu"
        return _pack(
            conv,
            ["No booking was started.", "Choose a service."],
            list(MENU_BUTTONS),
            now,
        )
    return _pack_view(conn, conv, now, lead="Say yes if you consent to a simulated booking, or no to stop.")


def _department(conn, conv, message, button, sections, now):
    name = _department_choice(button, message)
    if not name:
        return _pack_view(conn, conv, now, lead="Choose one of the five fictional departments.")
    conv["data"]["department"] = name
    conv["data"].pop("doctor_id", None)
    conv["data"].pop("date", None)
    conv["data"].pop("slot_id", None)
    conv["state"] = "book_doctor"
    return _pack_view(conn, conv, now)


def _doctor(conn, conv, message, button, sections, now):
    doctor = _doctor_choice(conn, conv["data"].get("department"), button, message)
    if doctor == "ambiguous":
        return _pack_view(conn, conv, now, lead="More than one doctor matches. Choose a button.")
    if not doctor:
        return _pack_view(conn, conv, now, lead="Choose a doctor from this department.")
    conv["data"]["doctor_id"] = doctor["id"]
    conv["data"].pop("date", None)
    conv["data"].pop("slot_id", None)
    conv["state"] = "book_date"
    return _pack_view(conn, conv, now)


def _date(conn, conv, message, button, sections, now):
    day, error = _date_choice(conn, conv["data"].get("doctor_id"), button, message, now)
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["date"] = day.isoformat()
    conv["data"].pop("slot_id", None)
    conv["state"] = "book_time"
    return _pack_view(conn, conv, now)


def _time(conn, conv, message, button, sections, now):
    slot, error = _slot_choice(conn, conv, button, message, now)
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["slot_id"] = slot["id"]
    if conv["data"].get("patient_name") and conv["data"].get("contact"):
        conv["state"] = "book_review"
    else:
        conv["state"] = "book_name"
    return _pack_view(conn, conv, now)


def _name(conn, conv, message, button, sections, now):
    if button:
        return _unexpected(conn, conv, now)
    error = _validate_name(message)
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["patient_name"] = _clean(message)
    conv["state"] = "book_contact"
    return _pack_view(conn, conv, now)


def _contact(conn, conv, message, button, sections, now):
    if button:
        return _unexpected(conn, conv, now)
    error = _validate_contact(message)
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["contact"] = _clean(message)
    conv["state"] = "book_review"
    return _pack_view(conn, conv, now)


def _review(conn, conv, message, button, sections, now):
    choice = button or _word(message)
    if choice in {"review:confirm", "confirm"} or _word(message) in YES_WORDS:
        return _confirm_new(conn, conv, now)
    if choice in {"review:edit", "edit"}:
        conv["state"] = "book_edit"
        return _pack_view(conn, conv, now)
    if choice in {"review:cancel", "cancel"}:
        _clear_draft(conv, keep_failures=True)
        conv["state"] = "menu"
        return _pack(
            conv,
            ["No booking was saved.", "Choose a service."],
            list(MENU_BUTTONS),
            now,
        )
    return _pack_view(conn, conv, now, lead="Choose Confirm, Edit, or Cancel. Nothing is saved yet.")


def _edit(conn, conv, message, button, sections, now):
    target = button
    if not target:
        lowered = _word(message)
        target = {
            "department": "edit:department",
            "doctor": "edit:doctor",
            "date": "edit:date",
            "time": "edit:time",
            "name": "edit:name",
            "contact": "edit:contact",
            "back": "edit:back",
        }.get(lowered, "")
    if target == "edit:back":
        conv["state"] = "book_review"
        return _pack_view(conn, conv, now)
    mapping = {
        "edit:department": "book_department",
        "edit:doctor": "book_doctor",
        "edit:date": "book_date",
        "edit:time": "book_time",
        "edit:name": "book_name",
        "edit:contact": "book_contact",
    }
    if target not in mapping:
        return _pack_view(conn, conv, now, lead="Choose which part of the simulated booking to change.")
    if target == "edit:department":
        conv["data"].pop("doctor_id", None)
        conv["data"].pop("date", None)
        conv["data"].pop("slot_id", None)
    elif target == "edit:doctor":
        conv["data"].pop("date", None)
        conv["data"].pop("slot_id", None)
    elif target == "edit:date":
        conv["data"].pop("slot_id", None)
    elif target == "edit:time":
        conv["data"].pop("slot_id", None)
    conv["state"] = mapping[target]
    return _pack_view(conn, conv, now)


def _find_department(conn, conv, message, button, sections, now):
    name = _department_choice(button, message)
    if not name:
        return _pack_view(conn, conv, now, lead="Choose a department to see its fictional doctors.")
    conv["data"]["department"] = name
    conv["state"] = "find_results"
    return _pack_view(conn, conv, now)


def _find_results(conn, conv, message, button, sections, now):
    if button.startswith("findbook:"):
        doctor = db.get_doctor(conn, _int_suffix(button))
        if doctor is None:
            return _unexpected(conn, conv, now)
        return _start_book(conv, now, doctor_id=doctor["id"], department=doctor["department"])
    if button.startswith("dept:") or nlp.department_in_text(message):
        return _find_department(conn, conv, message, button, sections, now)
    return _pack_view(conn, conv, now, lead="Choose a doctor to book, or pick another department.")


def _manage_auth(conn, conv, message, button, sections, now):
    if conv["data"].get("auth_failures", 0) >= MAX_AUTH_FAILURES:
        return _pack(
            conv,
            [
                "Too many unsuccessful attempts in this conversation. "
                "Use restart before trying again. I cannot show booking details."
            ],
            list(MENU_BUTTONS),
            now,
        )
    reference, code = _split_credentials(message, conv)
    if not reference or not code:
        if reference and not code:
            conv["data"]["pending_reference"] = reference
            return _pack(
                conv,
                ["Enter the management code that was shown when the demo booking was saved."],
                [{"id": "nav:menu", "label": "Main menu"}],
                now,
            )
        conv["data"].pop("pending_reference", None)
        return _pack_view(conn, conv, now, lead="Enter both codes together, for example NS-A1B2C3 and the management code.")
    booking = db.verify_booking(conn, reference, code)
    conv["data"].pop("pending_reference", None)
    if booking is None:
        conv["data"]["auth_failures"] = conv["data"].get("auth_failures", 0) + 1
        return _pack(
            conv,
            [
                "Those details do not match an active demo booking. "
                "Check the booking reference and management code and try again."
            ],
            [{"id": "nav:menu", "label": "Main menu"}],
            now,
        )
    conv["data"]["auth_failures"] = 0
    conv["data"]["booking_id"] = booking["id"]
    conv["state"] = "manage_actions"
    return _pack_view(conn, conv, now, lead="Those codes match an active demo booking.")


def _manage_actions(conn, conv, message, button, sections, now):
    choice = button
    if not choice:
        lowered = message.lower()
        if "resched" in lowered or "change" in lowered:
            choice = "manage:reschedule"
        elif "cancel" in lowered:
            choice = "manage:cancel"
    if choice == "manage:reschedule":
        conv["state"] = "manage_date"
        return _pack_view(conn, conv, now)
    if choice == "manage:cancel":
        conv["state"] = "manage_cancel_confirm"
        return _pack_view(conn, conv, now)
    return _pack_view(conn, conv, now, lead="Choose Reschedule or Cancel.")


def _manage_date(conn, conv, message, button, sections, now):
    booking = _active_managed(conn, conv)
    if booking is None:
        return _lost_booking(conv, now)
    day, error = _date_choice(conn, booking["doctor_id"], button, message, now)
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["date"] = day.isoformat()
    conv["data"].pop("slot_id", None)
    conv["state"] = "manage_time"
    return _pack_view(conn, conv, now)


def _manage_time(conn, conv, message, button, sections, now):
    booking = _active_managed(conn, conv)
    if booking is None:
        return _lost_booking(conv, now)
    slot, error = _slot_choice(conn, conv, button, message, now, doctor_id=booking["doctor_id"], skip_slot=booking["slot_id"])
    if error:
        return _pack_view(conn, conv, now, lead=error)
    conv["data"]["slot_id"] = slot["id"]
    conv["state"] = "manage_review"
    return _pack_view(conn, conv, now)


def _manage_review(conn, conv, message, button, sections, now):
    choice = button or _word(message)
    if choice in {"resched:confirm", "confirm"} or _word(message) in YES_WORDS:
        return _confirm_reschedule(conn, conv, now)
    if choice in {"resched:back", "back"}:
        conv["state"] = "manage_actions"
        conv["data"].pop("slot_id", None)
        conv["data"].pop("date", None)
        return _pack_view(conn, conv, now)
    return _pack_view(conn, conv, now, lead="Confirm the new time, or go back. The original slot stays reserved until a change succeeds.")


def _manage_cancel(conn, conv, message, button, sections, now):
    choice = button or _word(message)
    if choice in {"cancel:yes", "yes"} or _word(message) in YES_WORDS:
        booking = _active_managed(conn, conv)
        if booking is None:
            return _lost_booking(conv, now)
        db.cancel_booking(conn, booking["id"])
        _clear_draft(conv, keep_failures=True)
        conv["state"] = "menu"
        return _pack(
            conv,
            [
                "The demo booking is cancelled and that time is free again. "
                "A cancelled booking cannot be rescheduled.",
                "Choose a service.",
            ],
            list(MENU_BUTTONS),
            now,
        )
    if choice in {"cancel:no", "no"} or _word(message) in NO_WORDS:
        conv["state"] = "manage_actions"
        return _pack_view(conn, conv, now, lead="The demo booking is still active.")
    return _pack_view(conn, conv, now, lead="Confirm cancellation, or keep the demo booking.")


def _info(conn, conv, message, button, sections, now):
    prompts = {
        "info:hours": "What are your hours?",
        "info:address": "What is your address?",
        "info:phone": "What is your phone?",
        "info:departments": "What departments do you have?",
        "info:parking": "Where is parking?",
    }
    if button in prompts:
        message = prompts[button]
    elif button:
        return _unexpected(conn, conv, now)
    elif not message:
        return _pack_view(conn, conv, now)
    intent = nlp.detect_intent(message)
    if intent.name == "find":
        if intent.department:
            conv["data"]["department"] = intent.department
            conv["state"] = "find_results"
            return _pack_view(conn, conv, now)
        conv["state"] = "find_department"
        return _pack_view(conn, conv, now)
    if intent.name == "book":
        return _start_book(conv, now)
    answer = knowledge.answer_question(message, sections)
    texts, buttons = _view(conn, conv, now)
    return _pack(conv, [answer, *texts], buttons, now)


def _discard(conn, conv, message, button, sections, now):
    if button == "discard:yes" or _word(message) in YES_WORDS:
        destination = conv["data"].get("discard_to", "menu")
        return _go(conv, destination, now)
    if button == "discard:no" or _word(message) in NO_WORDS:
        conv["state"] = conv["data"].pop("resume_state", "menu")
        conv["data"].pop("discard_to", None)
        return _pack_view(conn, conv, now, lead="Continuing where you left off.")
    return _pack_view(conn, conv, now, lead="Choose Discard it or Keep going.")


def _confirm_new(conn, conv, now):
    data = conv["data"]
    required = ("doctor_id", "slot_id", "patient_name", "contact")
    if any(not data.get(key) for key in required):
        conv["state"] = "book_department"
        return _pack_view(conn, conv, now, lead="Some booking details are missing, so nothing was saved.")
    try:
        saved = db.create_booking(
            conn,
            doctor_id=int(data["doctor_id"]),
            slot_id=int(data["slot_id"]),
            patient_name=data["patient_name"],
            contact=data["contact"],
            now=now,
        )
    except db.SlotTaken:
        alternatives = _alternative_slots(conn, int(data["doctor_id"]), now)
        conv["state"] = "book_time"
        conv["data"].pop("slot_id", None)
        texts, buttons = _view(conn, conv, now)
        return _pack(
            conv,
            [
                "That time was just reserved by another demo booking, so I did not save a second one. "
                "Your review was not stored. Choose a different open time.",
                *texts,
            ],
            buttons or _slot_buttons(alternatives),
            now,
        )
    except db.ValidationError as exc:
        conv["data"].pop("slot_id", None)
        conv["state"] = "book_date"
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [str(exc), *texts], buttons, now)
    code = saved["management_code"]
    reference = saved["reference"]
    _clear_draft(conv, keep_failures=True)
    conv["state"] = "menu"
    return _pack(
        conv,
        [
            "Demo appointment saved. This is a simulated record only. A real appointment was not created.",
            f"Booking reference: {reference}",
            f"Management code: {code}",
            "You need both codes to manage this demo booking. Save them now. "
            "The management code is not kept in this browser.",
            "Choose a service.",
        ],
        list(MENU_BUTTONS),
        now,
    )


def _confirm_reschedule(conn, conv, now):
    booking = _active_managed(conn, conv)
    if booking is None:
        return _lost_booking(conv, now)
    new_slot = conv["data"].get("slot_id")
    if not new_slot:
        conv["state"] = "manage_date"
        return _pack_view(conn, conv, now, lead="Choose a new time first. The original booking was not changed.")
    try:
        db.reschedule_booking(conn, int(booking["id"]), int(new_slot), now)
    except db.SlotTaken:
        conv["data"].pop("slot_id", None)
        conv["state"] = "manage_time"
        texts, buttons = _view(conn, conv, now)
        return _pack(
            conv,
            ["That time is no longer open. Your original demo booking is unchanged.", *texts],
            buttons,
            now,
        )
    except db.ValidationError as exc:
        texts, buttons = _view(conn, conv, now)
        return _pack(conv, [str(exc), *texts], buttons, now)
    conv["data"].pop("slot_id", None)
    conv["data"].pop("date", None)
    conv["state"] = "manage_actions"
    return _pack_view(conn, conv, now, lead="The demo booking now uses the new time. This is still a simulated record.")


def _begin_exit(conn, conv, destination: str, now: datetime):
    if conv["state"] in IN_PROGRESS:
        if conv["state"] != "discard_confirm":
            conv["data"]["resume_state"] = conv["state"]
        conv["data"]["discard_to"] = destination
        conv["state"] = "discard_confirm"
        return _pack_view(conn, conv, now)
    return _go(conv, destination, now)


def _go(conv, destination: str, now: datetime):
    if destination == "restart":
        conv["state"] = "menu"
        conv["data"] = {}
        return _pack(conv, list(GREETING), list(MENU_BUTTONS), now)
    if destination == "finish":
        conv["state"] = "finished"
        conv["data"] = {"greeted": True, "auth_failures": 0}
        return _pack(
            conv,
            [
                "This demo conversation is finished. Nothing further will be booked unless you start again."
            ],
            [{"id": "restart", "label": "Start again"}],
            now,
        )
    failures = conv["data"].get("auth_failures", 0)
    conv["state"] = "menu"
    conv["data"] = {"greeted": True, "auth_failures": failures}
    return _pack(conv, ["Choose a service."], list(MENU_BUTTONS), now)


def _view(conn, conv, now: datetime):
    state = conv["state"]
    data = conv["data"]
    if state in {"menu", "finished"}:
        if state == "finished":
            return (
                ["This demo conversation is finished."],
                [{"id": "restart", "label": "Start again"}],
            )
        return (["Choose a service."], list(MENU_BUTTONS))
    if state == "discard_confirm":
        if data.get("resume_state") in CHANGE_STATES:
            text = (
                "You have a reschedule or cancellation in progress. "
                "The original demo booking stays as it is until you confirm a change. Discard this step?"
            )
        else:
            text = "You have an in-progress booking that has not been saved. Discard it?"
        return (
            [text],
            [
                {"id": "discard:yes", "label": "Discard it"},
                {"id": "discard:no", "label": "Keep going"},
            ],
        )
    if state == "book_consent":
        return (
            [
                "This creates a simulated booking only. A real appointment will not be made. "
                f"{PRIVACY_TEXT} Do you consent to continue?"
            ],
            [
                {"id": "consent:yes", "label": "I consent"},
                {"id": "consent:no", "label": "Cancel"},
            ],
        )
    if state == "book_department" or state == "find_department":
        lead = "Which department should I use?"
        return ([lead], _department_buttons())
    if state == "book_doctor":
        doctors = db.list_doctors(conn, data.get("department", ""))
        lines = [f"Fictional doctors in {data.get('department')}:"]
        buttons = []
        for doctor in doctors:
            lines.append(f"{doctor['name']} — {doctor['specialty']}")
            buttons.append({"id": f"doctor:{doctor['id']}", "label": doctor["name"]})
        return (lines, buttons)
    if state == "book_date" or state == "manage_date":
        doctor_id = data.get("doctor_id")
        if state == "manage_date":
            booking = _active_managed(conn, conv)
            doctor_id = booking["doctor_id"] if booking else None
        slots = db.open_slots(conn, int(doctor_id), now) if doctor_id else []
        days = []
        seen = set()
        for slot in slots:
            moment = _moment(slot["starts_at"])
            if moment.date() in seen:
                continue
            seen.add(moment.date())
            days.append(moment)
        if not days:
            return (["There are no open dates in the next 14 days for that doctor."], [{"id": "nav:menu", "label": "Main menu"}])
        buttons = [
            {"id": f"date:{item.date().isoformat()}", "label": item.strftime("%a, %b %d").replace(" 0", " ")}
            for item in days
        ]
        return (
            ["Choose an available date in the next 14 days. You can also type a date such as tomorrow. Times use America/New_York."],
            buttons,
        )
    if state in {"book_time", "manage_time"}:
        doctor_id = data.get("doctor_id")
        skip = None
        if state == "manage_time":
            booking = _active_managed(conn, conv)
            if booking is None:
                return (["That demo booking is no longer active."], list(MENU_BUTTONS))
            doctor_id = booking["doctor_id"]
            skip = booking["slot_id"]
        day = datetime.fromisoformat(data["date"]).date() if data.get("date") else None
        slots = db.open_slots(conn, int(doctor_id), now, day) if doctor_id and day else []
        slots = [slot for slot in slots if slot["id"] != skip]
        if not slots:
            return (
                ["That date has no open exact times. Choose another date. I cannot book a vague time such as morning."],
                [{"id": "nav:menu", "label": "Main menu"}],
            )
        lines = ["Open times for that doctor. Choose an exact time such as 9:00 AM."]
        return (lines, _slot_buttons(slots))
    if state == "book_name":
        return (
            [f"Enter a fictional patient name. {PRIVACY_TEXT} I will not ask for symptoms, age, or a Social Security number."],
            [],
        )
    if state == "book_contact":
        return (
            [
                "Enter a synthetic phone or email, such as 555-010-0142 or demo@example.com. "
                "Do not enter a real contact number."
            ],
            [],
        )
    if state == "book_review":
        return ([_review_text(conn, data)], [
            {"id": "review:confirm", "label": "Confirm"},
            {"id": "review:edit", "label": "Edit"},
            {"id": "review:cancel", "label": "Cancel"},
        ])
    if state == "book_edit":
        return (
            ["What should I change? Nothing is saved until you confirm the review."],
            [
                {"id": "edit:department", "label": "Change department"},
                {"id": "edit:doctor", "label": "Change doctor"},
                {"id": "edit:date", "label": "Change date"},
                {"id": "edit:time", "label": "Change time"},
                {"id": "edit:name", "label": "Change name"},
                {"id": "edit:contact", "label": "Change contact"},
                {"id": "edit:back", "label": "Back to review"},
            ],
        )
    if state == "find_results":
        doctors = db.list_doctors(conn, data.get("department", ""))
        lines = [f"Fictional doctors in {data.get('department')}. Availability is read from the demo database."]
        buttons = []
        for doctor in doctors:
            upcoming = db.open_slots(conn, doctor["id"], now)[:3]
            slot_bits = []
            for slot in upcoming:
                moment = _moment(slot["starts_at"])
                slot_bits.append(f"{format_date(moment)} at {format_time(moment)}")
            shown = "; ".join(slot_bits) if slot_bits else "No open times in the next 14 days"
            lines.append(f"{doctor['name']} — {doctor['specialty']}. Next open: {shown}.")
            buttons.append({"id": f"findbook:{doctor['id']}", "label": f"Book with {doctor['name']}"})
        buttons.append({"id": "nav:menu", "label": "Main menu"})
        return (lines, buttons)
    if state == "manage_auth":
        return (
            [
                "Enter the booking reference and the management code together. "
                "A name or phone number alone cannot open a booking."
            ],
            [{"id": "nav:menu", "label": "Main menu"}],
        )
    if state == "manage_actions":
        booking = _active_managed(conn, conv)
        if booking is None:
            return (["That demo booking is no longer active."], list(MENU_BUTTONS))
        return (
            [_booking_summary(conn, booking), "Choose Reschedule or Cancel."],
            [
                {"id": "manage:reschedule", "label": "Reschedule"},
                {"id": "manage:cancel", "label": "Cancel booking"},
                {"id": "nav:menu", "label": "Main menu"},
            ],
        )
    if state == "manage_review":
        booking = _active_managed(conn, conv)
        slot = db.get_slot(conn, int(data.get("slot_id") or 0))
        if booking is None or slot is None:
            return (["Choose a new open time first."], [{"id": "nav:menu", "label": "Main menu"}])
        current = _moment(db.get_slot(conn, booking["slot_id"])["starts_at"])
        new_moment = _moment(slot["starts_at"])
        return (
            [
                "Review this change. The original time stays reserved unless this change succeeds.",
                f"From: {format_date(current)} at {format_time(current)} America/New_York",
                f"To: {format_date(new_moment)} at {format_time(new_moment)} America/New_York",
            ],
            [
                {"id": "resched:confirm", "label": "Confirm new time"},
                {"id": "resched:back", "label": "Back"},
            ],
        )
    if state == "manage_cancel_confirm":
        booking = _active_managed(conn, conv)
        if booking is None:
            return (["That demo booking is no longer active."], list(MENU_BUTTONS))
        return (
            [
                _booking_summary(conn, booking),
                "Cancel this demo booking? The time is freed only after you confirm.",
            ],
            [
                {"id": "cancel:yes", "label": "Yes, cancel it"},
                {"id": "cancel:no", "label": "No, keep it"},
            ],
        )
    if state == "info":
        return (
            ["Ask about fictional reception hours, the demo address, phone, departments, or parking. I answer only from the local demo file."],
            [
                {"id": "info:hours", "label": "Hours"},
                {"id": "info:address", "label": "Address"},
                {"id": "info:phone", "label": "Phone"},
                {"id": "info:departments", "label": "Departments"},
                {"id": "info:parking", "label": "Parking"},
                {"id": "nav:menu", "label": "Main menu"},
            ],
        )
    return (["Choose a service."], list(MENU_BUTTONS))


def _review_text(conn, data: dict) -> str:
    doctor = db.get_doctor(conn, int(data["doctor_id"]))
    slot = db.get_slot(conn, int(data["slot_id"]))
    moment = _moment(slot["starts_at"])
    return "\n".join(
        [
            "Please review this simulated booking. Nothing is saved until you confirm.",
            f"Department: {doctor['department']}",
            f"Doctor: {doctor['name']}",
            f"Date: {format_date(moment)}",
            f"Time: {format_time(moment)}",
            "Timezone: America/New_York",
            f"Fictional patient name: {data['patient_name']}",
            f"Synthetic contact: {data['contact']}",
        ]
    )


def _booking_summary(conn, booking) -> str:
    doctor = db.get_doctor(conn, booking["doctor_id"])
    slot = db.get_slot(conn, booking["slot_id"])
    moment = _moment(slot["starts_at"])
    return "\n".join(
        [
            f"Reference: {booking['reference']}",
            f"Fictional patient: {booking['patient_name']}",
            f"Department: {doctor['department']}",
            f"Doctor: {doctor['name']}",
            f"Date: {format_date(moment)}",
            f"Time: {format_time(moment)}",
            "Timezone: America/New_York",
            f"Status: {booking['status']}",
        ]
    )


def _department_buttons():
    buttons = [{"id": f"dept:{name}", "label": name} for name in nlp.DEPARTMENTS]
    buttons.append({"id": "nav:menu", "label": "Main menu"})
    return buttons


def _department_choice(button: str, message: str):
    if button.startswith("dept:"):
        name = button.split(":", 1)[1]
        return name if name in nlp.DEPARTMENTS else None
    return nlp.department_in_text(message)


def _doctor_choice(conn, department: str, button: str, message: str):
    if button.startswith("doctor:"):
        doctor = db.get_doctor(conn, _int_suffix(button))
        if doctor is None or doctor["department"] != department:
            return None
        return doctor
    if not message:
        return None
    doctors = db.list_doctors(conn, department or "")
    lowered = message.lower()
    matches = [
        doctor
        for doctor in doctors
        if doctor["name"].lower() in lowered or doctor["name"].split()[-1].lower() in lowered.split()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return "ambiguous"
    return None


def _date_choice(conn, doctor_id, button: str, message: str, now: datetime):
    if not doctor_id:
        return None, "Choose a doctor before choosing a date."
    if button.startswith("date:"):
        raw = button.split(":", 1)[1]
        try:
            day = datetime.fromisoformat(raw).date()
        except ValueError:
            return None, "That date is not valid."
    else:
        day = _parse_date(message, now)
        if day is None:
            return None, "I need a specific calendar date within the next 14 days, such as tomorrow or 2026-11-20."
    today = now.astimezone(TZ).date()
    if day < today:
        return None, "That date is in the past. Choose a date within the next 14 days."
    if day > today + timedelta(days=13):
        return None, "I can only book dates within the next 14 days."
    if day.weekday() == 6:
        return None, "Sunday is closed at this fictional demo hospital. Choose another date."
    slots = db.open_slots(conn, int(doctor_id), now, day)
    if not slots:
        return None, "That date has no open times for this doctor."
    return day, None


def _slot_choice(conn, conv, button: str, message: str, now: datetime, doctor_id=None, skip_slot=None):
    doctor_id = doctor_id or conv["data"].get("doctor_id")
    if not doctor_id or not conv["data"].get("date"):
        return None, "Choose a date before choosing a time."
    day = datetime.fromisoformat(conv["data"]["date"]).date()
    slots = [slot for slot in db.open_slots(conn, int(doctor_id), now, day) if slot["id"] != skip_slot]
    if _word(message) in VAGUE_TIMES:
        return None, "I need an exact time from the open slots, such as 9:00 AM. I cannot book a general time like morning."
    if button.startswith("slot:"):
        slot_id = _int_suffix(button)
        for slot in slots:
            if slot["id"] == slot_id:
                return slot, None
        return None, "That time is not an open slot for this doctor."
    matched = _match_time_text(message, slots)
    if matched == "vague":
        return None, "I need an exact time from the open slots, such as 9:00 AM. I cannot book a general time like morning."
    if matched is None:
        return None, "Choose one of the exact open times. Past times and unavailable times are rejected."
    return matched, None


def _match_time_text(message: str, slots):
    text = _word(message).replace(".", "")
    if text in VAGUE_TIMES:
        return "vague"
    for slot in slots:
        moment = _moment(slot["starts_at"])
        labels = {
            format_time(moment).lower(),
            moment.strftime("%H:%M"),
            moment.strftime("%I:%M").lstrip("0"),
            moment.strftime("%I:%M %p").lower().lstrip("0"),
        }
        compact = {label.replace(" ", "") for label in labels}
        if text in labels or text.replace(" ", "") in compact:
            return slot
    return None


def _parse_date(message: str, now: datetime):
    text = _word(message)
    today = now.astimezone(TZ).date()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for index, name in enumerate(weekdays):
        if text in {name, f"next {name}", f"this {name}"}:
            delta = (index - today.weekday()) % 7
            if text.startswith("next") and delta == 0:
                delta = 7
            return today + timedelta(days=delta)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m/%d", "%b %d %Y", "%B %d %Y", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt in {"%m/%d", "%b %d", "%B %d"}:
            try:
                return today.replace(month=parsed.month, day=parsed.day)
            except ValueError:
                return None
        return parsed.date()
    return None


def _validate_name(message: str) -> str | None:
    cleaned = _clean(message)
    if SENSITIVE_RE.search(cleaned) or SSN_RE.search(cleaned):
        return (
            "I cannot store that. I only keep a fictional patient name for this demo, "
            "not symptoms, a diagnosis, a date of birth, or a Social Security number."
        )
    letters = [char for char in cleaned if char.isalpha()]
    if len(letters) < 2 or not NAME_RE.fullmatch(cleaned):
        return "Enter a fictional name using letters, such as Jamie Rivera."
    return None


def _validate_contact(message: str) -> str | None:
    cleaned = _clean(message)
    if SENSITIVE_RE.search(cleaned) or SSN_RE.search(cleaned):
        return "I cannot store that. Enter a synthetic phone or email only, such as 555-010-0142 or demo@example.com."
    if EMAIL_RE.fullmatch(cleaned):
        return None
    digits = re.sub(r"\D", "", cleaned)
    if PHONE_RE.fullmatch(cleaned) and len(digits) >= 7:
        return None
    return "Enter a synthetic phone or email, such as 555-010-0142 or demo@example.com."


def _split_credentials(message: str, conv: dict):
    pending = conv["data"].get("pending_reference")
    tokens = [part.strip(" ,;") for part in (message or "").split() if part.strip(" ,;")]
    reference = pending
    code = None
    for token in tokens:
        if re.fullmatch(r"NS-[A-F0-9]{6}", token.upper()):
            reference = token.upper()
        elif code is None:
            code = token
    return reference, code


def _alternative_slots(conn, doctor_id: int, now: datetime):
    return db.open_slots(conn, doctor_id, now)[:5]


def _slot_buttons(slots):
    buttons = []
    for slot in slots:
        moment = _moment(slot["starts_at"])
        buttons.append({"id": f"slot:{slot['id']}", "label": f"{format_time(moment)}"})
    return buttons


def _active_managed(conn, conv):
    booking_id = conv["data"].get("booking_id")
    if not booking_id:
        return None
    booking = db.get_booking(conn, int(booking_id))
    if booking is None or booking["status"] != "active":
        return None
    return booking


def _lost_booking(conv, now):
    _clear_draft(conv, keep_failures=True)
    conv["state"] = "menu"
    return _pack(
        conv,
        ["That demo booking is no longer active, so it cannot be changed.", "Choose a service."],
        list(MENU_BUTTONS),
        now,
    )


def _unexpected(conn, conv, now):
    texts, buttons = _view(conn, conv, now)
    return _pack(conv, ["That choice is not available in this step.", *texts], buttons, now)


def _clear_draft(conv, keep_failures: bool):
    failures = conv["data"].get("auth_failures", 0) if keep_failures else 0
    greeted = conv["data"].get("greeted", True)
    conv["data"] = {"greeted": greeted, "auth_failures": failures}


def _pack_view(conn, conv, now, lead=None):
    texts, buttons = _view(conn, conv, now)
    if lead:
        texts = [lead, *texts]
    return _pack(conv, texts, buttons, now)


def _pack(conv, texts, buttons, now):
    stamp = format_stamp(now)
    return {
        "messages": [{"role": "bot", "text": text, "time": stamp} for text in texts if text],
        "buttons": buttons,
        "state": conv["state"],
    }


def _moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def _int_suffix(button: str) -> int:
    try:
        return int(button.split(":", 1)[1])
    except (IndexError, ValueError):
        return -1


def _word(message: str) -> str:
    return re.sub(r"[.!?]", "", (message or "").strip().lower())


def _clean(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip())

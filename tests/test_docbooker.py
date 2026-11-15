import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from app import create_app
from app.db import SlotTaken, ValidationError, connect, count_active, create_booking, init_db, open_slots
from app.timeutil import TZ


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "docbooker.db"
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "SECRET_KEY": "test-secret",
            "URL_PREFIX": "",
        }
    )
    application.config["DATABASE_FILE"] = str(database)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


class Bot:
    def __init__(self, client):
        self.client = client
        response = client.get("/api/bootstrap")
        assert response.status_code == 200
        self.body = response.get_json()
        self.csrf = self.body["csrf_token"]

    def say(self, message="", button=""):
        response = self.client.post(
            "/api/chat",
            json={"message": message, "button": button},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.body = response.get_json()
        assert response.status_code == 200, self.body
        self.csrf = self.body.get("csrf_token", self.csrf)
        return self.body

    def text(self):
        return "\n".join(item["text"] for item in self.body["messages"])

    def button_id(self, prefix):
        for item in self.body["buttons"]:
            if item["id"].startswith(prefix):
                return item["id"]
        raise AssertionError(self.body)


def walk_to_review(bot, picks=None, name="Jamie Rivera", contact="555-010-0142"):
    picks = picks or {}
    bot.say(button="menu:book")
    bot.say(button="consent:yes")
    dept = picks.get("dept") or bot.button_id("dept:")
    bot.say(button=dept)
    doctor = picks.get("doctor") or bot.button_id("doctor:")
    bot.say(button=doctor)
    date = picks.get("date") or bot.button_id("date:")
    bot.say(button=date)
    slot = picks.get("slot") or bot.button_id("slot:")
    bot.say(button=slot)
    bot.say(message=name)
    bot.say(message=contact)
    return {"dept": dept, "doctor": doctor, "date": date, "slot": slot}


def saved_codes(bot):
    text = bot.text()
    reference = re.search(r"NS-[A-F0-9]{6}", text).group(0)
    code = re.search(r"Management code: ([A-Z2-9]+)", text).group(1)
    return reference, code


def test_valid_booking_persists_reference_and_code(client, app):
    bot = Bot(client)
    walk_to_review(bot)
    bot.say(button="review:confirm")
    text = bot.text()
    assert "Demo appointment saved" in text
    reference, code = saved_codes(bot)
    raw = open(app.config["DATABASE"], "rb").read()
    assert reference.encode() in raw
    assert code.encode() not in raw
    conn = connect(app.config["DATABASE"])
    row = conn.execute("SELECT code_hash, status FROM bookings WHERE reference = ?", (reference,)).fetchone()
    assert row["status"] == "active"
    assert code not in row["code_hash"]
    stored = conn.execute("SELECT data_json FROM conversations").fetchone()["data_json"]
    assert code not in stored
    conn.close()


def test_rejected_confirmation_inserts_nothing(client, app):
    bot = Bot(client)
    walk_to_review(bot)
    bot.say(button="review:cancel")
    assert "No booking was saved" in bot.text()
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 0
    conn.close()


def test_duplicate_and_concurrent_slot_reservation(client, app, tmp_path):
    first = Bot(client)
    picks = walk_to_review(first, name="Jamie Rivera")
    second = Bot(app.test_client())
    walk_to_review(second, picks=picks, name="Riley Chen", contact="demo@example.com")
    first.say(button="review:confirm")
    assert "Demo appointment saved" in first.text()
    second.say(button="review:confirm")
    assert "did not save a second one" in second.text()
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 1
    slot_id = int(picks["slot"].split(":")[1])
    doctor_id = int(picks["doctor"].split(":")[1])
    now = datetime.now(TZ)
    free = [row["id"] for row in open_slots(conn, doctor_id, now) if row["id"] != slot_id]
    conn.close()

    barrier = threading.Barrier(2)
    results = []

    def worker():
        local = connect(app.config["DATABASE"])
        barrier.wait()
        try:
            create_booking(
                local,
                doctor_id=doctor_id,
                slot_id=free[0],
                patient_name="Concurrent Test",
                contact="555-010-0198",
                now=now,
            )
            results.append("ok")
        except SlotTaken:
            results.append("taken")
        finally:
            local.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["ok", "taken"]
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 2
    conn.close()


def test_past_and_malformed_inputs_are_rejected(client, app):
    bot = Bot(client)
    bot.say(button="menu:book")
    bot.say(button="consent:yes")
    bot.say(button=bot.button_id("dept:"))
    bot.say(button=bot.button_id("doctor:"))
    bot.say(message="banana")
    assert "specific calendar date" in bot.text()
    bot.say(message="2000-01-01")
    assert "past" in bot.text().lower()
    bot.say(button=bot.button_id("date:"))
    bot.say(message="morning")
    assert "exact time" in bot.text()
    conn = connect(app.config["DATABASE"])
    yesterday = (datetime.now(TZ) - timedelta(days=1)).isoformat()
    doctor_id = conn.execute("SELECT id FROM doctors ORDER BY id LIMIT 1").fetchone()["id"]
    conn.execute("INSERT INTO slots (doctor_id, starts_at) VALUES (?, ?)", (doctor_id, yesterday))
    past_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    with pytest.raises(ValidationError):
        create_booking(
            conn,
            doctor_id=doctor_id,
            slot_id=past_id,
            patient_name="Past Test",
            contact="555-010-0142",
            now=datetime.now(TZ),
        )
    assert count_active(conn) == 0
    conn.close()


def test_find_doctor_matches_department(client):
    bot = Bot(client)
    bot.say(message="Show me cardiologists")
    text = bot.text()
    assert "Dr. Helen Cho" in text
    assert "Dr. Luis Ortega" in text
    assert "Dr. Avery Cole" not in text
    assert "Dr. Priya Nair" not in text


def test_reschedule_is_atomic(app):
    bot = Bot(app.test_client())
    walk_to_review(bot, name="Alex Morgan")
    bot.say(button="review:confirm")
    reference, code = saved_codes(bot)
    conn = connect(app.config["DATABASE"])
    booking = conn.execute(
        "SELECT id, doctor_id, slot_id FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()
    original = booking["slot_id"]
    conn.close()

    bot.say(button="menu:manage")
    bot.say(message=f"{reference} {code}")
    bot.say(button="manage:reschedule")
    bot.say(button=bot.button_id("date:"))
    chosen = None
    for item in bot.body["buttons"]:
        if item["id"].startswith("slot:") and int(item["id"].split(":")[1]) != original:
            chosen = item["id"]
            break
    assert chosen
    bot.say(button=chosen)
    assert bot.body["state"] == "manage_review"
    target = int(chosen.split(":")[1])
    rival = connect(app.config["DATABASE"])
    create_booking(
        rival,
        doctor_id=booking["doctor_id"],
        slot_id=target,
        patient_name="Blair Quinn",
        contact="555-010-0160",
        now=datetime.now(TZ),
    )
    rival.close()
    bot.say(button="resched:confirm")
    assert "unchanged" in bot.text()
    conn = connect(app.config["DATABASE"])
    assert conn.execute(
        "SELECT slot_id FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()["slot_id"] == original

    bot.say(button=bot.button_id("slot:"))
    bot.say(button="resched:confirm")
    assert "new time" in bot.text()
    updated = conn.execute(
        "SELECT slot_id, status FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()
    conn.close()
    assert updated["status"] == "active"
    assert updated["slot_id"] != original
    assert updated["slot_id"] != target


def test_cancel_requires_confirmation_and_frees_slot(app):
    bot = Bot(app.test_client())
    picks = walk_to_review(bot, name="Casey Diaz")
    bot.say(button="review:confirm")
    reference, code = saved_codes(bot)
    slot_id = int(picks["slot"].split(":")[1])
    bot.say(button="menu:manage")
    bot.say(message=f"{reference} {code}")
    bot.say(button="manage:cancel")
    bot.say(button="cancel:no")
    conn = connect(app.config["DATABASE"])
    assert conn.execute(
        "SELECT status FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()["status"] == "active"
    assert conn.execute(
        "SELECT id FROM bookings WHERE slot_id = ? AND status = 'active'",
        (slot_id,),
    ).fetchone()
    conn.close()
    bot.say(button="manage:cancel")
    bot.say(button="cancel:yes")
    assert "cancelled" in bot.text().lower()
    conn = connect(app.config["DATABASE"])
    assert conn.execute(
        "SELECT status FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()["status"] == "cancelled"
    assert conn.execute(
        "SELECT id FROM bookings WHERE slot_id = ? AND status = 'active'",
        (slot_id,),
    ).fetchone() is None
    conn.close()
    again = Bot(app.test_client())
    again.say(button="menu:manage")
    again.say(message=f"{reference} {code}")
    assert "do not match an active demo booking" in again.text()
    assert "Casey Diaz" not in again.text()


def test_invalid_credentials_hide_booking_details(app):
    bot = Bot(app.test_client())
    walk_to_review(bot, name="Zebulon Quilltest", contact="555-010-0177")
    bot.say(button="review:confirm")
    reference, _code = saved_codes(bot)
    other = Bot(app.test_client())
    other.say(button="menu:manage")
    other.say(message=f"{reference} NOTACODE")
    assert "do not match an active demo booking" in other.text()
    assert "Zebulon" not in other.text()
    assert "Quilltest" not in other.text()
    missing = Bot(app.test_client())
    missing.say(button="menu:manage")
    missing.say(message="NS-ABCDEF NOTACODE")
    assert "do not match an active demo booking" in missing.text()
    assert "Zebulon" not in missing.text()


def test_sessions_are_isolated(app):
    first = Bot(app.test_client())
    second = Bot(app.test_client())
    first.say(button="menu:book")
    first.say(button="consent:yes")
    assert first.body["state"] == "book_department"
    assert second.body["state"] == "menu"
    second.say(message="hello there")
    assert second.body["state"] == "menu"
    assert first.body["state"] == "book_department"


def test_emergency_phrase_interrupts_scheduling(client, app):
    bot = Bot(client)
    bot.say(button="menu:book")
    bot.say(button="consent:yes")
    bot.say(message="I have chest pain")
    assert "call 911" in bot.text()
    assert bot.body["state"] == "menu"
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 0
    conn.close()


def test_medical_questions_get_no_treatment_advice(client):
    bot = Bot(client)
    bot.say(message="What medicine should I take for a fever?")
    text = bot.text().lower()
    assert "cannot provide medical advice" in text
    for banned in ("ibuprofen", "acetaminophen", "tylenol", "mg", "dose"):
        assert banned not in text


def test_unknown_input_offers_menu(client):
    bot = Bot(client)
    bot.say(message="purple elephant")
    assert "did not understand" in bot.text()
    labels = {item["id"] for item in bot.body["buttons"]}
    assert "menu:book" in labels
    assert "menu:find" in labels
    assert "menu:manage" in labels
    assert "menu:info" in labels
    assert "menu:finish" in labels


def test_database_survives_new_app_instance(tmp_path):
    database = tmp_path / "persist.db"
    config = {"TESTING": True, "DATABASE": str(database), "SECRET_KEY": "test-secret"}
    first = create_app(config)
    bot = Bot(first.test_client())
    walk_to_review(bot, name="Parker Lee", contact="demo@example.com")
    bot.say(button="review:confirm")
    reference, _code = saved_codes(bot)
    second = create_app(dict(config))
    conn = connect(second.config["DATABASE"])
    row = conn.execute(
        "SELECT patient_name, status FROM bookings WHERE reference = ?",
        (reference,),
    ).fetchone()
    conn.close()
    assert row["patient_name"] == "Parker Lee"
    assert row["status"] == "active"


def test_csrf_and_invalid_state_changes_are_rejected(client, app):
    rejected = client.post("/api/chat", json={"message": "hi", "button": "review:confirm"})
    assert rejected.status_code == 403
    missing = client.post("/api/reset")
    assert missing.status_code == 404
    bot = Bot(client)
    bot.say(button="review:confirm")
    assert "did not understand" in bot.text()
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 0
    bad = client.post(
        "/api/chat",
        data="not-json",
        headers={"X-CSRF-Token": bot.csrf, "Content-Type": "text/plain"},
    )
    assert bad.status_code == 400
    conn.close()


def test_natural_language_examples(client):
    bot = Bot(client)
    bot.say(message="I want to book a doctor")
    assert "consent" in bot.text().lower()
    bot.say(button="nav:menu")
    bot.say(button="discard:yes")
    bot.say(message="Can I change my appointment?")
    assert "booking reference" in bot.text().lower()
    bot.say(button="nav:menu")
    bot.say(message="Cancel my booking")
    assert "management code" in bot.text().lower()
    bot.say(button="nav:menu")
    bot.say(message="What are your hours?")
    assert "Monday through Friday" in bot.text()
    bot.say(message="Do you accept insurance?")
    assert "will not guess" in bot.text()
    assert "Aetna" not in bot.text()


def test_browser_script_does_not_store_secrets():
    script = open(os.path.join("static", "js", "chat.js"), encoding="utf-8").read()
    assert "localStorage" not in script
    assert "sessionStorage" not in script


def test_parameterized_query_keeps_strange_text(app):
    conn = connect(app.config["DATABASE"])
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO bookings (reference, code_salt, code_hash, patient_name, contact, doctor_id, slot_id, status, created_at, timezone) VALUES (?, ?, ?, ?, ?, 1, 1, 'cancelled', ?, 'America/New_York')",
        (
            "NS-SAFE01",
            "salt",
            "hash",
            "Ann'; DROP TABLE bookings;--",
            "555-010-0142",
            datetime.now(TZ).isoformat(),
        ),
    )
    conn.execute("COMMIT")
    stored = conn.execute(
        "SELECT patient_name FROM bookings WHERE reference = ?",
        ("NS-SAFE01",),
    ).fetchone()["patient_name"]
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    conn.close()
    assert stored == "Ann'; DROP TABLE bookings;--"
    assert "bookings" in {row["name"] for row in tables}


def test_url_prefix_is_stripped_before_routing(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "prefixed.db"),
            "SECRET_KEY": "test-secret",
            "URL_PREFIX": "/docbooker",
        }
    )
    client = application.test_client()
    response = client.get("/docbooker/health")
    assert response.status_code == 200
    assert response.get_json()["service"] == "docbooker"
    page = client.get("/docbooker/")
    assert page.status_code == 200
    assert b"DocBooker" in page.data


def test_restart_discard_does_not_save(client, app):
    bot = Bot(client)
    walk_to_review(bot)
    bot.say(button="restart")
    assert "Discard" in bot.text()
    bot.say(button="discard:yes")
    conn = connect(app.config["DATABASE"])
    assert count_active(conn) == 0
    conn.close()

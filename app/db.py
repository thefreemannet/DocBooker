"""SQLite storage for fictional doctors, slots, and demo bookings."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, time, timedelta

from .timeutil import TZ, in_bookable_window

DOCTORS = (
    ("Dr. Avery Cole", "General Medicine", "Primary care"),
    ("Dr. Mina Shah", "General Medicine", "Internal medicine"),
    ("Dr. Helen Cho", "Cardiology", "Preventive cardiology"),
    ("Dr. Luis Ortega", "Cardiology", "Heart rhythm"),
    ("Dr. Priya Nair", "Pediatrics", "General pediatrics"),
    ("Dr. Owen Blake", "Pediatrics", "Pediatric wellness"),
    ("Dr. Sofia Rossi", "Dermatology", "Medical dermatology"),
    ("Dr. Jonah Park", "Dermatology", "Skin screening"),
    ("Dr. Camille Brooks", "Orthopedics", "Sports medicine"),
    ("Dr. Andre Walsh", "Orthopedics", "Joint care"),
)

WEEKDAY_TIMES = (time(9, 0), time(10, 30), time(13, 0), time(14, 30), time(16, 0))
SATURDAY_TIMES = (time(9, 0), time(10, 30))
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SlotTaken(Exception):
    """The requested slot already has an active demo booking."""


class ValidationError(Exception):
    """The booking request failed a server-side rule."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    specialty TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS slots (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    starts_at TEXT NOT NULL,
    UNIQUE (doctor_id, starts_at)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    code_salt TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    contact TEXT NOT NULL,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    slot_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'cancelled')),
    created_at TEXT NOT NULL,
    timezone TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_active_slot
    ON bookings(slot_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(path: str, now: datetime | None = None) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM doctors").fetchone()["c"]
        if count == 0:
            seed(conn, now or datetime.now(TZ))
    finally:
        conn.close()


def seed(conn: sqlite3.Connection, now: datetime) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for name, department, specialty in DOCTORS:
            conn.execute(
                "INSERT INTO doctors (name, department, specialty) VALUES (?, ?, ?)",
                (name, department, specialty),
            )
        doctors = conn.execute("SELECT id FROM doctors ORDER BY id").fetchall()
        today = now.astimezone(TZ).date()
        for offset in range(14):
            day = today + timedelta(days=offset)
            if day.weekday() == 6:
                times = ()
            elif day.weekday() == 5:
                times = SATURDAY_TIMES
            else:
                times = WEEKDAY_TIMES
            for doctor in doctors:
                for slot_time in times:
                    moment = datetime.combine(day, slot_time, tzinfo=TZ)
                    if moment <= now:
                        continue
                    conn.execute(
                        "INSERT INTO slots (doctor_id, starts_at) VALUES (?, ?)",
                        (doctor["id"], moment.isoformat()),
                    )
        conn.execute("COMMIT")
    except Exception:
        _rollback(conn)
        raise


def hash_code(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def _new_reference(conn: sqlite3.Connection) -> str:
    for _ in range(8):
        reference = "NS-" + "".join(secrets.choice("ABCDEF0123456789") for _ in range(6))
        found = conn.execute(
            "SELECT 1 FROM bookings WHERE reference = ?",
            (reference,),
        ).fetchone()
        if not found:
            return reference
    raise ValidationError("Could not create a booking reference. Try again.")


def create_booking(
    conn: sqlite3.Connection,
    *,
    doctor_id: int,
    slot_id: int,
    patient_name: str,
    contact: str,
    now: datetime,
) -> dict:
    conn.execute("BEGIN IMMEDIATE")
    try:
        _require_open_slot(conn, doctor_id, slot_id, now)
        reference = _new_reference(conn)
        code = _new_code()
        salt = secrets.token_hex(16)
        created = now.astimezone(TZ).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO bookings (
                reference, code_salt, code_hash, patient_name, contact,
                doctor_id, slot_id, status, created_at, timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, 'America/New_York')
            """,
            (
                reference,
                salt,
                hash_code(salt, code),
                patient_name,
                contact,
                doctor_id,
                slot_id,
                created,
            ),
        )
        conn.execute("COMMIT")
        return {
            "id": cursor.lastrowid,
            "reference": reference,
            "management_code": code,
        }
    except sqlite3.IntegrityError:
        _rollback(conn)
        raise SlotTaken() from None
    except Exception:
        _rollback(conn)
        raise


def reschedule_booking(
    conn: sqlite3.Connection,
    booking_id: int,
    new_slot_id: int,
    now: datetime,
) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND status = 'active'",
            (booking_id,),
        ).fetchone()
        if booking is None:
            raise ValidationError("That demo booking is no longer active.")
        if booking["slot_id"] == new_slot_id:
            raise ValidationError("That is already the reserved time.")
        _require_open_slot(conn, booking["doctor_id"], new_slot_id, now)
        cursor = conn.execute(
            "UPDATE bookings SET slot_id = ? WHERE id = ? AND status = 'active'",
            (new_slot_id, booking_id),
        )
        if cursor.rowcount != 1:
            raise ValidationError("That demo booking is no longer active.")
        conn.execute("COMMIT")
    except sqlite3.IntegrityError:
        _rollback(conn)
        raise SlotTaken() from None
    except Exception:
        _rollback(conn)
        raise


def cancel_booking(conn: sqlite3.Connection, booking_id: int) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'",
            (booking_id,),
        )
        if cursor.rowcount != 1:
            raise ValidationError("That demo booking is no longer active.")
        conn.execute("COMMIT")
    except Exception:
        _rollback(conn)
        raise


def _require_open_slot(conn, doctor_id: int, slot_id: int, now: datetime) -> sqlite3.Row:
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if slot is None or slot["doctor_id"] != doctor_id:
        raise ValidationError("That time is not available for this doctor.")
    moment = datetime.fromisoformat(slot["starts_at"])
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=TZ)
    if not in_bookable_window(moment, now):
        raise ValidationError("That date or time is outside the bookable window.")
    taken = conn.execute(
        "SELECT id FROM bookings WHERE slot_id = ? AND status = 'active'",
        (slot_id,),
    ).fetchone()
    if taken:
        raise SlotTaken()
    return slot


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def verify_booking(conn: sqlite3.Connection, reference: str, code: str):
    """Return the active booking only when both secrets match. Otherwise None."""
    cleaned = (reference or "").strip().upper()
    row = conn.execute(
        "SELECT * FROM bookings WHERE reference = ? AND status = 'active'",
        (cleaned,),
    ).fetchone()
    digest = hash_code(row["code_salt"], code) if row else hashlib.sha256(b"docbooker").hexdigest()
    expected = row["code_hash"] if row else hashlib.sha256(b"missing").hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    return row


def list_doctors(conn: sqlite3.Connection, department: str):
    return conn.execute(
        "SELECT * FROM doctors WHERE department = ? ORDER BY name",
        (department,),
    ).fetchall()


def get_doctor(conn: sqlite3.Connection, doctor_id: int):
    return conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()


def get_slot(conn: sqlite3.Connection, slot_id: int):
    return conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()


def get_booking(conn: sqlite3.Connection, booking_id: int):
    return conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()


def open_slots(conn: sqlite3.Connection, doctor_id: int, now: datetime, day=None):
    rows = conn.execute(
        """
        SELECT s.* FROM slots s
        WHERE s.doctor_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM bookings b
              WHERE b.slot_id = s.id AND b.status = 'active'
          )
        ORDER BY s.starts_at
        """,
        (doctor_id,),
    ).fetchall()
    chosen = []
    last_day = (now.astimezone(TZ).date() + timedelta(days=13))
    for row in rows:
        moment = datetime.fromisoformat(row["starts_at"])
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=TZ)
        moment = moment.astimezone(TZ)
        if moment <= now or moment.date() > last_day:
            continue
        if day is not None and moment.date() != day:
            continue
        chosen.append(row)
    return chosen


def count_active(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM bookings WHERE status = 'active'"
    ).fetchone()["c"]

"""Explainable keyword intent matching. This is not a generative model."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEPARTMENTS = (
    "General Medicine",
    "Cardiology",
    "Pediatrics",
    "Dermatology",
    "Orthopedics",
)

DEPARTMENT_ALIASES = {
    "general": "General Medicine",
    "general medicine": "General Medicine",
    "family medicine": "General Medicine",
    "primary care": "General Medicine",
    "cardiology": "Cardiology",
    "cardiologist": "Cardiology",
    "cardiologists": "Cardiology",
    "heart": "Cardiology",
    "pediatrics": "Pediatrics",
    "pediatrician": "Pediatrics",
    "pediatricians": "Pediatrics",
    "kids": "Pediatrics",
    "dermatology": "Dermatology",
    "dermatologist": "Dermatology",
    "dermatologists": "Dermatology",
    "skin": "Dermatology",
    "orthopedics": "Orthopedics",
    "orthopedist": "Orthopedics",
    "orthopedic": "Orthopedics",
    "ortho": "Orthopedics",
}


@dataclass
class Intent:
    name: str
    department: str | None = None


def is_command(text: str, command: str) -> bool:
    cleaned = re.sub(r"[.!?]", "", (text or "").strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    options = {
        command,
        f"please {command}",
        f"{command} please",
        f"go to {command}",
        f"show {command}",
    }
    return cleaned in options


def is_finish(text: str) -> bool:
    cleaned = re.sub(r"[.!?]", "", (text or "").strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned in {
        "finish",
        "goodbye",
        "good bye",
        "end conversation",
        "that's all",
        "thats all",
        "that is all",
    }


def department_in_text(text: str) -> str | None:
    lowered = (text or "").lower()
    # Longer aliases first so "general medicine" wins over "general".
    for alias in sorted(DEPARTMENT_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return DEPARTMENT_ALIASES[alias]
    return None


def detect_intent(text: str) -> Intent:
    """Map a free-text menu message to one service. First match wins."""
    raw = text or ""
    lowered = raw.lower()
    department = department_in_text(raw)

    if re.search(r"\b(reschedul\w*|change my appointment|manage my appointment|manage an appointment)\b", lowered):
        return Intent("manage", department)
    if re.search(r"\bcancel my (booking|appointment)\b", lowered):
        return Intent("manage", department)
    if re.search(
        r"\b(hours|address|where are you|parking|phone|reception|are you open)\b",
        lowered,
    ):
        return Intent("info", department)
    if re.search(r"\b(find (a |me )?doctors?|show me|who are the|which doctors)\b", lowered) or (
        department and re.search(r"\b(doctor|doctors|cardiologist|dermatologist|pediatrician)\b", lowered)
    ):
        return Intent("find", department)
    if re.search(r"\b(book|booking|schedule|appointment|see a doctor)\b", lowered):
        return Intent("book", department)
    if department:
        return Intent("find", department)
    return Intent("unknown")

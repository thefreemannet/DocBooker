"""Answers drawn only from the curated fictional hospital file."""

from __future__ import annotations

import re
from pathlib import Path

RECEPTION_LINE = "Fictional reception phone: (555) 010-0199."

SECTION_KEYWORDS = (
    ("Reception hours", ("hour", "hours", "open", "opening", "close", "closed", "sunday", "saturday")),
    ("Address", ("address", "where", "location", "located", "directions")),
    ("Phone", ("phone", "call", "number", "reception", "contact")),
    ("Departments", ("department", "departments")),
    ("Parking", ("parking", "park", "garage", "lot")),
    ("Appointments", ("appointment", "appointments", "booking", "book")),
)

REFUSAL_TOPICS = (
    "insurance",
    "price",
    "prices",
    "cost",
    "costs",
    "payment",
    "pay",
    "billing",
    "medicaid",
    "medicare",
)


def load_sections(path: str | Path) -> dict[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def answer_question(question: str, sections: dict[str, str]) -> str:
    lowered = (question or "").lower()
    if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in REFUSAL_TOPICS):
        missing = sections.get("Not in this file", "")
        return (
            "I don't have that in the fictional hospital information, so I will not guess. "
            f"{missing} {RECEPTION_LINE}"
        ).strip()

    for section_name, words in SECTION_KEYWORDS:
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
            body = sections.get(section_name)
            if not body:
                break
            return (
                f"{section_name} at Northshore Demo Hospital (fictional demo details):\n{body}"
            )

    return (
        "I don't have that in the fictional hospital information. "
        f"{RECEPTION_LINE} Reception hours are Monday through Friday, 8:00 AM to 5:00 PM, "
        "and Saturday 9:00 AM to 1:00 PM, America/New_York. Sunday is closed."
    )

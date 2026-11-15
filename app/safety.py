"""Explicit phrase lists. This is not clinical triage and not a diagnosis engine."""

from __future__ import annotations

import re

# Documented emergency phrases. Matching is literal and small on purpose.
EMERGENCY_PATTERNS = (
    r"\bchest pain\b",
    r"\bheart attack\b",
    r"\bstroke\b",
    r"\bcan(?:not|'t) breathe\b",
    r"\bdifficulty breathing\b",
    r"\bshort of breath\b",
    r"\bnot breathing\b",
    r"\bunconscious\b",
    r"\boverdos(?:e|ing)\b",
    r"\bsuicidal\b",
    r"\bkill myself\b",
    r"\bwant to die\b",
    r"\bend my life\b",
    r"\bsevere bleeding\b",
    r"\bbleeding heavily\b",
    r"\bcall 911\b",
    r"\b911\b",
)

MEDICAL_PATTERNS = (
    r"\bdiagnos(?:e|is|es|ing)\b",
    r"\bsymptoms?\b",
    r"\bmedications?\b",
    r"\bmedicines?\b",
    r"\bprescriptions?\b",
    r"\bdosages?\b",
    r"\btreatments?\b",
    r"\bwhat should i take\b",
    r"\bdo i have\b",
    r"\bis this serious\b",
    r"\bside effects?\b",
    r"\bmedical advice\b",
    r"\bhurts?\b",
    r"\bhurting\b",
    r"\bpain\b",
    r"\bfever\b",
    r"\brashes?\b",
    r"\binfections?\b",
)

_EMERGENCY = re.compile("|".join(EMERGENCY_PATTERNS), re.IGNORECASE)
_MEDICAL = re.compile("|".join(MEDICAL_PATTERNS), re.IGNORECASE)

EMERGENCY_TEXT = (
    "If this may be a medical emergency, call 911 in the United States or your local "
    "emergency number. DocBooker only schedules simulated appointments and cannot help "
    "in an emergency. This check looks for a few explicit phrases only. It is not medical "
    "screening, and other wording may not be detected."
)

MEDICAL_TEXT = (
    "I cannot provide medical advice, diagnoses, or treatment suggestions. Please talk "
    "with a licensed clinician. For fictional hospital questions, reception is listed as "
    "(555) 010-0199. This is not a real clinic."
)


def is_emergency(text: str) -> bool:
    return bool(text and _EMERGENCY.search(text))


def is_medical(text: str) -> bool:
    return bool(text and _MEDICAL.search(text))

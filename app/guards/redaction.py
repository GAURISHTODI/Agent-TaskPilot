import hashlib
import re

_PATTERNS = [
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[ -]\d{4}[ -]\d{4}(?!\d)|(?<!\d)\d{12}(?!\d)")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ADDRESS", re.compile(
        r"\b(?:flat|house|door|plot|apt|apartment)\s*(?:no\.?|number|#)?\s*[\w\-/]+"
        r"(?:\s*,\s*[\w .\-]+){1,3}", re.I)),
]


def redact(text: str) -> str:
    for label, rx in _PATTERNS:
        text = rx.sub(f"[{label}]", text)
    return text


def hash_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)[-10:]
    return hashlib.sha256(digits.encode()).hexdigest()[:32]

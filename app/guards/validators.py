import re

from app.guards.injection import scan

_UNKNOWN_VENDOR_RE = re.compile(
    r"\b(?:[A-Z][a-z]+ ){1,3}(?:Plumbers|Services|Traders|Electricals|Repairs|Works|Enterprises|Cabs|Caterers|Movers)\b")
_BANNED_DRAFT_RE = re.compile(r"\b(?:pay now|advance payment|transfer|upi|otp|cvv|wire)\b", re.I)
_CONTACT_RE = re.compile(r"https?://|\b\d{10}\b|@\w+\.\w+")
_RUPEE_RE = re.compile(r"(?:₹|rs\.?\s?|inr\s?)\s?(\d[\d,]*)", re.I)


def validate_vendor_ids(ids: list[int], db_ids: set[int], shortlist_ids: set[int]) -> tuple[bool, str]:
    for i in ids:
        if i not in db_ids:
            return False, f"vendor {i} not in vendors table"
        if i not in shortlist_ids:
            return False, f"vendor {i} not in shortlist"
    return True, "ok"


def _echoes(draft: str, note: str, n: int = 6) -> bool:
    words = re.findall(r"\w+", note.lower())
    dwords = " ".join(re.findall(r"\w+", draft.lower()))
    return any(" ".join(words[i:i + n]) in dwords for i in range(max(0, len(words) - n + 1)))


def validate_draft(draft: str, vendor_name: str, allowed_vendor_names: set[str], budget: str | None,
                   untrusted_note: str = "") -> tuple[bool, str]:
    """Quality + safety gate for vendor outreach drafts. A failure means: fall back to the template."""
    d = (draft or "").strip()
    if len(d) < 25:
        return False, "empty_or_too_short"
    if len(d) > 900:
        return False, "too_long"
    if vendor_name not in d:
        return False, "missing_vendor_name"
    if scan(d):
        return False, "injection_pattern_in_draft"
    if _BANNED_DRAFT_RE.search(d):
        return False, "banned_payment_language"
    if _CONTACT_RE.search(d):
        return False, "contact_or_link_leak"
    for m in _UNKNOWN_VENDOR_RE.finditer(d):
        if not any(m.group(0) in n for n in allowed_vendor_names):
            return False, f"unknown_vendor_name:{m.group(0)}"
    if untrusted_note and _echoes(d, untrusted_note):
        return False, "echoes_customer_text"
    allowed = {re.sub(r"\D", "", budget)} if budget else set()
    for m in _RUPEE_RE.finditer(d):
        if m.group(1).replace(",", "") not in allowed:
            return False, f"unsupported_price:{m.group(1)}"
    return True, "ok"

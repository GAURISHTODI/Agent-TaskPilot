"""Classifier, extractor, clarifier, planner, risk scorer and drafter. Each wraps one Runner step."""
import difflib
import re

from app.agents.runner import Runner, StepFailed
from app.agents.schemas import ClarifyOut, ClassifyOut, DraftOut, JudgeOut, PlanOut, ReplyOut, RiskOut
from app.agents.taxonomy import BY_NAME, CATEGORIES, SLOT_QUESTIONS, slot_model
from app.core.config import settings
from app.guards.validators import validate_draft
from app.llm.fake import AREAS

# ---------------- classifier / extractor / clarifier ----------------


def classify(r: Runner, message: str) -> ClassifyOut:
    payload = {"untrusted_message": message, "taxonomy": [c.name for c in CATEGORIES]}
    out = r.run("classify", payload, ClassifyOut, "small")
    if settings.cascade_below and (out.category == "unknown" or out.confidence < settings.cascade_below):
        try:  # escalate only the uncertain cases to the larger (pricier) model
            second = r.run("classify", payload, ClassifyOut, "large")
            if second.category != "unknown" or out.category == "unknown":
                return second
        except StepFailed:
            pass
    return out


def _number(v: str | None) -> str | None:
    """Normalise a model-provided numeric slot ("under 1,500", "2k", "₹3 lakh") to plain digits, else None."""
    if not v:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|l)?(?!\w)", v.lower())
    if not m:
        return None
    n = float(m.group(1).replace(",", "")) * {"k": 1e3, "lakh": 1e5, "l": 1e5}.get(m.group(2) or "", 1)
    return str(int(n))


def _canonical_area(v: str | None) -> str | None:
    """Map a model-provided area onto the vendor table's spelling ("HSR" -> "HSR Layout"); unknown stays as-is."""
    if not v:
        return v
    low = re.sub(r"\s+", " ", v.lower()).strip(" .,")
    for alias in sorted(AREAS, key=len, reverse=True):
        if low == alias or low == AREAS[alias].lower() or re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", low):
            return AREAS[alias]
    close = difflib.get_close_matches(low, list(AREAS), n=1, cutoff=0.85)
    return AREAS[close[0]] if close else v


def extract_slots(r: Runner, message: str, category: str) -> dict[str, str | None]:
    model = slot_model(category)
    out = r.run("extract", {"untrusted_message": message, "category": category, "slots": list(model.model_fields)},
                model, "small")
    slots = {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in out.model_dump().items()}
    if "where" in slots:
        slots["where"] = _canonical_area(slots["where"])
    for k in ("budget", "party_size"):  # numeric slots are validated here, not trusted from the model
        if k in slots:
            slots[k] = _number(slots[k])
    return slots


def missing_required(category: str, slots: dict) -> list[str]:
    return [s for s in BY_NAME[category].required if not slots.get(s)]


def clarify(r: Runner, category: str, missing: list[str]) -> str:
    labels = [SLOT_QUESTIONS[m] for m in missing]
    return r.run("clarify", {"category": category, "missing": missing, "missing_labels": labels},
                 ClarifyOut, "small").question


# ---------------- risk ----------------

RISK_RULES = [
    (re.compile(r"\b(doctor|hospital|surgery|medicine|medical|symptom|chest pain|blood|injury|prescription|dentist|"
                r"dermatologist|physio|clinic|fever|toothache)\b", re.I), "health", 0.7),
    (re.compile(r"\b(lawyer|legal|court|divorce|fir|advocate|sue|lawsuit)\b", re.I), "legal", 0.85),
    (re.compile(r"\b(pay|payment|transfer|upi|loan|emi|bill|recharge|credit card|wire)\b", re.I), "payment", 0.8),
    (re.compile(r"\b(lakh|crore)\b|(?:₹|rs\.?\s?)\s?\d{2,3},?\d{3}\b", re.I), "high_spend", 0.7),
]


RISK_VOCAB = {"health", "medical", "legal", "payment", "money", "high_spend", "emergency", "urgent",
              "urgent_or_emergency", "financial_data_or_advance", "legal_adjacent"}


def risk_rules(text: str, category: str | None, budget: str | None) -> tuple[float, list[str]]:
    score, reasons = (BY_NAME[category].risk_default if category in BY_NAME else 0.0), []
    if category in BY_NAME and score >= 0.6:
        reasons.append(f"category:{category}")
    for rx, why, s in RISK_RULES:
        if rx.search(text):
            reasons.append(why)
            score = max(score, s)
    if budget and int(budget) >= 10000:
        reasons.append("high_spend")
        score = max(score, 0.7)
    return score, sorted(set(reasons))


def score_risk(r: Runner, text: str, category: str | None, budget: str | None,
               injection_hits: list[str]) -> tuple[float, list[str]]:
    """Rules first, LLM second opinion; the higher score wins."""
    score, reasons = risk_rules(text, category, budget)
    try:
        second = r.run("risk", {"untrusted_message": text, "category": category}, RiskOut, "small")
        valid = [x for x in second.reasons if x.strip().lower().replace(" ", "_") in RISK_VOCAB]
        if valid:  # a second opinion must justify itself with a known risk reason, else it is ignored
            score = max(score, second.risk)
            reasons += valid
    except StepFailed:
        reasons.append("risk_second_opinion_failed")
        score = max(score, settings.risk_review_threshold)  # fail closed
    if injection_hits:
        score = max(score, 0.9)
        reasons.append("prompt_injection:" + ",".join(injection_hits))
    return round(score, 3), sorted(set(reasons))


# ---------------- planner ----------------


def plan(r: Runner, category: str, slots: dict, context_text: str) -> PlanOut:
    return r.run("plan", {"category": category, "slots": slots, "untrusted_message": context_text}, PlanOut, "large")


def complexity(budget: str | None, risk: float, clarify_rounds: int, needs_vendor: bool) -> int:
    c = 1 + (1 if budget and int(budget) >= 5000 else 0) + (1 if risk >= 0.4 else 0) + clarify_rounds
    return max(1, min(5, c + (0 if needs_vendor else 1)))


# ---------------- drafter ----------------


def outreach_template(vendor_name: str, category: str, slots: dict) -> str:
    bits = [f"Hi {vendor_name}, this is the TaskPilot concierge team writing on behalf of a customer."]
    need = category.replace("_", " ")
    details = [f"{k.replace('_', ' ')}: {v}" for k, v in slots.items()
               if v and k not in ("budget",)]
    bits.append(f"We need help with {need}." + (f" Details - {'; '.join(details)}." if details else ""))
    if slots.get("budget"):
        bits.append(f"Budget is around ₹{slots['budget']}.")
    bits.append("Are you available, and what would your quote be? Please reply with your earliest slot and price.")
    return " ".join(bits)


def draft_vendor_message(r: Runner, vendor: dict, category: str, slots: dict, note: str,
                         allowed_names: set[str]) -> tuple[str, str, str]:
    """Returns (draft, source, validator_result). LLM polish with a quality gate; template on any failure."""
    tmpl = outreach_template(vendor["name"], category, slots)
    try:
        out = r.run("polish", {"template": tmpl, "vendor_name": vendor["name"], "untrusted_note": note},
                    DraftOut, "large")
    except StepFailed as e:
        return tmpl, "template", f"llm_failed:{e}"[:190]
    ok, why = validate_draft(out.draft, vendor["name"], allowed_names, slots.get("budget"), note)
    return (out.draft, "llm", "ok") if ok else (tmpl, "template", why)


def judge_draft(r: Runner, draft: str, facts: dict) -> JudgeOut:
    return r.run("judge", {"draft": draft, "facts": facts}, JudgeOut, "large")


def parse_vendor_reply(r: Runner, reply: str) -> ReplyOut:
    return r.run("parse_reply", {"untrusted_reply": reply}, ReplyOut, "small")


def draft_customer_update(r: Runner, facts: dict) -> str:
    fallback = f"Update on your request: {facts['vendor']} has responded and our team is reviewing it. We'll confirm shortly."
    try:
        out = r.run("customer_update", {"facts": facts}, DraftOut, "large").draft
    except StepFailed:
        return fallback
    if facts["vendor"] not in out or len(out) < 20:
        return fallback
    return out

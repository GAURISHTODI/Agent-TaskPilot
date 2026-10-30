"""Deterministic stand-in for an LLM provider (offline dev, tests, CI, reproducible evals).

It is rule-based, NOT a language model. Metrics measured with it describe the pipeline and guardrails
around a deterministic stub; they say nothing about how a real LLM would score on the same data.

Two tiers mimic a small/large model split:
  fake-small : exact keyword / regex matching
  fake-large : + Hinglish cues, typo-tolerant (fuzzy) matching, extra slot patterns

It is also deliberately *naive*: if untrusted text asks for a banned action it will propose it in
`tool_requests`, and it echoes suspicious "notes" into drafts. That is the worst-case model the
guardrails must contain.
"""
import difflib
import json
import re
import time

from app.agents.taxonomy import BY_NAME, CATEGORIES
from app.llm.base import LLMResponse, est_tokens, price_for

AREAS = {
    "koramangala": "Koramangala", "indiranagar": "Indiranagar", "hsr layout": "HSR Layout", "hsr": "HSR Layout",
    "whitefield": "Whitefield", "jayanagar": "Jayanagar", "jp nagar": "JP Nagar", "btm layout": "BTM Layout",
    "btm": "BTM Layout", "marathahalli": "Marathahalli", "electronic city": "Electronic City",
    "malleshwaram": "Malleshwaram", "bellandur": "Bellandur", "hebbal": "Hebbal", "yelahanka": "Yelahanka",
    "banashankari": "Banashankari", "sarjapur": "Sarjapur Road", "mg road": "MG Road",
    "rajajinagar": "Rajajinagar", "basavanagudi": "Basavanagudi",
}
CITIES = ["goa", "mumbai", "delhi", "chennai", "hyderabad", "pune", "kolkata", "jaipur", "kochi", "mysore",
          "ooty", "manali", "udaipur", "coorg", "hampi"]
DAYS = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun"
WHEN_RE = re.compile(
    rf"\b(?:day after tomorrow|tomorrow|today|tonight|this weekend|next week|(?:this |next )?(?:{DAYS})\b"
    r"|\d{1,2}(?::\d{2})?\s?(?:am|pm)|morning|evening|afternoon|night"
    r"|\d{1,2}(?:st|nd|rd|th)?\s(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)",
    re.I)
WHEN_HI_RE = re.compile(r"\b(parso|kal|aaj|shaam|subah|dopahar|raat|is weekend)\b", re.I)
HI_WHEN_MAP = {"parso": "day after tomorrow", "kal": "tomorrow", "aaj": "today", "shaam": "evening",
               "subah": "morning", "dopahar": "afternoon", "raat": "night", "is weekend": "this weekend"}
BUDGET_RES = [
    re.compile(r"(?:under|below|upto|up to|within|max|maximum|budget(?: of| is)?|around|approx|about)\s*"
               r"(?:rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|l)?\b", re.I),
    re.compile(r"(?:₹|rs\.?\s?|inr\s?)(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|l)?\b", re.I),
    re.compile(r"\b(\d[\d,]*)\s*(?:rs|rupees|rupaye)\b()", re.I),
]
BUDGET_HI_RE = re.compile(r"\b(\d[\d,]*)\s*(k)?\s*(?:rs|₹|rupaye)?\s*(?:tak|ke andar)\b", re.I)
NUMWORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10}
PARTY_RES = [
    re.compile(r"(?:\bfor|party of|table of|group of)\s+(\d{1,2})\b(?!\s*(?:am|pm|:|k\b|rs|₹|st|nd|rd|th|km))", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:people|persons|pax|guests|ppl|adults|of us|seats|tickets)\b", re.I),
    re.compile(r"\b(" + "|".join(NUMWORDS) + r")\s*(?:people|persons|pax|guests|of us|adults)\b", re.I),
]
RECIPIENT_RE = re.compile(
    r"\b(?:for|to)\s+(?:my\s+)?(mom|mother|dad|father|wife|husband|girlfriend|boyfriend|friend|boss|sister|"
    r"brother|son|daughter|colleague|grandma|grandpa)\b", re.I)

ITEM_VOCAB = {
    "groceries": ["milk", "eggs", "vegetables", "atta", "rice", "bread", "fruits", "paneer", "curd", "oil",
                  "sugar", "dal", "onions", "tomatoes", "coffee", "tea", "butter", "sabzi", "doodh"],
    "delivery_pickup": ["documents", "document", "parcel", "keys", "laptop", "gift", "food", "package",
                        "charger", "files", "box", "suitcase", "saaman"],
    "personal_admin": ["passport", "aadhaar", "aadhar", "pan card", "driving licence", "license renewal",
                       "rto", "notary", "form filling", "kagaz"],
    "tailoring": ["blouse", "kurta", "trousers", "shirt", "saree", "suit", "jeans", "dress", "lehenga"],
    "gadget_repair": ["phone", "laptop", "tablet", "mobile", "screen", "charger", "earbuds", "watch"],
    "appliance_repair": ["washing machine", "fridge", "refrigerator", "microwave", "geyser", "water purifier", "mixer"],
    "tutoring": ["maths", "physics", "chemistry", "guitar", "english", "piano", "coding", "science", "biology"],
    "bill_payment": ["electricity bill", "credit card bill", "mobile recharge", "wifi bill", "rent", "water bill",
                     "gas bill", "emi", "loan emi", "recharge"],
}
ISSUE_VOCAB = {
    "doctor_appointment": ["fever", "cold", "cough", "headache", "back pain", "toothache", "skin rash", "checkup",
                           "check-up", "knee pain", "stomach pain", "dental", "eye", "allergy", "physio",
                           "dentist", "dermatologist", "cardiologist", "pediatrician"],
    "gadget_repair": ["cracked screen", "not charging", "battery", "not turning on", "slow", "water damage",
                      "screen", "broken"],
    "wifi_internet": ["slow", "no connection", "disconnected", "router", "no internet", "keeps dropping"],
    "legal_help": ["divorce", "property", "legal notice", "agreement", "fir", "tenant", "dispute", "court"],
    "insurance_finance": ["claim", "renewal", "tax filing", "itr", "loan", "policy renewal", "mutual fund"],
}
BANNED_TRIGGERS = [
    (re.compile(r"send (?:the )?(?:payment|money)|transfer|\bpay\b|payment link|upi", re.I), "pay"),
    (re.compile(r"\bbook (?:it|now|directly)|confirm the booking|auto[- ]?book", re.I), "book"),
    (re.compile(r"send (?:a )?(?:message|whatsapp)|message the vendor now|without approval", re.I), "send_message"),
]
BAD_PHRASE_RE = re.compile(r"ignore (?:all |previous |the )?(?:rules|instructions)|system prompt|you are now|"
                           r"disregard|override|developer mode|jailbreak", re.I)
UNKNOWN_VENDOR_RE = re.compile(r"\b(?:[A-Z][a-z]+ ){1,3}(?:Plumbers|Services|Traders|Electricals|Repairs|Works|Enterprises)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _kw_hit(text: str, kw: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(kw.strip()) + r"(?!\w)", text) is not None


_SINGLE_VOCAB: dict[str, list[str]] = {}
for _c in CATEGORIES:
    for _k in _c.keywords + _c.hi:
        if " " not in _k.strip() and len(_k.strip()) >= 5:
            _SINGLE_VOCAB.setdefault(_k.strip(), []).append(_c.name)


def classify(msg: str, large: bool) -> dict:
    text = " " + _norm(msg) + " "
    scores: dict[str, float] = {}
    for c in CATEGORIES:
        s = 0.0
        for kw in c.keywords + (c.hi if large else []):
            if _kw_hit(text, kw):
                s += 2.0 if " " in kw.strip() else 1.5
        scores[c.name] = s
    if large:
        for tok in set(re.findall(r"[a-z]{5,}", text)):
            if tok in _SINGLE_VOCAB:
                continue
            m = difflib.get_close_matches(tok, list(_SINGLE_VOCAB), n=1, cutoff=0.84)
            if m:
                for cat in _SINGLE_VOCAB[m[0]]:
                    scores[cat] += 1.2
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (top_name, top), (_, second) = ranked[0], ranked[1]
    if top <= 0:
        return {"category": "unknown", "confidence": 0.1}
    margin = (top - second) / top
    conf = round(min(0.99, 0.3 + 0.65 * margin * min(1.0, top / 2)), 3)
    return {"category": top_name, "confidence": conf}


def _to_number(num: str, suffix: str | None) -> str:
    v = float(num.replace(",", ""))
    s = (suffix or "").lower()
    if s == "k":
        v *= 1000
    elif s in ("lakh", "l"):
        v *= 100000
    return str(int(v))


def extract(msg: str, category: str, large: bool) -> dict:
    text = " " + _norm(msg) + " "
    slots: dict[str, str | None] = {}
    # when
    whens = [m.group(0) for m in WHEN_RE.finditer(text)]
    if large:
        whens += [HI_WHEN_MAP[m.group(0).lower()] for m in WHEN_HI_RE.finditer(text)]
    slots["when"] = " ".join(dict.fromkeys(w.strip() for w in whens)) or None
    # where
    where = None
    for alias in sorted(AREAS, key=len, reverse=True):
        if _kw_hit(text, alias):
            where = AREAS[alias]
            break
    if where is None and large:
        for tok in re.findall(r"[a-z]{6,}", text):
            m = difflib.get_close_matches(tok, [a for a in AREAS if " " not in a and len(a) >= 6], n=1, cutoff=0.82)
            if m:
                where = AREAS[m[0]]
                break
    slots["where"] = where
    # budget
    budget = None
    for rx in BUDGET_RES:
        m = rx.search(text)
        if m:
            budget = _to_number(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            break
    if budget is None and large:
        m = BUDGET_HI_RE.search(text)
        if m:
            budget = _to_number(m.group(1), m.group(2))
    slots["budget"] = budget
    # party size
    party = None
    for rx in PARTY_RES:
        m = rx.search(text)
        if m:
            g = m.group(1).lower()
            party = str(NUMWORDS.get(g, g))
            break
    slots["party_size"] = party
    # destination
    dest = None
    for city in CITIES:
        if re.search(rf"\b(?:to|for|in|at)\s+{city}\b", text) or (large and re.search(rf"\b{city}\b", text)):
            dest = city.title()
            break
    slots["destination"] = dest
    # recipient
    m = RECIPIENT_RE.search(text)
    slots["recipient"] = m.group(1).lower() if m else None
    # category-specific vocab slots
    items = [w for w in ITEM_VOCAB.get(category, []) if _kw_hit(text, w)]
    slots["item"] = ", ".join(dict.fromkeys(items)) or None
    issues = [w for w in ISSUE_VOCAB.get(category, []) if _kw_hit(text, w)]
    slots["issue"] = ", ".join(dict.fromkeys(issues)) or None
    return slots


RISK_SOFT = [
    (re.compile(r"\b(emergency|urgent(?:ly)?|asap|immediately|chest|bleeding|unconscious|panic)\b", re.I), "urgent_or_emergency", 0.65),
    (re.compile(r"\b(cash|advance|deposit|wallet|bank account|otp|cvv|pin)\b", re.I), "financial_data_or_advance", 0.65),
    (re.compile(r"\b(visa|immigration|police|tax notice|summons)\b", re.I), "legal_adjacent", 0.65),
]


def parse_reply(reply: str) -> dict:
    low = reply.lower()
    price = None
    m = re.search(r"(?:₹|rs\.?\s?|inr\s?)(\d[\d,]*)|(\d[\d,]*)\s*(?:rs|rupees|/-)", reply, re.I)
    if m:
        price = int((m.group(1) or m.group(2)).replace(",", ""))
    available: bool | None = None
    if re.search(r"\b(not available|unavailable|can'?t|cannot|no slot|fully booked|busy|sorry|nahi)\b", low):
        available = False
    elif re.search(r"\b(available|can do|yes|sure|ok|confirmed|free|haan|done)\b", low):
        available = True
    slot = None
    sm = re.search(rf"(?:{DAYS}|tomorrow|today)\b[^.,;]*|\d{{1,2}}(?::\d{{2}})?\s?(?:am|pm)", low)
    if sm:
        slot = sm.group(0).strip()
    return {"available": available, "price": price, "slot": slot, "notes": reply[:140]}


def plan_steps(category: str) -> list[dict]:
    spec = BY_NAME.get(category)
    label = category.replace("_", " ")
    if spec is not None and not spec.needs_vendor:
        steps = [
            ("agent", f"Capture details for {label} and verify with customer", 0),
            ("human", f"Ops completes the {label} action manually (no autonomous execution)", 6),
            ("agent", "Draft customer confirmation", 0),
            ("human", "Approve and send customer update", 1),
        ]
    else:
        steps = [
            ("agent", f"Classify and extract details for {label}", 0),
            ("agent", "Shortlist verified vendors from the vendor table", 0),
            ("human", "Review and approve vendor outreach drafts", 2),
            ("vendor", "Vendor confirms availability and quote", 30),
            ("human", "Review vendor reply and choose an option", 3),
            ("agent", "Draft customer status update", 0),
            ("human", "Approve and send customer update", 1),
        ]
    return [{"order": i + 1, "owner": o, "action": a, "effort_min": e} for i, (o, a, e) in enumerate(steps)]


class FakeLLM:
    """Implements LLMClient. `tier` selects fake-small / fake-large behaviour."""

    def complete(self, step: str, system: str, user: str, tier: str = "small") -> LLMResponse:
        t0 = time.perf_counter()
        model = "fake-large" if tier == "large" else "fake-small"
        large = tier == "large"
        p = json.loads(user)
        out = self._dispatch(step, p, large)
        text = json.dumps(out, ensure_ascii=False)
        tin, tout = est_tokens(system + user), est_tokens(text)
        return LLMResponse(text, model, tin, tout, price_for(model, tin, tout), (time.perf_counter() - t0) * 1000)

    def _dispatch(self, step: str, p: dict, large: bool) -> dict:
        if step == "classify":
            return classify(p["untrusted_message"], large)
        if step == "extract":
            return extract(p["untrusted_message"], p["category"], large)
        if step == "clarify":
            miss = p["missing_labels"]
            joined = miss[0] if len(miss) == 1 else ", ".join(miss[:-1]) + " and " + miss[-1]
            return {"question": f"Happy to help! Could you share {joined}?"}
        if step == "plan":
            out = {"steps": plan_steps(p["category"]), "tool_requests": []}
            msg = p.get("untrusted_message", "")
            for rx, tool in BANNED_TRIGGERS:  # naive model: obeys instructions found in untrusted text
                if rx.search(msg):
                    out["tool_requests"].append({"tool": tool})
            return out
        if step == "polish":
            draft = p["template"]
            note = p.get("untrusted_note", "")
            if note and (BAD_PHRASE_RE.search(note) or UNKNOWN_VENDOR_RE.search(note)
                         or re.search(r"recommend|i know|vendor|echo", note, re.I)):
                draft += f"\n\nCustomer note: {note}"
            return {"draft": draft}
        if step == "risk":
            msg = p["untrusted_message"]
            reasons, score = [], 0.0
            for rx, why, s in RISK_SOFT:
                if rx.search(msg):
                    reasons.append(why)
                    score = max(score, s)
            return {"risk": score, "reasons": reasons}
        if step == "parse_reply":
            out = parse_reply(p["untrusted_reply"])
            out["tool_requests"] = [{"tool": t} for rx, t in BANNED_TRIGGERS if rx.search(p["untrusted_reply"])]
            return out
        if step == "judge":
            # Deterministic rubric, NOT a language model judging: facts covered / unsupported content.
            d, f = p["draft"].lower(), p["facts"]
            vals = [str(v).lower() for v in f.values() if v]
            covered = sum(v in d for v in vals) / len(vals) if vals else 1.0
            unsupported = bool(UNKNOWN_VENDOR_RE.search(p["draft"]) and f.get("vendor") not in p["draft"])
            return {"faithfulness": 1 if unsupported else 5, "completeness": max(1, round(1 + 4 * covered)),
                    "tone": 5 if re.search(r"\b(hi|hello|please|thank)", d) else 3}
        if step == "customer_update":
            f = p["facts"]
            if f.get("price") and f.get("available") is not False:
                body = (f"Good news! {f['vendor']} can do it{(' on ' + f['slot']) if f.get('slot') else ''} "
                        f"for ₹{f['price']}. Shall we go ahead?")
            elif f.get("available") is False:
                body = f"{f['vendor']} isn't available for your slot. We're checking the next option for you."
            else:
                body = f"{f['vendor']} has replied and our team is reviewing the details. We'll update you shortly."
            return {"draft": body}
        raise ValueError(f"unknown step {step}")

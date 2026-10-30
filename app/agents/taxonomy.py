"""Fixed category taxonomy + per-category typed slot schemas.

`keywords` are English cues; `hi` are Hinglish cues that only the larger (fuzzy + Hinglish aware)
model uses. Slot names come from a shared pool so the extractor stays small.
"""
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, create_model

SLOT_POOL = ["when", "where", "budget", "party_size", "item", "issue", "destination", "recipient"]
SLOT_QUESTIONS = {
    "when": "when you need it (day/time)",
    "where": "your area/locality",
    "budget": "your budget",
    "party_size": "how many people",
    "item": "what exactly you need",
    "issue": "what the problem or reason is",
    "destination": "the destination",
    "recipient": "who it is for",
}


@dataclass
class CategorySpec:
    name: str
    keywords: list[str]
    required: list[str]
    risk_default: float = 0.1
    detailed: bool = False
    hi: list[str] = field(default_factory=list)
    manual_minutes: float = 20.0
    needs_vendor: bool = True


C = CategorySpec
CATEGORIES: list[CategorySpec] = [
    # ---- detailed (hand-crafted) ----
    C("restaurant_booking", ["table", "reservation", "restaurant", "dinner", "lunch", "brunch", "book a table"],
      ["when", "where", "party_size"], detailed=True, hi=["khana", "table book"], manual_minutes=25),
    C("home_repair_ac", ["ac ", "air conditioner", "not cooling", "split ac", "ac service", "ac repair", "ac technician"],
      ["when", "where"], detailed=True, hi=["ac theek", "ac kharab"], manual_minutes=35),
    C("plumbing", ["plumber", "leak", "tap", "pipe", "drain", "clogged", "flush", "water leakage"],
      ["when", "where"], detailed=True, hi=["nal", "paani leak", "plumber chahiye"], manual_minutes=35),
    C("electrician", ["electrician", "wiring", "switch", "ceiling fan", "short circuit", "mcb", "socket", "inverter"],
      ["when", "where"], detailed=True, hi=["bijli", "light kharab"], manual_minutes=35),
    C("groceries", ["groceries", "milk", "eggs", "vegetables", "atta", "rice", "bread", "fruits", "kirana"],
      ["item", "where"], detailed=True, hi=["sabzi", "doodh", "ration"], manual_minutes=15, needs_vendor=True),
    C("travel_booking", ["flight", "train ticket", "bus ticket", "hotel", "trip", "travel", "tickets to"],
      ["destination", "when"], risk_default=0.3, detailed=True, hi=["ticket book", "yatra"], manual_minutes=45),
    C("gifting", ["gift", "bouquet", "flowers", "cake", "hamper", "anniversary", "birthday gift", "surprise"],
      ["recipient", "when"], detailed=True, hi=["tohfa", "gift bhejna"], manual_minutes=30),
    C("doctor_appointment", ["doctor", "appointment", "dentist", "physio", "clinic", "dermatologist", "checkup", "check-up"],
      ["issue", "when"], risk_default=0.7, detailed=True, hi=["doctor ko dikhana", "dawai"], manual_minutes=30),
    C("delivery_pickup", ["courier", "parcel", "drop off", "deliver", "package"],
      ["item", "where", "when"], detailed=True, hi=["parcel bhejna", "saaman"], manual_minutes=20),
    C("personal_admin", ["passport", "aadhaar", "aadhar", "pan card", "rto", "driving licence", "license renewal", "notary", "form filling"],
      ["item", "when"], risk_default=0.4, detailed=True, hi=["kagaz", "document banwana"], manual_minutes=40, needs_vendor=True),
    # ---- generic ----
    C("cab_booking", ["cab", "taxi", "airport drop", "airport pickup", "ride to"], ["when", "where"], manual_minutes=10, needs_vendor=True),
    C("laundry", ["laundry", "dry clean", "ironing", "washing clothes", "dhobi"], ["when", "where"], manual_minutes=15),
    C("house_cleaning", ["house cleaning", "deep clean", "maid", "cleaning service", "sofa cleaning", "bathroom cleaning"],
      ["when", "where"], manual_minutes=25, hi=["safai"]),
    C("pest_control", ["pest control", "cockroach", "termite", "mosquito", "rats", "bed bugs"], ["when", "where"], manual_minutes=25),
    C("car_service", ["car service", "car wash", "car repair", "tyre", "battery jump", "car servicing"], ["when", "where"], manual_minutes=30),
    C("bike_service", ["bike service", "scooter", "bike repair", "motorcycle", "bike puncture"], ["when", "where"], manual_minutes=25),
    C("carpentry", ["carpenter", "furniture", "wardrobe", "cupboard repair", "door repair", "bed repair"], ["when", "where"], manual_minutes=35),
    C("painting", ["painter", "wall paint", "painting", "whitewash", "waterproofing"], ["when", "where"], manual_minutes=40),
    C("salon_at_home", ["salon", "haircut", "facial", "manicure", "pedicure", "waxing", "beautician"], ["when", "where"], manual_minutes=20),
    C("tailoring", ["tailor", "stitching", "alteration", "blouse", "hemming"], ["item", "when"], manual_minutes=20),
    C("event_decor", ["decoration", "decorator", "balloon", "party decor", "event setup"], ["when", "where", "budget"], manual_minutes=40),
    C("photographer", ["photographer", "photoshoot", "videographer", "photo shoot"], ["when", "where", "budget"], manual_minutes=35),
    C("catering", ["catering", "caterer", "party food", "bulk food", "tiffin"], ["when", "party_size", "where"], manual_minutes=35),
    C("movie_tickets", ["movie", "cinema", "pvr", "inox", "film tickets", "show tickets"], ["when", "party_size"], manual_minutes=12, needs_vendor=False),
    C("pet_care", ["pet", "dog walker", "dog grooming", "pet sitter", "cat", "puppy"], ["when", "where"], manual_minutes=25),
    C("tutoring", ["tutor", "coaching", "maths teacher", "home tuition", "guitar class", "classes for"], ["item", "when", "where"], manual_minutes=30),
    C("gadget_repair", ["phone screen", "laptop repair", "mobile repair", "screen replacement", "laptop not", "charger"], ["item", "issue", "where"], manual_minutes=30),
    C("appliance_repair", ["washing machine", "fridge", "refrigerator", "microwave", "geyser", "water purifier", "mixer"], ["item", "when", "where"], manual_minutes=35),
    C("packers_movers", ["packers", "movers", "shifting", "relocation", "move house"], ["when", "where", "budget"], risk_default=0.3, manual_minutes=50),
    C("wifi_internet", ["wifi", "broadband", "internet connection", "router", "fibre"], ["issue", "where"], manual_minutes=25),
    C("gas_cylinder", ["gas cylinder", "lpg", "cylinder refill", "gas booking"], ["where"], manual_minutes=10),
    C("bill_payment", ["pay my", "bill payment", "recharge", "electricity bill", "credit card bill", "transfer money", "upi payment", "emi"],
      ["item", "budget"], risk_default=0.85, manual_minutes=12, needs_vendor=False),
    C("legal_help", ["lawyer", "legal notice", "court", "advocate", "divorce", "fir ", "agreement drafting", "legal"],
      ["issue", "when"], risk_default=0.85, manual_minutes=45),
    C("insurance_finance", ["insurance", "mutual fund", "loan", "tax filing", "itr", "investment", "policy renewal"],
      ["issue", "when"], risk_default=0.75, manual_minutes=40),
]

BY_NAME = {c.name: c for c in CATEGORIES}


def slot_model(category: str) -> type[BaseModel]:
    """Typed slot schema for a category: every pool slot is optional (null = not stated)."""
    spec = BY_NAME[category]
    fields = {s: (str | None, None) for s in SLOT_POOL if s in spec.required or s in ("budget", "where", "when")}
    return create_model(f"Slots_{category}", __config__=ConfigDict(coerce_numbers_to_str=True), **fields)  # type: ignore[call-overload]

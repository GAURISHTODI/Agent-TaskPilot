"""Seed: 34 categories (10 detailed), ~90 synthetic vendors, 10 synthetic customers. All data is fake."""
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.taxonomy import CATEGORIES
from app.db.models import Category, Customer, Vendor, VendorArea, VendorCategory
from app.guards.redaction import hash_phone
from app.llm.fake import AREAS

AREA_LIST = sorted(set(AREAS.values()))
CORE_AREAS = ["Koramangala", "Indiranagar", "HSR Layout", "Whitefield", "Jayanagar", "BTM Layout", "JP Nagar", "Marathahalli"]
PREFIX = ["Quick", "Reliable", "Prime", "Urban", "Swift", "Metro", "Trusty", "Bright", "Ace", "Sure", "Royal", "Nova"]
SUFFIX = ["Care", "Hub", "Pros", "Co", "Express", "Solutions", "Team", "Point"]

DEMO_CUSTOMERS = [
    ("Aarav Mehta", "+91 90000 00001", "premium"), ("Diya Rao", "+91 90000 00002", "mini"),
    ("Kabir Singh", "+91 90000 00003", "mini"), ("Meera Nair", "+91 90000 00004", "premium"),
    ("Rohan Gupta", "+91 90000 00005", "mini"), ("Ishita Das", "+91 90000 00006", "mini"),
    ("Vikram Shah", "+91 90000 00007", "premium"), ("Ananya Iyer", "+91 90000 00008", "mini"),
    ("Neil Fernandes", "+91 90000 00009", "mini"), ("Sana Khan", "+91 90000 00010", "premium"),
]


def seed(db: Session) -> None:
    if db.scalar(select(Category.id).limit(1)):
        return
    rng = random.Random(42)
    cats = {}
    for c in CATEGORIES:
        row = Category(name=c.name, required_slots=c.required, risk_default=c.risk_default, detailed=c.detailed)
        db.add(row)
        cats[c.name] = row
    db.flush()
    n = 0
    for c in CATEGORIES:
        if not c.needs_vendor:
            continue
        count = 4 if c.detailed else 2
        label = " ".join(w.title() for w in c.name.split("_")[:2])
        for i in range(count):
            n += 1
            v = Vendor(
                name=f"{rng.choice(PREFIX)}{rng.choice(SUFFIX)} {label} #{n}",
                rating=round(rng.uniform(3.6, 4.9), 1), on_time_rate=round(rng.uniform(0.62, 0.98), 2),
                price_band=rng.choice([1, 2, 2, 3]), contact=f"+91 8{rng.randint(10**8, 10**9 - 1)}", verified=True,
            )
            db.add(v)
            db.flush()
            db.add(VendorCategory(vendor_id=v.id, category_id=cats[c.name].id))
            areas = set(rng.sample(CORE_AREAS, 5 if c.detailed else 3)) | set(rng.sample(AREA_LIST, 2))
            if c.detailed:
                areas |= {"Koramangala", "Indiranagar", "HSR Layout"}
            for a in sorted(areas):
                db.add(VendorArea(vendor_id=v.id, area=a))
    # one unverified vendor that must never be shortlisted
    bad = Vendor(name="Unverified Fixers (do not use)", rating=5.0, on_time_rate=1.0, price_band=1,
                 contact="+91 8000000000", verified=False)
    db.add(bad)
    db.flush()
    db.add(VendorCategory(vendor_id=bad.id, category_id=cats["plumbing"].id))
    db.add(VendorArea(vendor_id=bad.id, area="Koramangala"))
    for name, phone, plan in DEMO_CUSTOMERS:
        db.add(Customer(name=name, phone_hash=hash_phone(phone), plan=plan, plan_price=1999 if plan == "premium" else 399))
    db.commit()

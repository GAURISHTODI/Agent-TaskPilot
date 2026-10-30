"""Vendor shortlist: pure SQL filter + deterministic scoring. No LLM involved, so no invented vendors."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Vendor, VendorArea, VendorCategory


def budget_band(budget: str | None) -> int | None:
    if not budget:
        return None
    b = int(budget)
    return 1 if b < 1000 else 2 if b < 5000 else 3


def search_vendors(db: Session, category_id: int, area: str | None, budget: str | None, limit: int = 3) -> list[dict]:
    q = (select(Vendor).join(VendorCategory, VendorCategory.vendor_id == Vendor.id)
         .where(VendorCategory.category_id == category_id, Vendor.verified.is_(True)))
    vendors = db.scalars(q).all()
    areas: dict[int, set[str]] = {}
    for va in db.scalars(select(VendorArea).where(VendorArea.vendor_id.in_([v.id for v in vendors] or [0]))):
        areas.setdefault(va.vendor_id, set()).add(va.area)
    band = budget_band(budget)
    out = []
    for v in vendors:
        area_match = bool(area) and area in areas.get(v.id, set())
        if area and not area_match:
            continue  # hard filter: never suggest a vendor that does not serve the customer's area
        price_fit = 1.0 if band is None or v.price_band <= band else 0.5
        score = 0.4 * v.rating / 5 + 0.3 * v.on_time_rate + 0.2 * (1.0 if area_match else 0.5) + 0.1 * price_fit
        out.append({"vendor_id": v.id, "name": v.name, "rating": v.rating, "on_time_rate": v.on_time_rate,
                    "price_band": v.price_band, "area_match": area_match, "score": round(score, 4)})
    out.sort(key=lambda d: (-d["score"], d["vendor_id"]))
    return out[:limit]

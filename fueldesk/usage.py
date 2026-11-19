"""Turn one month of transactions plus the card register into per-card usage.
Reports, dashboards and analytics all build on this single calculation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import Database
from .fqms import FqmsData

UNREGISTERED = "NOT REGISTERED"
UNCATEGORIZED = "UNCATEGORIZED"

OK = "OK"
EXCEEDED = "EXCEEDED LIMIT"
NO_LIMIT = "NO LIMIT SET"
NEW_CARD = "NEW CARD - NOT REGISTERED"
INACTIVE = "INACTIVE CARD - HAS USAGE"


@dataclass
class CardUsage:
    card: str
    vehicle: str
    name: str
    category: str
    limit: float
    is_escort: bool
    registered: bool
    litres: float = 0.0
    value: float = 0.0
    fills: int = 0
    daily: dict = field(default_factory=dict)       # day-of-month -> litres
    status: str = OK
    first_use: object = None
    last_use: object = None

    @property
    def balance(self):
        """Limit minus usage; None when no limit is set (a balance would mislead)."""
        return round(self.limit - self.litres, 3) if self.limit > 0 else None


def _status(u: CardUsage, active: bool) -> str:
    if not u.registered:
        return NEW_CARD
    if not active:
        return INACTIVE
    if u.limit > 0 and u.litres > u.limit:
        return EXCEEDED
    if u.limit <= 0 and u.litres > 0:
        return NO_LIMIT
    return OK


def compute_usage(db: Database, data: FqmsData) -> list[CardUsage]:
    """Registered active cards first (in category order, even with no usage),
    then removed/unregistered cards that have transactions."""
    df = data.df
    all_cards = db.list_cards(include_inactive=True, as_of=data.period_end)
    by_card = {c["card_number"]: c for c in all_cards}

    groups = {k: g for k, g in df.groupby("card")}
    out: list[CardUsage] = []

    def make(card, reg):
        g = groups.get(card)
        if reg:
            u = CardUsage(card, reg["vehicle_number"], reg["name"],
                          reg["category"] or UNCATEGORIZED, float(reg["limit_liters"]),
                          reg["is_escort"], True)
        else:   # take whatever the FQMS file says about this card
            vehicle = name = ""
            if g is not None:
                vs = g["vehicle"][g["vehicle"] != ""]
                ns = g["name"][g["name"] != ""]
                vehicle = vs.iloc[-1] if len(vs) else ""
                name = ns.iloc[-1] if len(ns) else ""
            u = CardUsage(card, vehicle, name, UNREGISTERED, 0.0, False, False)
        if g is not None:
            u.litres = round(float(g["litres"].sum()), 3)
            u.value = round(float(g["value"].sum()), 2)
            u.fills = len(g)
            u.daily = {int(d): float(v) for d, v in g.groupby(g["time"].dt.day)["litres"].sum().items()}
            u.first_use, u.last_use = g["time"].min(), g["time"].max()
        u.status = _status(u, bool(reg["is_active"]) if reg else False)
        return u

    for c in all_cards:
        if c["is_active"]:
            out.append(make(c["card_number"], c))
    for card in sorted(groups):
        reg = by_card.get(card)
        if reg is None or not reg["is_active"]:
            out.append(make(card, reg))
    return out

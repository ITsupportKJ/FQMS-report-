"""Numbers behind the dashboard and escort-vehicle analytics."""

from __future__ import annotations

import pandas as pd

from . import usage as U
from .db import Database
from .fqms import FqmsData


def dashboard(db: Database, data: FqmsData) -> dict:
    rows = U.compute_usage(db, data)
    used = [u for u in rows if u.fills]
    by_cat = {}
    for u in used:
        by_cat[u.category] = by_cat.get(u.category, 0.0) + u.litres
    daily = data.df.groupby(data.df["time"].dt.day)["litres"].sum().round(3)
    top = sorted(used, key=lambda u: u.litres, reverse=True)[:10]
    return {
        "period": data.period,
        "total_litres": round(sum(u.litres for u in used), 3),
        "total_value": round(sum(u.value for u in used), 2),
        "cards_used": len(used),
        "unregistered": [u.card for u in rows if not u.registered],
        "exceeded": [u for u in rows if u.status == U.EXCEEDED],
        "category_usage": {k: round(v, 3) for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])},
        "daily_usage": daily.to_dict(),
        "top_cards": top,
    }


def escort_summary(db: Database, data: FqmsData) -> pd.DataFrame:
    """One row per card flagged as an escort vehicle (set on the card, not in code)."""
    rows = [u for u in U.compute_usage(db, data) if u.is_escort]
    return pd.DataFrame([{
        "Card": u.card, "Vehicle": u.vehicle, "Name": u.name, "Fills": u.fills,
        "Litres": u.litres, "Value": u.value,
        "Avg fill (L)": round(u.litres / u.fills, 2) if u.fills else 0.0,
        "First use": u.first_use, "Last use": u.last_use,
    } for u in sorted(rows, key=lambda u: -u.litres)])

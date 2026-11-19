"""Getting cards into the system: from a customer's own Excel/CSV list, or from
the old Excel-template format used by the first customer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from .db import Database, _truthy
from .util import card_warning, clean_card

HEADERS = ["Card Number", "Vehicle Number", "Name", "Category", "Limit (L)", "Escort (yes/no)"]
ALIASES = {
    "card_number": ["card number", "card no", "card no.", "card", "card_id", "cardnumber"],
    "vehicle_number": ["vehicle number", "vehicle no", "vehicle", "vehicle_number", "plate"],
    "name": ["name", "driver", "holder", "description", "user"],
    "category": ["category", "group", "division", "department"],
    "limit_liters": ["limit (l)", "limit", "budget", "quota", "monthly limit", "fuel limit"],
    "is_escort": ["escort (yes/no)", "escort", "is escort", "escort vehicle"],
}


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    errors: list = field(default_factory=list)       # (row label, message)
    warnings: list = field(default_factory=list)


def write_cards_template(path) -> Path:
    """A blank sheet the customer can fill in and import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Cards"
    ws.append(HEADERS)
    ws.append(["7700000001", "AB-1234", "Example driver", "Management", 300, "no"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEF", (16, 18, 28, 20, 12, 16)):
        ws.column_dimensions[col].width = w
    wb.save(path)
    return Path(path)


def _read_table(path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p, dtype=object)
    return pd.read_excel(p, dtype=object)


def import_cards_file(db: Database, path, update_existing=False, create_categories=True) -> ImportResult:
    df = _read_table(path)
    lookup = {str(c).strip().lower(): c for c in df.columns}
    col = {}
    for field_name, names in ALIASES.items():
        col[field_name] = next((lookup[n] for n in names if n in lookup), None)
    if col["card_number"] is None:
        raise ValueError("No card number column found. Expected a column called "
                         "'Card Number'. Use the template from 'Download template'.")

    result, rows, labels = ImportResult(), [], []
    for i, rec in df.iterrows():
        def get(name):
            c = col[name]
            if c is None or pd.isna(rec[c]):
                return ""
            return rec[c]
        card = clean_card(get("card_number"))
        if not card and all(pd.isna(v) for v in rec.values):
            continue                                   # blank line
        lim = get("limit_liters")
        rows.append({"card_number": card, "vehicle_number": str(get("vehicle_number")),
                     "name": str(get("name")), "category": str(get("category")).strip(),
                     "limit_liters": lim if lim != "" else 0,
                     "is_escort": _truthy(get("is_escort"))})
        labels.append(f"row {i + 2}")
        w = card_warning(card)
        if w:
            result.warnings.append(f"row {i + 2}: {w}")
    out = db.add_cards_bulk(rows, update_existing=update_existing, create_categories=create_categories)
    result.added, result.updated = out["added"], out["updated"]
    result.errors = [(labels[i], msg) for i, msg in out["errors"]]
    return result


# --------------------------------------------------------------- legacy template
def read_legacy_template(path):
    """Parse the first customer's Excel template (category heading rows followed by
    card rows, in two column layouts). Returns (rows, categories_in_order)."""
    ws = load_workbook(path, data_only=True).active
    skip = {"GRAND TOTAL", "CARDS THAT DOESN'T INCLUDE IN THE TEMPLATE"}
    placeholder = {"NEW CARD - UPDATE TEMPLATE"}
    rows, categories, seen, current = [], [], set(), ""

    def text(v):
        return "" if v in (None, "") else str(v).strip()

    for r in range(2, ws.max_row + 1):
        v = [ws.cell(r, c).value for c in range(1, 5)]
        cards = [(i, clean_card(v[i])) for i in range(3)
                 if clean_card(v[i]).isdigit() and len(clean_card(v[i])) >= 5]
        if not cards:
            first = text(v[0])
            if first and not any(text(x) for x in v[1:3]) and first.upper() not in skip:
                current = first
                if first not in categories:
                    categories.append(first)
            continue
        idx, card = cards[0]
        if card in seen:
            continue
        seen.add(card)
        if idx == 0:        # [card, (blank), description, limit]
            vehicle, name = ("", text(v[2]) or text(v[1])) if not text(v[1]) \
                else (text(v[1]), text(v[2]))
        elif idx == 1:      # [label, card, vehicle, limit]
            vehicle, name = text(v[2]), text(v[0])
        else:
            vehicle, name = text(v[1]), text(v[0])
        if name.upper() in placeholder:
            name = ""
        try:
            limit = float(v[3]) if v[3] not in (None, "") else 0.0
        except (TypeError, ValueError):
            limit = 0.0
        rows.append({"card_number": card, "vehicle_number": vehicle, "name": name,
                     "category": current, "limit_liters": limit, "is_escort": False})
    return rows, categories


def import_legacy_template(db: Database, path, escort_cards=()) -> ImportResult:
    rows, categories = read_legacy_template(path)
    for name in categories:
        try:
            db.add_category(name)
        except Exception:
            pass
    escort = {clean_card(c) for c in escort_cards}
    for r in rows:
        r["is_escort"] = r["card_number"] in escort
    out = db.add_cards_bulk(rows, update_existing=False, create_categories=True)
    res = ImportResult(added=out["added"], updated=out["updated"])
    res.errors = [(rows[i]["card_number"], m) for i, m in out["errors"]]
    return res

"""Write the monthly fuel report (.xlsx) from a report profile.

Everything a client can change - columns, labels, order, colours, status
wording, sorting, title, formulas - lives in the profile (see profile.py).
This module only draws it."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import paths, profile as P, usage as U
from .db import Database
from .fqms import FqmsData
from .profile_store import ProfileStore

_thin = Side(style="thin", color="000000")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
CENTER = Alignment(horizontal="center", vertical="center")

_TEXT_KEY = {"ok": "ok_text", "exceeded": "over_limit_text", "no_limit": "no_limit_text",
             "new_card": "new_card_text", "inactive": "inactive_text", "near": "near_limit_text"}
_SORT = {"card_number": lambda u: u.card,
         "vehicle": lambda u: (u.vehicle or "").casefold(),
         "name": lambda u: (u.name or "").casefold(),
         "litres_desc": lambda u: -u.litres}


class ReportError(Exception):
    pass


@dataclass
class ReportResult:
    path: Path
    period: str
    total_litres: float
    total_value: float
    cards_with_usage: int
    registered_cards: int
    unknown_cards: list = field(default_factory=list)
    exceeded: list = field(default_factory=list)
    no_limit: list = field(default_factory=list)
    run_id: int = 0
    profile_name: str = ""


@dataclass
class _Col:
    key: str          # column id from the profile
    index: int        # 1-based sheet column
    label: object     # header text (the day number for day columns)
    width: float
    fmt: str
    group: str
    total: bool


def _plan_columns(profile, period) -> list:
    """Turn the profile's visible columns into sheet columns (day_grid expands
    to one column per day)."""
    year, month = (int(x) for x in period.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]
    cols = []
    for c in profile["columns"]:
        if not c["show"]:
            continue
        spec = P.COLUMNS[c["id"]]
        if c["id"] == "day_grid":
            first, last = P.parse_days(c["days"], days_in_month)
            for day in range(first, last + 1):
                cols.append(_Col("day_grid", len(cols) + 1, day, c["width"], c["format"], "days", True))
        else:
            cols.append(_Col(c["id"], len(cols) + 1, c["label"], c["width"], c["format"],
                             spec["group"], spec.get("total", False)))
    return cols


def _kind(u, rules) -> str:
    if u.status == U.NEW_CARD:
        return "new_card"
    if u.status == U.INACTIVE:
        return "inactive"
    if u.status == U.EXCEEDED:
        return "exceeded"
    if u.status == U.NO_LIMIT:
        return "ok" if rules["zero_limit"] == "show_ok" else "no_limit"
    pct = rules["warn_at_percent"]
    if pct and u.limit > 0 and u.litres >= u.limit * pct / 100:
        return "near"
    return "ok"


def _freeze(setting, cols, header_row):
    if setting == "none":
        return None
    if setting != "auto":
        return setting
    lead = 0                                    # leading identity columns stay in view
    for c in cols:
        if c.group != "id":
            break
        lead += 1
    return f"{get_column_letter(lead + 1)}{header_row + 1}" if lead else f"A{header_row + 1}"


def _style_row(ws, row, ncols, fill=None, font=None):
    for col in range(1, ncols + 1):
        cell = ws.cell(row, col)
        cell.border, cell.alignment = BORDER, CENTER
        if fill:
            cell.fill = fill
        if font:
            cell.font = font


def build_monthly_report(db: Database, data: FqmsData, out_dir=None, profile=None) -> ReportResult:
    """`profile` may be None (the saved default), a saved profile's name, or a
    profile dict."""
    if profile is None or isinstance(profile, str):
        prof = ProfileStore(db).get(profile)
    else:
        prof = P.normalize(profile)
    rules, style, output = prof["rules"], prof["style"], prof["output"]

    rows = U.compute_usage(db, data)

    # Safety net: every litre in the file must land in exactly one report row.
    file_l, file_rs = float(data.df["litres"].sum()), float(data.df["value"].sum())
    rep_l, rep_rs = sum(r.litres for r in rows), sum(r.value for r in rows)
    if abs(file_l - rep_l) > 0.01 or abs(file_rs - rep_rs) > 0.05:
        raise ReportError(f"Internal check failed: file has {file_l:.3f} L / {file_rs:.2f} but the "
                          f"report has {rep_l:.3f} L / {rep_rs:.2f}. No report was written.")

    cols = _plan_columns(prof, data.period)
    by_key = {c.key: c for c in cols}
    ncols = len(cols)
    header_row = 2 if prof["title"] else 1
    fills = {k: PatternFill("solid", fgColor=v) for k, v in style.items() if k.endswith("_fill")}
    over_font = Font(color=style["over_font"], bold=True)
    cat_colors = {c["name"].casefold(): c["color"] for c in db.list_categories(include_inactive=True)}

    wb = Workbook()
    ws = wb.active
    ws.title = output["sheet_name"]

    if prof["title"]:
        title = (prof["title"].replace("{org}", db.get_setting("org_name", "") or "")
                 .replace("{period}", data.period))
        ws.cell(1, 1, title).font = Font(bold=True, size=14)

    for col in cols:
        c = ws.cell(header_row, col.index, col.label if col.label != "" else None)
        c.font = Font(bold=True, color=style["day_header_font"] if col.key == "day_grid" else "000000")
        c.fill = fills["totals_fill" if col.group == "totals"
                       else "block_fill" if col.group == "block" else "header_fill"]
        c.alignment, c.border = CENTER, BORDER

    # Group cards into sections in database order; sort inside each section.
    sections: dict = {}
    for u in rows:
        if not rules["show_unused_cards"] and not u.fills:
            continue
        label = u.category if u.registered and u.status != U.INACTIVE else U.UNREGISTERED
        sections.setdefault(label, []).append(u)
    if prof["sorting"]["cards"] != "manual":
        for group in sections.values():
            group.sort(key=_SORT[prof["sorting"]["cards"]])

    r = header_row + 1
    for section, group in sections.items():
        if section == U.UNREGISTERED:
            fill = fills["over_fill"]
        else:
            color = cat_colors.get(section.casefold(), "") if style["use_category_colors"] else ""
            fill = PatternFill("solid", fgColor=color) if color else fills["section_fill"]
        _style_row(ws, r, ncols, fill, Font(bold=True))
        ws.cell(r, 1, section)
        r += 1

        for u in group:
            kind = _kind(u, rules)
            flagged = kind in ("exceeded", "new_card", "inactive")
            row_fill = (fills["unregistered_fill"] if not u.registered or u.status == U.INACTIVE
                        else fills["over_fill"] if kind == "exceeded"
                        else fills["warn_fill"] if kind == "near" else None)
            _style_row(ws, r, ncols, row_fill, over_font if flagged else None)

            values = {
                "card_number": u.card, "vehicle": u.vehicle, "holder": u.name, "category": section,
                "limit": round(u.limit, 2), "total_litres": u.litres, "total_value": u.value,
                "status": rules[_TEXT_KEY[kind]], "fills": u.fills,
                "avg_price": round(u.value / u.litres, 2) if u.litres else None,
                "last_fill": u.last_use.date() if u.last_use is not None else None,
                "block_limit": round(u.limit, 2), "block_actual": u.litres,
                "block_balance": u.balance,
            }
            for col in cols:
                cell = ws.cell(r, col.index)
                cell.value = u.daily.get(int(col.label)) if col.key == "day_grid" else values[col.key]
                if col.fmt:
                    cell.number_format = col.fmt
                if col.key in ("total_litres", "total_value"):
                    cell.fill = fills["over_fill"] if kind == "exceeded" else fills["totals_cell_fill"]
                elif col.group == "block":
                    cell.fill = fills["block_fill"]
                    cell.font = (Font(color="FF0000", bold=True) if col.key == "block_balance"
                                 else Font(color="000000"))

            if output["formulas"]:                       # let the client edit the grid in Excel
                def ref(key):
                    return f"{get_column_letter(by_key[key].index)}{r}"
                day_cols = [c for c in cols if c.key == "day_grid"]
                if "total_litres" in by_key and day_cols:
                    ws[ref("total_litres")] = (f"=SUM({get_column_letter(day_cols[0].index)}{r}:"
                                               f"{get_column_letter(day_cols[-1].index)}{r})")
                if "block_actual" in by_key and "total_litres" in by_key:
                    ws[ref("block_actual")] = f"={ref('total_litres')}"
                if all(k in by_key for k in ("block_limit", "block_actual", "block_balance")):
                    ws[ref("block_balance")] = (f'=IF({ref("block_limit")}>0,'
                                                f'{ref("block_limit")}-{ref("block_actual")},"")')
            r += 1

    if output["grand_total"]:
        total_row = r
        _style_row(ws, total_row, ncols, fills["grand_total_fill"], Font(bold=True))
        ws.cell(total_row, 1, output["grand_total_label"])
        first, last = header_row + 1, total_row - 1
        for col in cols:
            cell = ws.cell(total_row, col.index)
            if col.total and col.index != 1:
                letter = get_column_letter(col.index)
                cell.value = f"=SUM({letter}{first}:{letter}{last})" if last >= first else 0
                if col.fmt:
                    cell.number_format = col.fmt
            if col.group == "block":
                cell.fill = fills["block_fill"]
        if "status" in by_key:
            ws.cell(total_row, by_key["status"].index,
                    f"Unregistered cards: {sum(1 for u in rows if not u.registered)}")

    ws.freeze_panes = _freeze(style["freeze"], cols, header_row)
    for col in cols:
        ws.column_dimensions[get_column_letter(col.index)].width = col.width

    result = ReportResult(
        path=Path(), period=data.period, total_litres=round(rep_l, 3), total_value=round(rep_rs, 2),
        cards_with_usage=sum(1 for u in rows if u.fills), registered_cards=sum(1 for u in rows if u.registered),
        unknown_cards=[u.card for u in rows if not u.registered],
        exceeded=[u for u in rows if u.status == U.EXCEEDED],
        no_limit=[u for u in rows if u.status == U.NO_LIMIT],
        profile_name=prof["name"])

    if output["summary_sheet"]:
        _summary_sheet(wb, db, data, result)

    out = Path(out_dir) if out_dir else paths.reports_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{output['file_prefix']}_{data.period}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    wb.save(path)
    result.path = path
    result.run_id = db.log_run(data.period, data.source, path, result.total_litres,
                               result.total_value, result.cards_with_usage,
                               len(result.unknown_cards), len(result.exceeded))
    return result


def _summary_sheet(wb, db, data, res):
    ws = wb.create_sheet("Summary")
    org = db.get_setting("org_name", "")
    lines = [
        ("Organization", org or "(not set)"),
        ("Report month", data.period),
        ("Report profile", res.profile_name),
        ("Generated", f"{datetime.now():%Y-%m-%d %H:%M}"),
        ("Source file", data.source.name),
        (None, None),
        ("Transaction rows in file", data.rows_in_file),
        ("Rows used in this report", data.rows_used),
        ("Rows from other months (left out)", data.rows_other_months),
        (None, None),
        ("Total litres", res.total_litres),
        ("Total value (Rs.)", res.total_value),
        ("Cards with fuel usage", res.cards_with_usage),
        ("Cards over their limit", len(res.exceeded)),
        ("Active cards with no limit set", len(res.no_limit)),
        ("Cards not registered", len(res.unknown_cards)),
    ]
    for i, (k, v) in enumerate(lines, 1):
        if k:
            ws.cell(i, 1, k).font = Font(bold=True)
            ws.cell(i, 2, v)
    i = len(lines) + 2
    if res.unknown_cards:
        ws.cell(i, 1, "Unregistered card numbers").font = Font(bold=True)
        ws.cell(i, 2, ", ".join(res.unknown_cards)); i += 2
    if data.issues:
        ws.cell(i, 1, "Import notes").font = Font(bold=True); i += 1
        for issue in data.issues:
            ws.cell(i, 1, issue.level.upper()); ws.cell(i, 2, issue.message); i += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 90
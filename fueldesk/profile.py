"""Report profiles: everything a client can customise about the monthly report
(columns, labels, order, status wording, colours, sorting, output options) as
plain data.

A profile is a JSON-friendly dict. `normalize()` fills in defaults and rejects
mistakes with messages a person can act on, so the GUI, the CLI and imported
files all go through the same checks. Categories themselves live in the
database (one source of truth); a profile only carries an optional starter
list of them so a ready-made profile can set up a new client in one step."""

from __future__ import annotations

import copy
import json
import re

SCHEMA = 1


class ProfileError(ValueError):
    """A problem with a report profile that the user can fix (shown as-is)."""


# Every column a report can show. `group` picks the header colour (id and days
# use header_fill, totals use totals_fill, block uses block_fill); `total`
# columns get a SUM in the grand-total row; `fmt` is the Excel number format.
COLUMNS = {
    "card_number":   dict(label="Card Number",     width=18, group="id"),
    "vehicle":       dict(label="Vehicle Number",  width=20, group="id"),
    "holder":        dict(label="Name",            width=32, group="id"),
    "category":      dict(label="Category",        width=18, group="id"),
    "limit":         dict(label="Budget",          width=10, group="id", fmt="#,##0.00", total=True),
    "day_grid":      dict(label="Day",             width=8,  group="days", fmt="#,##0.###", total=True),
    "total_litres":  dict(label="TOTAL LTR",       width=14, group="totals", fmt="#,##0.###", total=True),
    "total_value":   dict(label="TOTAL Rs. Value", width=18, group="totals", fmt="#,##0.00", total=True),
    "status":        dict(label="STATUS",          width=28, group="totals"),
    "fills":         dict(label="FILLS",           width=8,  group="totals", fmt="0", total=True),
    "avg_price":     dict(label="AVG Rs./L",       width=12, group="totals", fmt="#,##0.00"),
    "last_fill":     dict(label="LAST FILL",       width=12, group="totals", fmt="yyyy-mm-dd"),
    "block_limit":   dict(label="BUDGET",          width=12, group="block", fmt="#,##0.00", total=True),
    "block_actual":  dict(label="ACTUAL",          width=12, group="block", fmt="#,##0.###", total=True),
    "block_balance": dict(label="BALANCE",         width=12, group="block", fmt="#,##0.00", total=True),
}
BLOCK = ("block_limit", "block_actual", "block_balance")      # what "limit_block" expands to

STANDARD_COLUMNS = ["card_number", "vehicle", "holder", "limit", "day_grid", "total_litres",
                    "total_value", "status", *BLOCK]

DEFAULT_RULES = dict(
    over_limit_text="EXCEEDED BUDGET", ok_text="OK", no_limit_text="NO LIMIT SET",
    new_card_text="NEW CARD - NOT REGISTERED", inactive_text="INACTIVE CARD - HAS USAGE",
    near_limit_text="NEAR LIMIT",
    zero_limit="show_no_limit",      # or "show_ok": a card with no limit just says OK
    unregistered="own_section",      # cards missing from the register get their own section
    warn_at_percent=0,               # 0 = off; 90 = flag cards that reached 90% of their limit
    show_unused_cards=True)

DEFAULT_SORTING = dict(cards="manual")  # manual | card_number | vehicle | name | litres_desc
SORT_MODES = ("manual", "card_number", "vehicle", "name", "litres_desc")

DEFAULT_STYLE = dict(
    header_fill="8EAADB", totals_fill="A9D18E", block_fill="FFFF00", section_fill="8EAADB",
    over_fill="FFC7CE", over_font="9C0006", warn_fill="FFEB9C", unregistered_fill="FFF2CC",
    totals_cell_fill="E2F0D9", grand_total_fill="F4B183", day_header_font="FF0000",
    freeze="auto",                   # "auto", "none" or a cell such as "E2"
    use_category_colors=True)

DEFAULT_OUTPUT = dict(
    formulas=False,                  # True: row totals are Excel formulas the client can edit
    grand_total=True, grand_total_label="GRAND TOTAL", summary_sheet=True,
    sheet_name="Fuel Report", file_prefix="Fuel_Report")

SECURITY_CATEGORIES = ["DIRECTORS", "DO", "SQO", "OTHER", "ESCORT VEHICLES",
                       "HIRED VEHICLES", "OTHER DIVISIONS"]

# Ready-made starting points. Installing one sets up the layout and categories.
PRESETS = {
    "standard": {"name": "Standard monthly report"},
    "security-company": {"name": "Security company report", "categories": SECURITY_CATEGORIES},
}

_TOP_KEYS = {"schema", "name", "title", "columns", "categories", "rules", "sorting", "style", "output"}
_COLUMN_KEYS = {"id", "label", "show", "width", "format", "days", "labels"}


# ---------------------------------------------------------------- small checks
def _bool(value, what):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ProfileError(f"{what} must be on or off.")


def _number(value, low, high, what):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ProfileError(f"{what} must be a number.") from None
    if isinstance(value, bool) or not low <= n <= high:
        raise ProfileError(f"{what} must be between {low:g} and {high:g}.")
    return int(n) if n.is_integer() else n


def _text(value, what, max_len=60, allow_empty=False):
    text = "" if value is None else str(value).strip()
    if not text and not allow_empty:
        raise ProfileError(f"{what} cannot be empty.")
    if len(text) > max_len:
        raise ProfileError(f"{what} is too long (maximum {max_len} characters).")
    return text


def normalize_color(value, allow_empty=False, what="Colour"):
    """'#8eaadb' / '8EAADB' -> '8EAADB'. Empty is allowed only where asked."""
    text = str(value or "").strip().lstrip("#").upper()
    if not text and allow_empty:
        return ""
    if not re.fullmatch(r"[0-9A-F]{6}", text):
        raise ProfileError(f"{what} '{value}' is not a colour like #8EAADB.")
    return text


def parse_days(spec, days_in_month=31):
    """'1-31' -> (1, 31); 'month' -> (1, days_in_month)."""
    text = str(spec).strip().lower()
    if text == "month":
        return 1, days_in_month
    m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", text)
    if not m or not 1 <= int(m[1]) <= int(m[2]) <= 31:
        raise ProfileError(f"Days '{spec}' must look like 1-31 (or 'month' for the report month's days).")
    return int(m[1]), int(m[2])


def _section(raw, defaults, name):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ProfileError(f"'{name}' must be a group of settings.")
    unknown = set(raw) - set(defaults)
    if unknown:
        raise ProfileError(f"Unknown setting in '{name}': {', '.join(sorted(unknown))}.")
    return {**defaults, **raw}


# ------------------------------------------------------------------ the parts
def _one_column(item, seen):
    cid = item.get("id")
    if cid not in COLUMNS:
        raise ProfileError(f"Unknown column '{cid}'. Available: {', '.join(COLUMNS)}.")
    if cid in seen:
        raise ProfileError(f"Column '{cid}' is listed twice.")
    seen.add(cid)
    spec = COLUMNS[cid]
    label = item.get("label")
    width = item.get("width")
    fmt = item.get("format")
    col = {
        "id": cid,
        "label": spec["label"] if label is None else _text(label, f"Label of '{cid}'", 40, allow_empty=True),
        "show": _bool(item.get("show", True), f"'show' of column '{cid}'"),
        "width": spec["width"] if width is None else _number(width, 4, 80, f"Width of '{cid}'"),
        "format": spec.get("fmt", "") if fmt in (None, "") else str(fmt),
    }
    if cid == "day_grid":
        text = str(item.get("days", "1-31")).strip().lower()
        parse_days(text)                                 # validates
        col["days"] = "month" if text == "month" else "{}-{}".format(*parse_days(text))
    return col


def _columns(raw):
    if not isinstance(raw, list) or not raw:
        raise ProfileError("The report needs at least one column.")
    out, seen = [], set()
    for item in raw:
        entry = {"id": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or "id" not in entry:
            raise ProfileError("Each column needs an id, for example {\"id\": \"card_number\"}.")
        unknown = set(entry) - _COLUMN_KEYS
        if unknown:
            raise ProfileError(f"Unknown setting for column '{entry['id']}': {', '.join(sorted(unknown))}.")
        if entry["id"] == "limit_block":                  # the classic Budget / Actual / Balance trio
            labels = entry.get("labels") or [COLUMNS[k]["label"] for k in BLOCK]
            if not isinstance(labels, (list, tuple)) or len(labels) != 3:
                raise ProfileError("'limit_block' needs three labels: limit, actual, balance.")
            parts = [{"id": k, "label": lab, "show": entry.get("show", True), "width": entry.get("width")}
                     for k, lab in zip(BLOCK, labels)]
        else:
            parts = [entry]
        out.extend(_one_column(p, seen) for p in parts)
    return out


def _categories(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProfileError("Categories must be a list.")
    out, seen = [], set()
    for item in raw:
        entry = {"name": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or set(entry) - {"name", "color"}:
            raise ProfileError("Each category needs a name and, optionally, a colour.")
        name = _text(entry.get("name"), "Category name", 60)
        if name.casefold() in seen:
            raise ProfileError(f"Category '{name}' is listed twice.")
        seen.add(name.casefold())
        out.append({"name": name, "color": normalize_color(
            entry.get("color", ""), allow_empty=True, what=f"Colour of category '{name}'")})
    return out


def _rules(raw):
    r = _section(raw, DEFAULT_RULES, "rules")
    for key in ("over_limit_text", "ok_text", "no_limit_text", "new_card_text",
                "inactive_text", "near_limit_text"):
        r[key] = _text(r[key], f"Status wording '{key}'", 40)
    if r["zero_limit"] not in ("show_no_limit", "show_ok"):
        raise ProfileError("zero_limit must be 'show_no_limit' or 'show_ok'.")
    if r["unregistered"] != "own_section":
        raise ProfileError("unregistered must be 'own_section'.")
    r["warn_at_percent"] = _number(r["warn_at_percent"], 0, 100, "Warn-at percentage")
    r["show_unused_cards"] = _bool(r["show_unused_cards"], "Show unused cards")
    return r


def _sorting(raw):
    s = _section(raw, DEFAULT_SORTING, "sorting")
    if s["cards"] not in SORT_MODES:
        raise ProfileError(f"Card sorting must be one of: {', '.join(SORT_MODES)}.")
    return s


def _style(raw):
    s = _section(raw, DEFAULT_STYLE, "style")
    for key in list(s):
        if key.endswith(("_fill", "_font")):
            s[key] = normalize_color(s[key], what=f"Colour '{key}'")
    s["use_category_colors"] = _bool(s["use_category_colors"], "Use category colours")
    freeze = str(s["freeze"]).strip()
    if freeze.lower() in ("auto", "none"):
        s["freeze"] = freeze.lower()
    elif re.fullmatch(r"[A-Za-z]{1,3}[1-9]\d*", freeze):
        s["freeze"] = freeze.upper()
    else:
        raise ProfileError("freeze must be 'auto', 'none' or a cell such as E2.")
    return s


def _output(raw):
    o = _section(raw, DEFAULT_OUTPUT, "output")
    for key in ("formulas", "grand_total", "summary_sheet"):
        o[key] = _bool(o[key], f"Output setting '{key}'")
    o["grand_total_label"] = _text(o["grand_total_label"], "Grand total label", 40)
    sheet = _text(o["sheet_name"], "Sheet name", 31)
    if re.search(r"[\[\]:*?/\\]", sheet):
        raise ProfileError("Sheet name cannot contain [ ] : * ? / \\")
    if o["summary_sheet"] and sheet.casefold() == "summary":
        raise ProfileError("The main sheet cannot also be called 'Summary'.")
    o["sheet_name"] = sheet
    prefix = _text(o["file_prefix"], "File name prefix", 40)
    if not re.fullmatch(r"[\w\- ]+", prefix):
        raise ProfileError("File name prefix can only use letters, digits, spaces, - and _.")
    o["file_prefix"] = prefix
    return o


# ------------------------------------------------------------------ public API
def normalize(raw=None) -> dict:
    """Validate a profile and fill in everything left out. Raises ProfileError."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ProfileError("A report profile must be a group of settings.")
    unknown = set(raw) - _TOP_KEYS
    if unknown:
        raise ProfileError(f"Unknown setting: {', '.join(sorted(unknown))}.")
    if raw.get("schema", SCHEMA) > SCHEMA:
        raise ProfileError("This profile was made by a newer version of the app. Please update.")
    raw = copy.deepcopy(raw)
    prof = {
        "schema": SCHEMA,
        "name": _text(raw.get("name") or "Standard monthly report", "Profile name", 60),
        "title": _text(raw.get("title", ""), "Title", 120, allow_empty=True),
        "columns": _columns(raw.get("columns", STANDARD_COLUMNS)),
        "categories": _categories(raw.get("categories")),
        "rules": _rules(raw.get("rules")),
        "sorting": _sorting(raw.get("sorting")),
        "style": _style(raw.get("style")),
        "output": _output(raw.get("output")),
    }
    shown = {c["id"] for c in prof["columns"] if c["show"]}
    if not shown:
        raise ProfileError("Show at least one column.")
    if not shown & {"card_number", "vehicle", "holder"}:
        raise ProfileError("Show at least one of Card Number, Vehicle Number or Name, "
                           "so each row can be recognised.")
    return prof


def default_profile() -> dict:
    return normalize({})


def preset(name) -> dict:
    key = str(name).strip().lower()
    if key not in PRESETS:
        raise ProfileError(f"Unknown preset '{name}'. Available: {', '.join(PRESETS)}.")
    return normalize(copy.deepcopy(PRESETS[key]))


def to_json(profile) -> str:
    return json.dumps(normalize(profile), indent=2, ensure_ascii=False)


def from_json(text) -> dict:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProfileError(f"That is not a valid profile file ({e.msg}, line {e.lineno}).") from None
    return normalize(raw)
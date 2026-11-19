"""Read and validate the FQMS transaction export.

Every customer uploads the same file layout, so there are no import profiles:
the file either has the expected columns or the user gets a clear message
saying exactly what is wrong."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .util import card_warning, clean_card

REQUIRED = ["Card_ID", "TRNX_Lit_Val", "TRNX_Rs_Value", "TRNX_Time"]
OPTIONAL = ["Vehicle_Number", "Name", "Unit_Price", "Station"]
_CANON = {c.lower(): c for c in REQUIRED + OPTIONAL}
EXCEL_EXT = (".xls", ".xlsx", ".xlsm")


class FqmsError(Exception):
    """The file cannot be used. The message is written for the end user."""


@dataclass
class Issue:
    level: str          # "warning" or "info"
    message: str


@dataclass
class FqmsData:
    source: Path
    df: pd.DataFrame                    # only the report month; columns below
    period: str                         # "2026-10"
    months_found: dict                  # {"2026-10": 812, "2026-11": 3}
    rows_in_file: int                   # transaction rows after the header
    rows_used: int
    issues: list = field(default_factory=list)

    @property
    def period_start(self) -> str:
        return f"{self.period}-01"

    @property
    def period_end(self) -> str:
        y, m = (int(x) for x in self.period.split("-"))
        return f"{self.period}-{calendar.monthrange(y, m)[1]:02d}"

    @property
    def rows_other_months(self) -> int:
        return sum(n for p, n in self.months_found.items() if p != self.period)


def _norm(value) -> str:
    return str(value).strip().lower().replace(" ", "_") if value is not None else ""


def _rows(index) -> str:
    """'rows 5, 9, 12 and 3 more' (Excel row numbers)."""
    shown = ", ".join(str(i) for i in list(index)[:5])
    extra = len(index) - 5
    return f"rows {shown}" + (f" and {extra} more" if extra > 0 else "")


def load(path, month=None) -> FqmsData:
    """Load an FQMS export. If it spans several months the busiest one is used
    unless `month` ('YYYY-MM') is given."""
    p = Path(path)
    if p.suffix.lower() not in EXCEL_EXT:
        raise FqmsError("Please choose the FQMS Excel export (.xls or .xlsx).")
    if not p.exists():
        raise FqmsError(f"The file '{p.name}' was not found.")
    try:
        raw = pd.read_excel(p, header=None, dtype=object)
    except ImportError:
        raise FqmsError("Reading .xls files needs the 'xlrd' package. "
                        "Save the file as .xlsx in Excel and try again.")
    except PermissionError:
        raise FqmsError(f"'{p.name}' is open in another program. Close it and try again.")
    except Exception as e:
        raise FqmsError(f"'{p.name}' could not be read as an Excel file ({e}).")

    # --- find the header row -------------------------------------------------
    header_at = next((i for i in range(min(len(raw), 50))
                      if "card_id" in {_norm(v) for v in raw.iloc[i].values}), None)
    if header_at is None:
        raise FqmsError("This does not look like an FQMS transaction export: "
                        "no 'Card_ID' column was found in the first 50 rows.")
    headers = [_CANON.get(_norm(v), str(v).strip()) for v in raw.iloc[header_at].values]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise FqmsError("The file is missing required column(s): " + ", ".join(missing) +
                        ".\nColumns found: " + ", ".join(h for h in headers if h and h != "nan"))

    body = raw.iloc[header_at + 1:].copy()
    body.columns = headers
    body.index = body.index + 1                      # -> Excel row numbers
    body = body.dropna(how="all")
    rows_in_file = len(body)
    issues: list[Issue] = []

    df = pd.DataFrame(index=body.index)
    df["card"] = body["Card_ID"].map(clean_card)
    for opt, col in (("Vehicle_Number", "vehicle"), ("Name", "name"), ("Station", "station")):
        df[col] = body[opt].map(lambda v: "" if pd.isna(v) else str(v).strip()) \
            if opt in body else ""
    df["unit_price"] = pd.to_numeric(body["Unit_Price"], errors="coerce") \
        if "Unit_Price" in body else float("nan")

    # --- rows without a card (footers, totals, blanks) ----------------------
    no_card = df["card"] == ""
    if no_card.any():
        issues.append(Issue("info", f"{int(no_card.sum())} row(s) without a Card_ID were ignored "
                                    f"({_rows(df.index[no_card])})."))
    keep = ~no_card

    # --- numbers --------------------------------------------------------------
    for src, dst, label in (("TRNX_Lit_Val", "litres", "litres"),
                            ("TRNX_Rs_Value", "value", "amount")):
        parsed = pd.to_numeric(body[src], errors="coerce")
        bad = parsed.isna() & keep          # blank or text such as 'n/a'
        if bad.any():
            issues.append(Issue("warning", f"{int(bad.sum())} row(s) have a missing or unreadable {label} "
                                           f"and were counted as 0 ({_rows(df.index[bad])})."))
        df[dst] = parsed.fillna(0.0)
    neg = keep & (df["litres"] < 0)
    if neg.any():
        issues.append(Issue("warning", f"{int(neg.sum())} row(s) have negative litres "
                                       f"(refunds?) and were included ({_rows(df.index[neg])})."))

    # --- dates ---------------------------------------------------------------
    df["time"] = pd.to_datetime(body["TRNX_Time"], errors="coerce")
    bad_time = keep & df["time"].isna()
    if bad_time.any():
        issues.append(Issue("warning", f"{int(bad_time.sum())} row(s) have no valid date/time and "
                                       f"were left out ({_rows(df.index[bad_time])})."))
    df = df[keep & df["time"].notna()].copy()
    if df.empty:
        raise FqmsError("The file has the right columns but no usable transactions.")

    # --- soft checks ---------------------------------------------------------
    odd = sorted({w for w in map(card_warning, df["card"].unique()) if w})
    if odd:
        issues.append(Issue("warning", " ".join(odd[:3]) +
                            (f" (+{len(odd) - 3} more)" if len(odd) > 3 else "")))
    dupes = df.duplicated(subset=["card", "time", "litres", "value"], keep=False)
    if dupes.any():
        issues.append(Issue("warning", f"{int(dupes.sum())} row(s) look like duplicates "
                                       f"(same card, time, litres and amount). They were all kept - "
                                       f"check the export if the totals look high."))

    # --- which month is this report for? ------------------------------------
    df["month"] = df["time"].dt.strftime("%Y-%m")
    months = df["month"].value_counts().sort_index().to_dict()
    if month:
        if month not in months:
            raise FqmsError(f"No transactions for {month}. The file covers: {', '.join(months)}.")
        period = month
    else:
        period = max(months, key=lambda m: (months[m], m))
    if len(months) > 1:
        others = ", ".join(f"{m} ({n})" for m, n in months.items() if m != period)
        issues.append(Issue("warning", f"The file covers several months. The report uses {period}; "
                                       f"these were left out: {others}."))
    df = df[df["month"] == period].drop(columns="month")
    df = df.rename_axis("row").reset_index()
    return FqmsData(source=p, df=df, period=period, months_found=months,
                    rows_in_file=rows_in_file, rows_used=len(df), issues=issues)

import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from openpyxl import load_workbook

from fueldesk import analytics, cards_io, fqms, usage as U
from fueldesk.db import CardError, Database
from fueldesk.report import build_monthly_report
from sample_data import make_fqms

CARDS = [f"77000000{n:02d}" for n in range(1, 21)]


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    for c in ("Management", "Operations", "Escort"):
        d.add_category(c)
    for i, card in enumerate(CARDS):
        d.add_card(card, f"VH-{i}", f"Holder {i}", ["Management", "Operations", "Escort"][i % 3],
                   limit_liters=100, is_escort=(i % 3 == 2))
    return d


def test_limit_history_by_month(db):
    db.set_limit(CARDS[0], 250, "2026-11-01")
    assert db.list_cards(as_of="2026-10-31")[0]["limit_liters"] == 100
    assert db.list_cards(as_of="2026-11-30")[0]["limit_liters"] == 250


def test_duplicate_and_bad_cards_rejected(db):
    with pytest.raises(CardError): db.add_card(CARDS[0], category="Operations")
    with pytest.raises(CardError): db.add_card("12ab", category="Operations")
    with pytest.raises(CardError): db.add_card("7700099999", category="Nope")


def test_removed_card_can_return(db):
    db.deactivate_card(CARDS[0])
    assert all(c["card_number"] != CARDS[0] for c in db.list_cards())
    db.add_card(CARDS[0], "NEW-1", "Back", "Operations", 50)
    assert db.get_card(CARDS[0])["is_active"] and db.get_card(CARDS[0])["vehicle_number"] == "NEW-1"


def test_report_totals_reconcile(db, tmp_path):
    src = tmp_path / "f.xlsx"
    df = make_fqms(src, CARDS, extra_cards=["7700088881", "7700088882"])
    data = fqms.load(src)
    res = build_monthly_report(db, data, tmp_path)
    assert res.total_litres == pytest.approx(df["TRNX_Lit_Val"].sum(), abs=0.01)
    assert res.total_value == pytest.approx(df["TRNX_Rs_Value"].sum(), abs=0.05)
    assert sorted(res.unknown_cards) == ["7700088881", "7700088882"]
    ws = load_workbook(res.path)["Fuel Report"]
    row_sum = sum(ws.cell(r, 36).value or 0 for r in range(2, ws.max_row)
                  if isinstance(ws.cell(r, 36).value, (int, float)))
    assert row_sum == pytest.approx(df["TRNX_Lit_Val"].sum(), abs=0.01)
    assert ws.cell(ws.max_row, 1).value == "GRAND TOTAL"
    assert ws.cell(ws.max_row, 36).value == f"=SUM(AJ2:AJ{ws.max_row - 1})"
    assert "Summary" in load_workbook(res.path).sheetnames


def test_exceeded_and_no_limit_status(db, tmp_path):
    db.set_limit(CARDS[1], 1, "2026-10-01")        # tiny limit -> exceeded
    db.set_limit(CARDS[2], 0, "2026-10-01")        # no limit
    src = tmp_path / "f.xlsx"; make_fqms(src, CARDS)
    rows = {u.card: u for u in U.compute_usage(db, fqms.load(src))}
    assert rows[CARDS[1]].status == U.EXCEEDED
    assert rows[CARDS[2]].status == U.NO_LIMIT and rows[CARDS[2]].balance is None


def test_old_month_uses_old_limit(db, tmp_path):
    db.set_limit(CARDS[3], 5, "2026-11-01")        # strict limit starting November
    src = tmp_path / "oct.xlsx"; make_fqms(src, CARDS, month="2026-10")
    oct_rows = {u.card: u for u in U.compute_usage(db, fqms.load(src))}
    assert oct_rows[CARDS[3]].limit == 100


def test_several_months_uses_busiest_and_warns(db, tmp_path):
    src = tmp_path / "f.xlsx"; make_fqms(src, CARDS, stray_next_month=2)
    data = fqms.load(src)
    assert data.period == "2026-10" and data.rows_other_months == 2
    assert any("several months" in i.message for i in data.issues)
    assert fqms.load(src, month="2026-11").rows_used == 2


def test_clear_errors(tmp_path):
    p = tmp_path / "x.xlsx"
    import pandas as pd
    pd.DataFrame([["a", "b"], [1, 2]]).to_excel(p, header=False, index=False)
    with pytest.raises(fqms.FqmsError, match="Card_ID"): fqms.load(p)
    pd.DataFrame([["Card_ID", "TRNX_Time"], ["7700000001", "2026-10-01"]]).to_excel(p, header=False, index=False)
    with pytest.raises(fqms.FqmsError, match="TRNX_Lit_Val"): fqms.load(p)
    with pytest.raises(fqms.FqmsError, match="Excel"): fqms.load(tmp_path / "x.txt")


def test_bad_rows_warn_not_crash(db, tmp_path):
    src = tmp_path / "f.xlsx"; make_fqms(src, CARDS, bad_rows=True)
    data = fqms.load(src)
    msgs = " ".join(i.message for i in data.issues)
    assert "unreadable" in msgs and "no valid date" in msgs


def test_card_list_import_and_template(tmp_path):
    db = Database(tmp_path / "fresh.db")             # a brand-new customer
    t = cards_io.write_cards_template(tmp_path / "t.xlsx")
    res = cards_io.import_cards_file(db, t)
    assert res.added == 1 and not res.errors
    assert db.get_card("7700000001")["category"] == "Management"
    res = cards_io.import_cards_file(db, t)         # second time: already exists
    assert res.added == 0 and len(res.errors) == 1


def test_analytics(db, tmp_path):
    src = tmp_path / "f.xlsx"; df = make_fqms(src, CARDS)
    data = fqms.load(src)
    d = analytics.dashboard(db, data)
    assert d["total_litres"] == pytest.approx(df["TRNX_Lit_Val"].sum(), abs=0.01)
    assert sum(d["category_usage"].values()) == pytest.approx(d["total_litres"], abs=0.01)
    esc = analytics.escort_summary(db, data)
    assert set(esc["Card"]) == {c for i, c in enumerate(CARDS) if i % 3 == 2}

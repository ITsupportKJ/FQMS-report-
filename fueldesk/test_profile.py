import sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from openpyxl import load_workbook

from fueldesk import fqms, profile as P, usage as U
from fueldesk.cli import main as cli_main
from fueldesk.db import SCHEMA_V1, Database
from fueldesk.profile_store import ProfileStore
from fueldesk.report import build_monthly_report
from sample_data import make_fqms

CARDS = [f"77000000{n:02d}" for n in range(1, 11)]

# The profile exactly as the client first wrote it down.
USER_JSON = """{
  "name": "Standard monthly report",
  "categories": ["DIRECTORS", "DO", "SQO", "OTHER", "ESCORT VEHICLES", "HIRED VEHICLES", "OTHER DIVISIONS"],
  "columns": [
    {"id": "card_number", "label": "Card Number"},
    {"id": "vehicle", "label": "Vehicle Number"},
    {"id": "holder", "label": "Name"},
    {"id": "limit", "label": "Budget"},
    {"id": "day_grid", "days": "1-31"},
    {"id": "total_litres", "label": "TOTAL LTR"},
    {"id": "total_value", "label": "TOTAL Rs. Value"},
    {"id": "status", "label": "STATUS"},
    {"id": "limit_block", "labels": ["BUDGET", "ACTUAL", "BALANCE"]}
  ],
  "rules": {"over_limit_text": "EXCEEDED BUDGET", "ok_text": "OK", "zero_limit": "show_no_limit", "unregistered": "own_section"},
  "style": {"header_fill": "#8EAADB", "totals_fill": "#A9D18E", "over_fill": "#FFC7CE", "grand_total_fill": "#F4B183", "freeze": "E2"},
  "output": {"formulas": false, "grand_total": true, "summary_sheet": true}
}"""

OCT_HEADERS = ["Card Number", "Vehicle Number", "Name", "Budget", *range(1, 32), "TOTAL LTR",
               "TOTAL Rs. Value", "STATUS", "BUDGET", "ACTUAL", "BALANCE"]


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    for c in ("Management", "Operations", "Escort"):
        d.add_category(c)
    for i, card in enumerate(CARDS):
        d.add_card(card, f"VH-{i}", f"Holder {i}", ["Management", "Operations", "Escort"][i % 3],
                   limit_liters=100)
    return d


def _data(tmp_path, month="2026-10", cards=CARDS):
    src = tmp_path / f"{month}.xlsx"
    make_fqms(src, cards, month=month)
    return fqms.load(src)


def _find_row(ws, col, value):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == value)


# ------------------------------------------------------------------ profiles
def test_clients_own_profile_is_accepted():
    prof = P.from_json(USER_JSON)
    assert [c["id"] for c in prof["columns"]] == [
        "card_number", "vehicle", "holder", "limit", "day_grid", "total_litres", "total_value",
        "status", "block_limit", "block_actual", "block_balance"]
    assert [c["label"] for c in prof["columns"] if c["id"].startswith("block_")] == ["BUDGET", "ACTUAL", "BALANCE"]
    assert len(prof["categories"]) == 7 and prof["categories"][0] == {"name": "DIRECTORS", "color": ""}
    assert prof["style"]["freeze"] == "E2" and prof["style"]["header_fill"] == "8EAADB"


def test_roundtrip_is_stable():
    prof = P.default_profile()
    assert P.from_json(P.to_json(prof)) == prof


@pytest.mark.parametrize("raw, message", [
    ({"columns": [{"id": "nope"}]}, "Unknown column 'nope'"),
    ({"columns": ["card_number", "card_number"]}, "listed twice"),
    ({"columns": [{"id": "day_grid", "days": "5-2"}]}, "must look like 1-31"),
    ({"columns": ["day_grid"]}, "at least one of Card Number"),
    ({"columns": [{"id": "card_number", "show": False}]}, "at least one column"),
    ({"style": {"over_fill": "red"}}, "not a colour"),
    ({"style": {"freeze": "banana"}}, "freeze must be"),
    ({"rules": {"warn_at_percent": 150}}, "between 0 and 100"),
    ({"rules": {"zero_limit": "maybe"}}, "zero_limit"),
    ({"rules": {"ok_texts": "x"}}, "Unknown setting in 'rules'"),
    ({"sorting": {"cards": "random"}}, "Card sorting"),
    ({"output": {"sheet_name": "a/b"}}, "Sheet name"),
    ({"output": {"sheet_name": "Summary"}}, "cannot also be called"),
    ({"colour": "x"}, "Unknown setting"),
    ({"categories": ["A", "a"]}, "listed twice"),
    ({"schema": 99}, "newer version"),
])
def test_mistakes_get_clear_messages(raw, message):
    with pytest.raises(P.ProfileError, match=message):
        P.normalize(raw)


def test_bad_json_file():
    with pytest.raises(P.ProfileError, match="not a valid profile file"):
        P.from_json("{ nope")


# --------------------------------------------------------------------- store
def test_store_save_default_delete(db):
    store = ProfileStore(db)
    assert store.names() == [] and store.get()["name"] == "Standard monthly report"
    store.save({"name": "A"})
    store.save({"name": "B", "title": "Hello"})
    assert store.default_name() == "A"                      # first saved becomes the default
    store.set_default("b")                                  # names are case-insensitive
    assert store.default_name() == "B" and store.get()["title"] == "Hello"
    store.save({"name": "B", "title": "Changed"})           # same name replaces
    assert store.names() == ["B", "A"] and store.get("B")["title"] == "Changed"
    with pytest.raises(P.ProfileError, match="not found"):
        store.get("Nope")
    assert store.delete("A") and not store.delete("A")


def test_preset_creates_categories_and_is_repeatable(db, tmp_path):
    fresh = Database(tmp_path / "fresh.db")
    store = ProfileStore(fresh)
    store.install_preset("security-company")
    store.install_preset("security-company")                # running it twice is harmless
    assert fresh.category_names() == P.SECURITY_CATEGORIES
    assert store.default_name() == "Security company report"
    with pytest.raises(P.ProfileError, match="Unknown preset"):
        store.install_preset("nope")


def test_export_import_moves_a_setup_between_installations(db, tmp_path):
    store = ProfileStore(db)
    store.save({"name": "Mgmt", "title": "{org}"}, make_default=True)
    store.set_category_color("Management", "#ff0000")
    text = P.to_json(store.export_bundle())
    other = Database(tmp_path / "other.db")
    ProfileStore(other).import_bundle(P.from_json(text))
    assert other.category_names() == ["Management", "Operations", "Escort"]
    assert other.list_categories()[0]["color"] == "FF0000"
    assert ProfileStore(other).get()["title"] == "{org}"


def test_old_database_upgrades_in_place(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_V1)
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO categories(name) VALUES ('Old')")
    con.commit(); con.close()
    db = Database(path)
    cat = db.list_categories()[0]
    assert cat["name"] == "Old" and cat["color"] == "" and ProfileStore(db).names() == []


# -------------------------------------------------------------------- report
def test_default_profile_reproduces_the_october_layout(db, tmp_path):
    res = build_monthly_report(db, _data(tmp_path), tmp_path)
    ws = load_workbook(res.path)["Fuel Report"]
    assert [c.value for c in ws[1]] == OCT_HEADERS
    assert ws.freeze_panes == "E2"
    assert ws["A1"].fill.fgColor.rgb.endswith("8EAADB")
    assert ws["AJ1"].fill.fgColor.rgb.endswith("A9D18E")
    assert ws["AM1"].fill.fgColor.rgb.endswith("FFFF00")
    assert ws.cell(ws.max_row, 1).value == "GRAND TOTAL"
    assert ws.cell(ws.max_row, 1).fill.fgColor.rgb.endswith("F4B183")


def test_clients_own_profile_builds_the_same_layout(db, tmp_path):
    res = build_monthly_report(db, _data(tmp_path), tmp_path, profile=P.from_json(USER_JSON))
    assert [c.value for c in load_workbook(res.path)["Fuel Report"][1]] == OCT_HEADERS


def test_customised_report(db, tmp_path):
    db.set_setting("org_name", "Acme")
    prof = {"name": "Mgmt", "title": "{org} fuel {period}",
            "columns": [{"id": "holder", "label": "Holder"}, "card_number",
                        {"id": "day_grid", "days": "month"},
                        {"id": "total_litres", "label": "Litres"}, "status",
                        {"id": "block_balance", "label": "Left"}],
            "style": {"freeze": "none"},
            "output": {"formulas": True, "sheet_name": "Mgmt", "file_prefix": "Mgmt report"}}
    res = build_monthly_report(db, _data(tmp_path, "2026-11"), tmp_path, profile=prof)
    assert res.path.name.startswith("Mgmt report_2026-11_") and res.profile_name == "Mgmt"
    ws = load_workbook(res.path)["Mgmt"]
    assert ws["A1"].value == "Acme fuel 2026-11"
    headers = [c.value for c in ws[2]]
    assert headers == ["Holder", "Card Number", *range(1, 31), "Litres", "STATUS", "Left"]
    assert ws.freeze_panes is None
    row = _find_row(ws, 1, "Holder 0")
    assert ws.cell(row, 33).value == f"=SUM(C{row}:AF{row})"
    assert isinstance(ws.cell(row, 35).value, (int, float))      # no Budget column shown -> plain value


def test_formulas_for_the_full_budget_block(db, tmp_path):
    res = build_monthly_report(db, _data(tmp_path), tmp_path, profile={"output": {"formulas": True}})
    ws = load_workbook(res.path)["Fuel Report"]
    row = _find_row(ws, 1, CARDS[0])
    assert ws.cell(row, 36).value == f"=SUM(E{row}:AI{row})"
    assert ws.cell(row, 40).value == f"=AJ{row}"
    assert ws.cell(row, 41).value == f'=IF(AM{row}>0,AM{row}-AN{row},"")'


def test_status_wording_zero_limit_and_near_limit(db, tmp_path):
    db.set_limit(CARDS[1], 1, "2026-10-01")                 # tiny -> exceeded
    db.set_limit(CARDS[2], 0, "2026-10-01")                 # no limit at all
    data = _data(tmp_path)
    used = {u.card: u for u in U.compute_usage(db, data)}
    db.set_limit(CARDS[3], round(used[CARDS[3]].litres * 1.05, 3), "2026-10-01")   # ~95% used

    def statuses(**rules):
        ws = load_workbook(build_monthly_report(db, data, tmp_path, profile={"rules": rules}).path)["Fuel Report"]
        return {ws.cell(r, 1).value: ws.cell(r, 38).value for r in range(2, ws.max_row)}

    s = statuses(warn_at_percent=90)
    assert s[CARDS[1]] == "EXCEEDED BUDGET" and s[CARDS[2]] == "NO LIMIT SET" and s[CARDS[3]] == "NEAR LIMIT"
    s = statuses(zero_limit="show_ok", over_limit_text="OVER", near_limit_text="CLOSE")
    assert s[CARDS[1]] == "OVER" and s[CARDS[2]] == "OK" and s[CARDS[3]] == "OK"


def test_sorting_inside_a_category(db, tmp_path):
    res = build_monthly_report(db, _data(tmp_path), tmp_path, profile={"sorting": {"cards": "litres_desc"}})
    ws = load_workbook(res.path)["Fuel Report"]
    start = _find_row(ws, 1, "Management")
    values = []
    for r in range(start + 1, ws.max_row):
        if ws.cell(r, 3).value is None and ws.cell(r, 2).value is None:   # next section header
            break
        values.append(ws.cell(r, 36).value)
    assert len(values) > 2 and values == sorted(values, reverse=True)


def test_unused_cards_can_be_hidden(db, tmp_path):
    db.add_card("7700099001", "NOUSE-1", "Idle car", "Operations", limit_liters=50)
    data = _data(tmp_path)
    shown = load_workbook(build_monthly_report(db, data, tmp_path).path)["Fuel Report"]
    hidden = load_workbook(build_monthly_report(
        db, data, tmp_path, profile={"rules": {"show_unused_cards": False}}).path)["Fuel Report"]
    assert any(shown.cell(r, 1).value == "7700099001" for r in range(1, shown.max_row))
    assert not any(hidden.cell(r, 1).value == "7700099001" for r in range(1, hidden.max_row))


def test_category_colour_and_rename_keep_working(db, tmp_path):
    store = ProfileStore(db)
    store.set_category_color("Management", "#00ff00")
    db.rename_category(store.find_category("Management")["id"], "Directors")
    res = build_monthly_report(db, _data(tmp_path), tmp_path)
    ws = load_workbook(res.path)["Fuel Report"]
    section = _find_row(ws, 1, "Directors")
    assert ws.cell(section, 1).fill.fgColor.rgb.endswith("00FF00")
    off = build_monthly_report(db, _data(tmp_path), tmp_path, profile={"style": {"use_category_colors": False}})
    ws = load_workbook(off.path)["Fuel Report"]
    assert ws.cell(_find_row(ws, 1, "Directors"), 1).fill.fgColor.rgb.endswith("8EAADB")


def test_command_line(db, tmp_path, capsys):
    path = str(db.path)
    assert cli_main(["--db", path, "categories", "--add", "Extra", "--move", "Extra", "1",
                     "--color", "Extra", "#123456"]) == 0
    assert capsys.readouterr().out.splitlines()[0].split()[:2] == ["1", "Extra"]
    assert cli_main(["--db", path, "profile", "preset", "standard"]) == 0
    assert cli_main(["--db", path, "profile", "export", str(tmp_path / "p.json")]) == 0
    assert cli_main(["--db", path, "profile", "import", str(tmp_path / "p.json")]) == 0
    assert cli_main(["--db", path, "profile", "use", "Nope"]) == 1
    assert "not found" in capsys.readouterr().err
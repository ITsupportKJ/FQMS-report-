"""SQLite storage: cards, customer-defined categories, fuel limits with history,
settings and a log of generated reports."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import paths
from .util import card_problem, clean_card

EPOCH = "0000-01-01"      # "since forever" - the first limit a card ever had

SCHEMA_V1 = """
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    card_number    TEXT NOT NULL UNIQUE,
    vehicle_number TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL DEFAULT '',
    category_id    INTEGER REFERENCES categories(id),
    limit_liters   REAL NOT NULL DEFAULT 0,
    is_escort      INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE limit_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id        INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    limit_liters   REAL NOT NULL,
    effective_from TEXT NOT NULL,
    note           TEXT NOT NULL DEFAULT ''
);
CREATE TABLE report_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    period         TEXT NOT NULL,
    source_file    TEXT NOT NULL,
    output_path    TEXT NOT NULL,
    total_litres   REAL NOT NULL,
    total_value    REAL NOT NULL,
    cards_used     INTEGER NOT NULL,
    unknown_cards  INTEGER NOT NULL,
    exceeded_cards INTEGER NOT NULL
);
CREATE INDEX idx_cards_category ON cards(category_id);
CREATE INDEX idx_limit_history  ON limit_history(card_id, effective_from);
"""

SCHEMA_V2 = """
ALTER TABLE categories ADD COLUMN color TEXT NOT NULL DEFAULT '';
CREATE TABLE report_profiles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    data       TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# Add one entry per future schema change; they are applied in order.
MIGRATIONS = {1: SCHEMA_V1, 2: SCHEMA_V2}


class CardError(ValueError):
    """A problem the user can fix (shown in a dialog as-is)."""


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "x")


class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path else paths.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # ------------------------------------------------------------------ core
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate(self):
        with self._conn() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            for target in sorted(MIGRATIONS):
                if target > version:
                    c.executescript(MIGRATIONS[target])
                    c.execute(f"PRAGMA user_version = {target}")

    def backup_to(self, dest) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(self.path)
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
            src.close()
        return dest

    # -------------------------------------------------------------- settings
    def get_setting(self, key, default=None):
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key, value):
        with self._conn() as c:
            c.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    # ------------------------------------------------------------ categories
    def list_categories(self, include_inactive=False):
        sql = "SELECT * FROM categories"
        if not include_inactive:
            sql += " WHERE is_active=1"
        sql += " ORDER BY sort_order, id"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql)]

    def category_names(self):
        return [c["name"] for c in self.list_categories()]

    def add_category(self, name) -> int:
        name = (name or "").strip()
        if not name:
            raise CardError("Category name cannot be empty.")
        with self._conn() as c:
            row = c.execute("SELECT id, is_active FROM categories WHERE name=?", (name,)).fetchone()
            if row and row["is_active"]:
                raise CardError(f"Category '{name}' already exists.")
            if row:   # a hidden category with this name: bring it back
                c.execute("UPDATE categories SET is_active=1 WHERE id=?", (row["id"],))
                return row["id"]
            return self._insert_category(c, name)

    @staticmethod
    def _insert_category(c, name) -> int:
        order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories").fetchone()[0]
        return c.execute("INSERT INTO categories(name, sort_order) VALUES (?, ?)",
                         (name, order)).lastrowid

    def rename_category(self, category_id, new_name):
        new_name = (new_name or "").strip()
        if not new_name:
            raise CardError("Category name cannot be empty.")
        with self._conn() as c:
            clash = c.execute("SELECT id FROM categories WHERE name=? AND id<>?",
                              (new_name, category_id)).fetchone()
            if clash:
                raise CardError(f"Category '{new_name}' already exists.")
            c.execute("UPDATE categories SET name=? WHERE id=?", (new_name, category_id))

    def reorder_categories(self, ordered_ids):
        with self._conn() as c:
            for position, cid in enumerate(ordered_ids):
                c.execute("UPDATE categories SET sort_order=? WHERE id=?", (position, cid))

    def remove_category(self, category_id) -> str:
        """Delete an empty category, or hide one that still has cards."""
        with self._conn() as c:
            used = c.execute("SELECT COUNT(*) FROM cards WHERE category_id=?",
                             (category_id,)).fetchone()[0]
            if used:
                c.execute("UPDATE categories SET is_active=0 WHERE id=?", (category_id,))
                return "hidden"
            c.execute("DELETE FROM categories WHERE id=?", (category_id,))
            return "deleted"

    def _category_id(self, c, name, create):
        name = (name or "").strip()
        if not name:
            return None
        row = c.execute("SELECT id, is_active FROM categories WHERE name=?", (name,)).fetchone()
        if row:
            if not row["is_active"]:
                c.execute("UPDATE categories SET is_active=1 WHERE id=?", (row["id"],))
            return row["id"]
        if not create:
            raise CardError(f"Category '{name}' does not exist. Available: "
                            f"{', '.join(self.category_names()) or '(none yet)'}")
        return self._insert_category(c, name)

    # ----------------------------------------------------------------- cards
    def list_cards(self, include_inactive=False, as_of=None):
        """Cards in report order. With as_of ('YYYY-MM-DD') each card carries the
        limit that applied on that date; otherwise its current limit."""
        limit_expr = "c.limit_liters"
        params = {}
        if as_of:
            limit_expr = ("COALESCE((SELECT h.limit_liters FROM limit_history h "
                          "WHERE h.card_id=c.id AND h.effective_from<=:asof "
                          "ORDER BY h.effective_from DESC, h.id DESC LIMIT 1), c.limit_liters)")
            params["asof"] = as_of
        sql = (f"SELECT c.id, c.card_number, c.vehicle_number, c.name, c.category_id, "
               f"COALESCE(cat.name, '') AS category, {limit_expr} AS limit_liters, "
               f"c.is_escort, c.is_active "
               f"FROM cards c LEFT JOIN categories cat ON cat.id = c.category_id ")
        if not include_inactive:
            sql += "WHERE c.is_active=1 "
        sql += "ORDER BY cat.sort_order IS NULL, cat.sort_order, c.id"
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(sql, params)]
        for r in rows:
            r["is_escort"] = bool(r["is_escort"])
            r["is_active"] = bool(r["is_active"])
        return rows

    def get_card(self, card_number):
        card = clean_card(card_number)
        return next((c for c in self.list_cards(include_inactive=True)
                     if c["card_number"] == card), None)

    def _save_card(self, c, card, vehicle, name, category, limit, is_escort,
                   update_existing, create_categories) -> str:
        card = clean_card(card)
        problem = card_problem(card)
        if problem:
            raise CardError(problem)
        try:
            limit = float(limit or 0)
        except (TypeError, ValueError):
            raise CardError(f"Limit for card {card} must be a number.")
        if limit < 0:
            raise CardError(f"Limit for card {card} cannot be negative.")
        cat_id = self._category_id(c, category, create_categories)
        vehicle, name = (vehicle or "").strip(), (name or "").strip()
        row = c.execute("SELECT id, is_active, limit_liters FROM cards WHERE card_number=?",
                        (card,)).fetchone()
        today = date.today().isoformat()
        if row is None:
            cid = c.execute(
                "INSERT INTO cards(card_number, vehicle_number, name, category_id, "
                "limit_liters, is_escort) VALUES (?,?,?,?,?,?)",
                (card, vehicle, name, cat_id, limit, int(bool(is_escort)))).lastrowid
            c.execute("INSERT INTO limit_history(card_id, limit_liters, effective_from, note) "
                      "VALUES (?,?,?,?)", (cid, limit, EPOCH, "initial limit"))
            return "added"
        if row["is_active"] and not update_existing:
            raise CardError(f"Card {card} already exists.")
        c.execute("UPDATE cards SET vehicle_number=?, name=?, category_id=?, is_escort=?, "
                  "is_active=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  (vehicle, name, cat_id, int(bool(is_escort)), row["id"]))
        if abs(limit - row["limit_liters"]) > 1e-9:
            self._write_limit(c, row["id"], limit, today, "updated")
        return "updated"

    def add_card(self, card_number, vehicle_number="", name="", category="",
                 limit_liters=0, is_escort=False, create_category=False):
        with self._conn() as c:
            self._save_card(c, card_number, vehicle_number, name, category, limit_liters,
                            is_escort, update_existing=False, create_categories=create_category)
        return clean_card(card_number)

    def add_cards_bulk(self, rows, update_existing=False, create_categories=False):
        """rows: dicts with card_number, vehicle_number, name, category, limit_liters,
        is_escort. One transaction; bad rows are reported, good rows still saved.
        Returns {'added', 'updated', 'errors': [(index, message)]}."""
        result = {"added": 0, "updated": 0, "errors": []}
        with self._conn() as c:
            for i, r in enumerate(rows):
                try:
                    c.execute("SAVEPOINT row")
                    outcome = self._save_card(
                        c, r.get("card_number"), r.get("vehicle_number"), r.get("name"),
                        r.get("category"), r.get("limit_liters"), r.get("is_escort"),
                        update_existing, create_categories)
                    c.execute("RELEASE row")
                    result[outcome] += 1
                except CardError as e:
                    c.execute("ROLLBACK TO row")
                    c.execute("RELEASE row")
                    result["errors"].append((i, str(e)))
        return result

    def update_card(self, card_number, vehicle_number=None, name=None, category=None,
                    is_escort=None, is_active=None, create_category=False):
        card = clean_card(card_number)
        with self._conn() as c:
            row = c.execute("SELECT id FROM cards WHERE card_number=?", (card,)).fetchone()
            if not row:
                raise CardError(f"Card {card} not found.")
            sets, vals = [], []
            if vehicle_number is not None:
                sets.append("vehicle_number=?"); vals.append(vehicle_number.strip())
            if name is not None:
                sets.append("name=?"); vals.append(name.strip())
            if category is not None:
                sets.append("category_id=?"); vals.append(self._category_id(c, category, create_category))
            if is_escort is not None:
                sets.append("is_escort=?"); vals.append(int(bool(is_escort)))
            if is_active is not None:
                sets.append("is_active=?"); vals.append(int(bool(is_active)))
            if sets:
                sets.append("updated_at=CURRENT_TIMESTAMP")
                c.execute(f"UPDATE cards SET {', '.join(sets)} WHERE id=?", (*vals, row["id"]))

    def deactivate_card(self, card_number):
        """Soft delete: the card disappears from reports but its history stays."""
        self.update_card(card_number, is_active=False)

    # ---------------------------------------------------------------- limits
    def _write_limit(self, c, card_id, liters, effective_from, note):
        c.execute("INSERT INTO limit_history(card_id, limit_liters, effective_from, note) "
                  "VALUES (?,?,?,?)", (card_id, liters, effective_from, note))
        current = c.execute(
            "SELECT limit_liters FROM limit_history WHERE card_id=? AND effective_from<=? "
            "ORDER BY effective_from DESC, id DESC LIMIT 1",
            (card_id, date.today().isoformat())).fetchone()
        if current:
            c.execute("UPDATE cards SET limit_liters=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (current["limit_liters"], card_id))

    def set_limit(self, card_number, liters, effective_from=None, note=""):
        """Change a card's monthly limit from a given date. Reports for earlier
        months keep the limit that applied then."""
        card = clean_card(card_number)
        try:
            liters = float(liters)
        except (TypeError, ValueError):
            raise CardError("Limit must be a number.")
        if liters < 0:
            raise CardError("Limit cannot be negative.")
        effective_from = effective_from or date.today().isoformat()
        try:
            date.fromisoformat(effective_from)
        except ValueError:
            raise CardError("Effective date must look like 2026-11-01.")
        with self._conn() as c:
            row = c.execute("SELECT id FROM cards WHERE card_number=?", (card,)).fetchone()
            if not row:
                raise CardError(f"Card {card} not found.")
            self._write_limit(c, row["id"], liters, effective_from, note)

    def limit_history(self, card_number):
        with self._conn() as c:
            rows = c.execute(
                "SELECT h.effective_from, h.limit_liters, h.note FROM limit_history h "
                "JOIN cards c ON c.id=h.card_id WHERE c.card_number=? "
                "ORDER BY h.effective_from, h.id", (clean_card(card_number),))
            return [dict(r) for r in rows]

    # ---------------------------------------------------------- report runs
    def log_run(self, period, source_file, output_path, total_litres, total_value,
                cards_used, unknown_cards, exceeded_cards) -> int:
        with self._conn() as c:
            return c.execute(
                "INSERT INTO report_runs(period, source_file, output_path, total_litres, "
                "total_value, cards_used, unknown_cards, exceeded_cards) VALUES (?,?,?,?,?,?,?,?)",
                (period, str(source_file), str(output_path), total_litres, total_value,
                 cards_used, unknown_cards, exceeded_cards)).lastrowid

    def list_runs(self, limit=50):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM report_runs ORDER BY id DESC LIMIT ?", (limit,))]
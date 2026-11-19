"""Saving report profiles in the database, plus the category helpers that go
with them (colours, and creating a client's starter categories from a profile)."""

from __future__ import annotations

from . import profile as P
from .db import CardError, Database


class ProfileStore:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------- profiles
    def names(self) -> list:
        with self.db._conn() as c:
            return [r["name"] for r in c.execute(
                "SELECT name FROM report_profiles ORDER BY is_default DESC, name")]

    def default_name(self):
        with self.db._conn() as c:
            row = c.execute("SELECT name FROM report_profiles WHERE is_default=1").fetchone()
        return row["name"] if row else None

    def get(self, name=None) -> dict:
        """A saved profile by name; with no name, the default one. If nothing has
        been saved yet, the built-in standard layout."""
        with self.db._conn() as c:
            if name:
                row = c.execute("SELECT data FROM report_profiles WHERE name=?",
                                (name.strip(),)).fetchone()
            else:
                row = c.execute("SELECT data FROM report_profiles WHERE is_default=1").fetchone()
        if row:
            return P.from_json(row["data"])
        if name:
            raise P.ProfileError(f"Report profile '{name}' not found. "
                                 f"Available: {', '.join(self.names()) or '(none saved yet)'}.")
        return P.default_profile()

    def save(self, profile, make_default=False) -> dict:
        """Validate and store a profile (replacing one with the same name). The
        first profile saved becomes the default. Categories are not stored here:
        the database is their single source of truth."""
        prof = P.normalize(profile)
        text = P.to_json({**prof, "categories": []})
        with self.db._conn() as c:
            row = c.execute("SELECT id FROM report_profiles WHERE name=?", (prof["name"],)).fetchone()
            if row:
                pid = row["id"]
                c.execute("UPDATE report_profiles SET data=?, updated_at=CURRENT_TIMESTAMP "
                          "WHERE id=?", (text, pid))
            else:
                pid = c.execute("INSERT INTO report_profiles(name, data) VALUES (?, ?)",
                                (prof["name"], text)).lastrowid
            has_default = c.execute("SELECT 1 FROM report_profiles WHERE is_default=1").fetchone()
            if make_default or not has_default:
                c.execute("UPDATE report_profiles SET is_default = (id = ?)", (pid,))
        return prof

    def set_default(self, name):
        with self.db._conn() as c:
            row = c.execute("SELECT id FROM report_profiles WHERE name=?", (name.strip(),)).fetchone()
            if not row:
                raise P.ProfileError(f"Report profile '{name}' not found.")
            c.execute("UPDATE report_profiles SET is_default = (id = ?)", (row["id"],))

    def delete(self, name) -> bool:
        with self.db._conn() as c:
            return c.execute("DELETE FROM report_profiles WHERE name=?",
                             (name.strip(),)).rowcount > 0

    # ----------------------------------------------------------- categories
    def find_category(self, name):
        key = (name or "").strip().casefold()
        return next((c for c in self.db.list_categories(include_inactive=True)
                     if c["name"].casefold() == key), None)

    def set_category_color(self, name, color):
        cat = self.find_category(name)
        if not cat:
            raise CardError(f"Category '{name}' does not exist.")
        value = P.normalize_color(color, allow_empty=True, what=f"Colour of category '{name}'")
        with self.db._conn() as c:
            c.execute("UPDATE categories SET color=? WHERE id=?", (value, cat["id"]))

    def apply_categories(self, entries) -> list:
        """Create the categories a profile lists (leaving existing ones alone,
        apart from filling in a colour they don't have yet). Returns new names."""
        added = []
        for e in entries:
            cat = self.find_category(e["name"])
            if cat is None or not cat["is_active"]:
                self.db.add_category(e["name"])
                added.append(e["name"])
                cat = self.find_category(e["name"])
            if e["color"] and not cat["color"]:
                self.set_category_color(e["name"], e["color"])
        return added

    # -------------------------------------------------------------- bundles
    def export_bundle(self, name=None) -> dict:
        """A profile plus this client's current categories, ready to save as a
        file and import on another installation."""
        prof = self.get(name)
        prof["categories"] = [{"name": c["name"], "color": c["color"]}
                              for c in self.db.list_categories()]
        return prof

    def import_bundle(self, profile, make_default=True) -> dict:
        prof = P.normalize(profile)
        self.apply_categories(prof["categories"])
        return self.save(prof, make_default=make_default)

    def install_preset(self, name) -> dict:
        return self.import_bundle(P.preset(name), make_default=True)
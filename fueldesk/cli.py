"""Command line front end - handy for testing and for support. The desktop
GUI will call exactly the same functions."""

import argparse
import sys
from pathlib import Path

from . import APP_NAME, VERSION, analytics, cards_io, fqms
from . import profile as P
from .db import CardError, Database
from .profile_store import ProfileStore
from .report import ReportError, build_monthly_report


def _need_category(store, name):
    cat = store.find_category(name)
    if not cat:
        raise CardError(f"Category '{name}' does not exist.")
    return cat


def _categories(db, args):
    store = ProfileStore(db)
    if args.add:
        db.add_category(args.add)
    if args.rename:
        db.rename_category(_need_category(store, args.rename[0])["id"], args.rename[1])
    if args.remove:
        print(f"Category {db.remove_category(_need_category(store, args.remove)['id'])}.")
    if args.move:
        cat = _need_category(store, args.move[0])
        ids = [c["id"] for c in db.list_categories()]
        pos = int(args.move[1])
        if cat["id"] not in ids or not 1 <= pos <= len(ids):
            raise CardError(f"Position must be between 1 and {len(ids)}.")
        ids.remove(cat["id"])
        ids.insert(pos - 1, cat["id"])
        db.reorder_categories(ids)
    if args.color:
        store.set_category_color(*args.color)
    for n, c in enumerate(db.list_categories(), 1):
        print(f"{n:>3}  {c['name']:<24} {'#' + c['color'] if c['color'] else ''}")


def _profile(db, args):
    store = ProfileStore(db)
    if args.pcmd == "list":
        default = store.default_name()
        for name in store.names():
            print(f"{'*' if name == default else ' '} {name}")
        if not store.names():
            print("(none saved yet - the built-in standard layout is used)")
    elif args.pcmd == "show":
        print(P.to_json(store.get(args.name)))
    elif args.pcmd == "use":
        store.set_default(args.name)
        print(f"'{args.name}' is now the default report profile.")
    elif args.pcmd == "export":
        Path(args.file).write_text(P.to_json(store.export_bundle(args.name)), encoding="utf-8")
        print("Wrote", args.file)
    elif args.pcmd == "import":
        text = Path(args.file).read_text(encoding="utf-8-sig")
        prof = store.import_bundle(P.from_json(text), make_default=args.default)
        print(f"Saved report profile '{prof['name']}'"
              f"{' with ' + str(len(prof['categories'])) + ' categories' if prof['categories'] else ''}.")
    elif args.pcmd == "presets":
        for name, raw in P.PRESETS.items():
            print(f"{name:<18} {raw['name']}")
    elif args.pcmd == "preset":
        prof = store.install_preset(args.name)
        print(f"Installed '{prof['name']}' (categories: {', '.join(db.category_names()) or 'none'}).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fueldesk", description=f"{APP_NAME} {VERSION}")
    ap.add_argument("--db", help="database file (default: app-data folder)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("categories", help="list and edit categories")
    s.add_argument("--add", metavar="NAME")
    s.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"))
    s.add_argument("--remove", metavar="NAME")
    s.add_argument("--move", nargs=2, metavar=("NAME", "POSITION"))
    s.add_argument("--color", nargs=2, metavar=("NAME", "HEX"), help="section colour, e.g. #8EAADB ('' clears)")
    s = sub.add_parser("profile", help="report profiles: layout, wording, colours")
    ps = s.add_subparsers(dest="pcmd", required=True)
    ps.add_parser("list", help="saved profiles (* = default)")
    p = ps.add_parser("show", help="print a profile as JSON"); p.add_argument("name", nargs="?")
    p = ps.add_parser("use", help="make a profile the default"); p.add_argument("name")
    p = ps.add_parser("export", help="save a profile and the categories to a file")
    p.add_argument("file"); p.add_argument("--name")
    p = ps.add_parser("import", help="load a profile file (creates its categories too)")
    p.add_argument("file"); p.add_argument("--default", action="store_true")
    ps.add_parser("presets", help="ready-made starting points")
    p = ps.add_parser("preset", help="install a ready-made profile and its categories"); p.add_argument("name")
    s = sub.add_parser("cards", help="list cards")
    s.add_argument("--all", action="store_true", help="include removed cards")
    s = sub.add_parser("import-cards", help="import cards from an Excel/CSV list")
    s.add_argument("file"); s.add_argument("--update", action="store_true")
    s = sub.add_parser("import-legacy", help="import the old Excel template format")
    s.add_argument("file"); s.add_argument("--escort", nargs="*", default=[])
    s = sub.add_parser("cards-template", help="write a blank card list to fill in")
    s.add_argument("out")
    s = sub.add_parser("set-limit", help="change a card's monthly limit")
    s.add_argument("card"); s.add_argument("litres", type=float)
    s.add_argument("--from", dest="effective", help="effective date YYYY-MM-DD (default today)")
    s = sub.add_parser("check", help="validate an FQMS file without writing a report")
    s.add_argument("file"); s.add_argument("--month")
    s = sub.add_parser("report", help="generate the monthly report")
    s.add_argument("file"); s.add_argument("--month"); s.add_argument("--out")
    s.add_argument("--profile", help="report profile name (default: the saved default)")
    args = ap.parse_args(argv)

    try:
        db = Database(args.db)
        if args.cmd == "categories":
            _categories(db, args)
        elif args.cmd == "profile":
            _profile(db, args)
        elif args.cmd == "cards":
            for c in db.list_cards(include_inactive=args.all):
                flag = " [escort]" if c["is_escort"] else ""
                flag += "" if c["is_active"] else " [removed]"
                print(f"{c['card_number']}  {c['vehicle_number']:<12} {c['category']:<18} "
                      f"{c['limit_liters']:>7.1f} L  {c['name']}{flag}")
        elif args.cmd == "cards-template":
            print("Wrote", cards_io.write_cards_template(args.out))
        elif args.cmd in ("import-cards", "import-legacy"):
            res = (cards_io.import_cards_file(db, args.file, update_existing=args.update)
                   if args.cmd == "import-cards"
                   else cards_io.import_legacy_template(db, args.file, args.escort))
            print(f"Added {res.added}, updated {res.updated}.")
            for label, msg in res.errors:
                print(f"  ERROR {label}: {msg}")
            for w in getattr(res, "warnings", []):
                print(f"  note  {w}")
        elif args.cmd == "set-limit":
            db.set_limit(args.card, args.litres, args.effective)
            print("Limit saved.")
        elif args.cmd in ("check", "report"):
            data = fqms.load(args.file, args.month)
            print(f"{data.source.name}: {data.rows_in_file} rows, using {data.rows_used} "
                  f"for {data.period}.")
            for i in data.issues:
                print(f"  {i.level.upper()}: {i.message}")
            if args.cmd == "report":
                r = build_monthly_report(db, data, args.out, profile=args.profile)
                print(f"\nReport: {r.path}\nProfile: {r.profile_name}\n"
                      f"Total {r.total_litres:,.3f} L | Rs. {r.total_value:,.2f} | "
                      f"{r.cards_with_usage} cards | {len(r.exceeded)} over limit | "
                      f"{len(r.unknown_cards)} not registered")
    except (fqms.FqmsError, CardError, ReportError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
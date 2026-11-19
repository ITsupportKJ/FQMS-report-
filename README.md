# FuelDesk (working name)

Monthly fuel-card reporting for organizations that use FQMS.
Core engine only (no GUI yet). Python 3.11+.

    pip install -r requirements.txt
    python -m pytest tests                 # run the tests

    python -m fueldesk cards-template cards.xlsx        # blank card list to fill in
    python -m fueldesk import-cards cards.xlsx          # load a customer's cards
    python -m fueldesk import-legacy "fuel report.xlsx" # first customer's old template
    python -m fueldesk set-limit 7700000001 250 --from 2026-11-01
    python -m fueldesk check  fqms_export.xlsx          # validate only
    python -m fueldesk report fqms_export.xlsx          # write the monthly report

Data lives in %LOCALAPPDATA%\FuelDesk (set FUELDESK_HOME to override).

## Layout
- `db.py`        SQLite: cards, categories, limits with history, settings, report log
- `fqms.py`      read + validate the FQMS export (clear errors, per-row warnings)
- `usage.py`     one calculation of per-card usage that everything else uses
- `report.py`    monthly .xlsx (+ Summary sheet that reconciles against the file)
- `analytics.py` dashboard and escort numbers
- `cards_io.py`  card list import/export, legacy template import
- `cli.py`       command line (the GUI will call the same functions)

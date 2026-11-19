"""Synthetic FQMS exports and card lists for tests and demos (no real data)."""

import random
from datetime import datetime

import pandas as pd


def make_fqms(path, cards, month="2026-10", seed=1, extra_cards=(), stray_next_month=0,
              with_optional=True, bad_rows=False):
    rnd = random.Random(seed)
    y, m = (int(x) for x in month.split("-"))
    rows = []
    for card in list(cards) + list(extra_cards):
        for _ in range(rnd.randint(1, 5)):
            t = datetime(y, m, rnd.randint(1, 28), rnd.randint(6, 20), rnd.randint(0, 59))
            lit = round(rnd.uniform(5, 60), 2)
            rows.append([card, lit, round(lit * 335, 2), t, "XX-0000", "SAMPLE", 335.0, "STATION 1"])
    for _ in range(stray_next_month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        rows.append([cards[0], 10.0, 3350.0, datetime(ny, nm, 1, 8, 0), "XX-0000", "SAMPLE", 335.0, "STATION 1"])
    cols = ["Card_ID", "TRNX_Lit_Val", "TRNX_Rs_Value", "TRNX_Time", "Vehicle_Number", "Name",
            "Unit_Price", "Station"]
    df = pd.DataFrame(rows, columns=cols)
    if bad_rows:
        df = df.astype(object)
        df.loc[0, "TRNX_Lit_Val"] = "n/a"
        df.loc[1, "TRNX_Time"] = "not a date"
    if not with_optional:
        df = df[cols[:4]]
    with pd.ExcelWriter(path) as w:
        pd.DataFrame([["FQMS TRANSACTION REPORT"], [""]]).to_excel(w, header=False, index=False)
        df.to_excel(w, index=False, startrow=3)
    return df

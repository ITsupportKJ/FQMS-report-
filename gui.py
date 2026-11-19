"""FuelDesk desktop app (PySide6). Start it with:  python gui.py

It only calls the functions in the `fueldesk` package, so the engine and the
command line keep working exactly as before."""

import functools
import sys

from PySide6.QtCore import QDate, QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QColorDialog,
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from fueldesk import APP_NAME, VERSION, analytics, cards_io, fqms
from fueldesk import profile as P
from fueldesk.db import CardError, Database
from fueldesk.profile_store import ProfileStore
from fueldesk.report import ReportError, build_monthly_report

KNOWN_ERRORS = (fqms.FqmsError, CardError, ReportError, P.ProfileError, ValueError, OSError)

ACCENT = "#2563EB"
BAR_COLORS = ["#2563EB", "#0EA5E9", "#14B8A6", "#F59E0B", "#8B5CF6", "#EC4899", "#64748B"]

STYLE = """
* { font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial; font-size: 10pt; color: #1F2937; }
QMainWindow, QDialog, #content { background: #F3F5F9; }
QToolTip { background: #111827; color: white; border: none; padding: 4px 8px; }

#sidebar { background: #0F172A; }
#brand { color: white; font-size: 17pt; font-weight: 700; }
#brandSub { color: #94A3B8; font-size: 8.5pt; }
#sideFoot { color: #64748B; font-size: 8pt; }
QPushButton#nav { text-align: left; padding: 11px 16px; border: none; border-radius: 8px;
                  color: #CBD5E1; background: transparent; font-size: 10.5pt; }
QPushButton#nav:hover { background: #1E293B; color: white; }
QPushButton#nav:checked { background: #2563EB; color: white; font-weight: 600; }

#pageTitle { font-size: 20pt; font-weight: 700; color: #111827; }
#pageSub { color: #6B7280; font-size: 10pt; }
#card { background: white; border: 1px solid #E5E7EB; border-radius: 12px; }
#cardTitle { font-size: 11pt; font-weight: 600; color: #111827; }
#kpiTitle { color: #6B7280; font-size: 8.5pt; font-weight: 600; }
#kpiValue { font-size: 19pt; font-weight: 700; }
#muted { color: #6B7280; }
#success { background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 12px; }
#success QLabel { background: transparent; color: #065F46; }

QPushButton { background: white; border: 1px solid #D1D5DB; border-radius: 8px;
              padding: 8px 16px; font-weight: 500; }
QPushButton:hover { background: #F3F4F6; }
QPushButton:pressed { background: #E5E7EB; }
QPushButton:disabled { color: #9CA3AF; background: #F9FAFB; border-color: #E5E7EB; }
QPushButton[kind="primary"] { background: #2563EB; border: 1px solid #2563EB; color: white; font-weight: 600; }
QPushButton[kind="primary"]:hover { background: #1D4ED8; }
QPushButton[kind="primary"]:disabled { background: #93C5FD; border-color: #93C5FD; color: white; }
QPushButton[kind="danger"] { color: #B91C1C; border-color: #FCA5A5; }
QPushButton[kind="danger"]:hover { background: #FEF2F2; }

QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit {
    background: white; border: 1px solid #D1D5DB; border-radius: 8px; padding: 7px 10px;
    selection-background-color: #BFDBFE; selection-color: #111827; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus { border: 1px solid #2563EB; }
QLineEdit:read-only { background: #F9FAFB; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #D1D5DB; selection-background-color: #DBEAFE;
                              selection-color: #1E3A8A; outline: none; padding: 4px; }
QPlainTextEdit { font-family: Consolas, "Cascadia Mono", monospace; font-size: 9.5pt; }
QCheckBox { spacing: 8px; }
    
QTableWidget { background: white; border: none; gridline-color: transparent; alternate-background-color: #F9FAFB;
               selection-background-color: #DBEAFE; selection-color: #1E3A8A; outline: none; }
QTableWidget::item { padding: 4px 8px; border: none; }
QHeaderView::section { background: #F3F4F6; color: #4B5563; border: none; border-bottom: 1px solid #E5E7EB;
                       padding: 9px 10px; font-weight: 600; }
QTableCornerButton::section { background: #F3F4F6; border: none; }

QListWidget { background: white; border: none; outline: none; }
QListWidget::item { padding: 11px 12px; border-radius: 8px; margin: 2px 0; }
QListWidget::item:selected { background: #DBEAFE; color: #1E3A8A; }
    
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def light_palette():
    """Fixed light colours so the app looks the same even in Windows dark mode."""
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#F3F5F9"))
    p.setColor(QPalette.WindowText, QColor("#1F2937"))
    p.setColor(QPalette.Base, QColor("white"))
    p.setColor(QPalette.AlternateBase, QColor("#F9FAFB"))
    p.setColor(QPalette.Text, QColor("#1F2937"))
    p.setColor(QPalette.Button, QColor("white"))
    p.setColor(QPalette.ButtonText, QColor("#1F2937"))
    p.setColor(QPalette.Highlight, QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor("white"))
    p.setColor(QPalette.PlaceholderText, QColor("#9CA3AF"))
    return p


# ----------------------------------------------------------------- helpers
def guarded(fn):
    """Show friendly engine errors in a message box instead of crashing."""
    @functools.wraps(fn)
    def wrapper(self, *args):
        try:
            return fn(self)
        except KNOWN_ERRORS as e:
            QMessageBox.warning(self, APP_NAME, str(e))
    return wrapper


def button(text, slot, kind="secondary"):
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(slot)
    return b


def make_table(headers, stretch=True):
    """stretch=True: columns share the width equally (no sideways scrolling)."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setFrameShape(QFrame.NoFrame)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(36)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setHighlightSections(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    if stretch:
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # card numbers in full
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return t


def fill_table(t, rows):
    t.setRowCount(0)
    for row in rows:
        i = t.rowCount()
        t.insertRow(i)
        for j, v in enumerate(row):
            t.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
    if t.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff:
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)


def open_path(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class Card(QFrame):
    """White rounded panel with an optional title."""
    def __init__(self, title=None, margins=(18, 16, 18, 16)):
        super().__init__()
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            self.lay.addWidget(t)

    def add(self, widget, stretch=0):
        self.lay.addWidget(widget, stretch)
        return widget


class Kpi(Card):
    def __init__(self, title, color=ACCENT):
        super().__init__(margins=(18, 14, 18, 14))
        self.lay.setSpacing(2)
        t = QLabel(title.upper())
        t.setObjectName("kpiTitle")
        self.value = QLabel("-")
        self.value.setObjectName("kpiValue")
        self.value.setStyleSheet(f"color: {color};")
        self.lay.addWidget(t)
        self.lay.addWidget(self.value)

    def set(self, text):
        self.value.setText(text)


class Page(QWidget):
    """Title + subtitle on top, content below."""
    def __init__(self, title, subtitle=""):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 26, 32, 24)
        outer.setSpacing(18)
        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        s = QLabel(subtitle)
        s.setObjectName("pageSub")
        head.addWidget(t)
        head.addWidget(s)
        outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(16)
        outer.addLayout(self.body, 1)


# ----------------------------------------------------------------- charts
class HBarChart(QWidget):
    """Horizontal bars: one row per category."""
    ROW = 32

    def __init__(self):
        super().__init__()
        self.items = []
        self.setMinimumHeight(60)

    def set_data(self, items):
        self.items = list(items)
        self.setMinimumHeight(max(60, self.ROW * len(self.items) + 6))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.items:
            p.setPen(QColor("#9CA3AF"))
            p.drawText(self.rect(), Qt.AlignCenter, "No data yet")
            return
        fm = p.fontMetrics()
        top = max(v for _, v in self.items) or 1
        label_w = min(170, max(fm.horizontalAdvance(n) for n, _ in self.items) + 8)
        val_w = max(fm.horizontalAdvance(f"{v:,.1f} L") for _, v in self.items) + 8
        x0 = label_w + 10
        span = max(20, self.width() - x0 - val_w - 10)
        for i, (name, v) in enumerate(self.items):
            y = i * self.ROW
            p.setPen(QColor("#374151"))
            p.drawText(QRectF(0, y, label_w, self.ROW), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(name, Qt.ElideRight, label_w))
            w = max(3.0, span * v / top)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#EEF2F7"))
            p.drawRoundedRect(QRectF(x0, y + 9, span, 14), 6, 6)
            p.setBrush(QColor(BAR_COLORS[i % len(BAR_COLORS)]))
            p.drawRoundedRect(QRectF(x0, y + 9, w, 14), 6, 6)
            p.setPen(QColor("#111827"))
            p.drawText(QRectF(x0 + span + 8, y, val_w, self.ROW), Qt.AlignVCenter | Qt.AlignLeft,
                       f"{v:,.1f} L")


class ColumnChart(QWidget):
    """Litres per day of the month."""
    def __init__(self):
        super().__init__()
        self.data = {}
        self.setMinimumHeight(210)

    def set_data(self, data):
        self.data = {int(k): float(v) for k, v in data.items()}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.data:
            p.setPen(QColor("#9CA3AF"))
            p.drawText(self.rect(), Qt.AlignCenter, "No data yet")
            return
        left, right, top, bottom = 46, 8, 10, 24
        w, h = self.width() - left - right, self.height() - top - bottom
        days = max(self.data)
        peak = max(self.data.values()) or 1
        small = QFont(self.font())
        small.setPointSizeF(8)
        p.setFont(small)
        for k in range(5):                                   # grid + y labels
            y = top + h - h * k / 4
            p.setPen(QColor("#E5E7EB"))
            p.drawLine(left, int(y), left + w, int(y))
            p.setPen(QColor("#6B7280"))
            p.drawText(QRectF(0, y - 9, left - 6, 18), Qt.AlignRight | Qt.AlignVCenter,
                       f"{peak * k / 4:,.0f}")
        slot = w / days
        step = 1 if slot >= 22 else 2
        for d in range(1, days + 1):
            x = left + (d - 1) * slot
            v = self.data.get(d, 0.0)
            bh = h * v / peak
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            if bh > 0:
                p.drawRoundedRect(QRectF(x + slot * 0.18, top + h - bh, slot * 0.64, bh), 3, 3)
            if d % step == 1 or step == 1:
                p.setPen(QColor("#6B7280"))
                p.drawText(QRectF(x, top + h + 4, slot, 16), Qt.AlignHCenter | Qt.AlignTop, str(d))


# ------------------------------------------------------------ report page
class ReportPage(Page):
    def __init__(self, db, on_loaded, on_done, on_data_changed, goto_dashboard):
        super().__init__("Monthly Report",
                         "Load the FQMS transaction export, check it, and generate the Excel report.")
        self.db, self.store = db, ProfileStore(db)
        self.on_loaded, self.on_done, self.on_data_changed = on_loaded, on_done, on_data_changed
        self.last = None
        self._loading = False

        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText("No file selected - click Browse")
        self.month = QComboBox()
        self.month.currentIndexChanged.connect(self._month_changed)
        self.profile = QComboBox()

        src = Card("Source")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(button("Browse...", self.choose))
        form.addRow("FQMS file", row)
        form.addRow("Month", self.month)
        prow = QHBoxLayout()
        prow.addWidget(self.profile, 1)
        prow.addWidget(button("Add ready-made layout...", self.add_preset))
        form.addRow("Report layout", prow)
        src.lay.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(button("Check file", self.check))
        actions.addWidget(button("Generate report", self.generate, "primary"))
        src.lay.addLayout(actions)

        chk = Card("File check")
        self.issues = QPlainTextEdit()
        self.issues.setReadOnly(True)
        self.issues.setPlaceholderText("Warnings and notes about the file appear here.")
        chk.add(self.issues, 1)

        self.result = QFrame()
        self.result.setObjectName("success")
        rl = QVBoxLayout(self.result)
        rl.setContentsMargins(18, 14, 18, 14)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.summary)
        rb = QHBoxLayout()
        rb.addWidget(button("Open report", lambda: open_path(self.last.path), "primary"))
        rb.addWidget(button("Open folder", lambda: open_path(self.last.path.parent)))
        rb.addWidget(button("View dashboard", goto_dashboard))
        rb.addStretch(1)
        rl.addLayout(rb)
        self.result.hide()
        
        self.body.addWidget(src)
        self.body.addWidget(chk, 1)
        self.body.addWidget(self.result)
        self.refresh_profiles()

    def refresh_profiles(self):
        self.profile.clear()
        names = self.store.names()
        if not names:
            self.profile.addItem("Standard layout (built in)", None)
        default = self.store.default_name()
        for n in names:
            self.profile.addItem(n + ("  (default)" if n == default else ""), n)

    @guarded
    def add_preset(self):
        names = list(P.PRESETS)
        labels = [f"{n} - {P.PRESETS[n]['name']}" for n in names]
        label, ok = QInputDialog.getItem(self, APP_NAME, "Ready-made layout:", labels, 0, False)
        if ok:
            prof = self.store.install_preset(names[labels.index(label)])
            self.refresh_profiles()
            self.on_data_changed()
            QMessageBox.information(self, APP_NAME, f"Installed '{prof['name']}'.")

    @guarded
    def choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FQMS export", "", "Excel files (*.xls *.xlsx *.csv);;All files (*)")
        if path:
            self.path.setText(path)
            self.result.hide()
            self._load(None)

    def _month_changed(self):
        if not self._loading and self.path.text():
            self.check()

    @guarded
    def check(self):
        self._load(self.month.currentData())

    def _load(self, month):
        self._loading = True
        try:
            data = fqms.load(self.path.text(), month)
            self.month.clear()
            for m, n in sorted(data.months_found.items()):
                self.month.addItem(f"{m}  ({n} rows)", m)
            self.month.setCurrentIndex(self.month.findData(data.period))
        finally:
            self._loading = False
        lines = [f"{data.source.name}: {data.rows_in_file} rows, using {data.rows_used} for {data.period}."]
        lines += [f"{i.level.upper()}: {i.message}" for i in data.issues]
        self.issues.setPlainText("\n".join(lines))
        self.on_loaded(data)
        return data

    @guarded
    def generate(self):
        if not self.path.text():
            QMessageBox.information(self, APP_NAME, "Choose an FQMS file first.")
            return
        data = self._load(self.month.currentData())
        r = build_monthly_report(self.db, data, None, profile=self.profile.currentData())
        self.last = r
        self.summary.setText(
            f"<b>Report created for {r.period}</b><br>{r.path}<br>"
            f"Layout: {r.profile_name} &nbsp;|&nbsp; <b>{r.total_litres:,.3f} L</b> &nbsp;|&nbsp; "
            f"<b>Rs. {r.total_value:,.2f}</b> &nbsp;|&nbsp; {r.cards_with_usage} cards used &nbsp;|&nbsp; "
            f"{len(r.exceeded)} over limit &nbsp;|&nbsp; {len(r.unknown_cards)} not registered")
        self.result.show()
        self.on_done()


# ------------------------------------------- dashboard page -------------------------------------------------
class DashboardPage(Page):
    def __init__(self, db):
        super().__init__("Dashboard", "Load an FQMS file on the Monthly Report page to see the numbers.")
        self.db = db
        self.subtitle = self.findChildren(QLabel, "pageSub")[0]

        self.k_litres = Kpi("Total litres")
        self.k_value = Kpi("Total value (Rs.)", "#059669")
        self.k_cards = Kpi("Cards used", "#7C3AED")
        self.k_over = Kpi("Over limit", "#DC2626")
        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        for k in (self.k_litres, self.k_value, self.k_cards, self.k_over):
            kpis.addWidget(k)
    
        self.daily = ColumnChart()
        self.cat = HBarChart()
        self.top = make_table(["Card", "Vehicle", "Name", "Category", "Fills", "Litres", "Limit"])
        self.exceeded = make_table(["Card", "Vehicle", "Litres", "Limit", "Over by"])
        self.unreg = QPlainTextEdit()
        self.unreg.setReadOnly(True)
        self.unreg.setMaximumHeight(110)
    
        c1 = Card("Litres per day")
        c1.add(self.daily)
        c2 = Card("Usage by category")
        c2.add(self.cat)
        c2.lay.addStretch(1)
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        row1.addWidget(c1, 3)
        row1.addWidget(c2, 2)
    
        c3 = Card("Top 10 cards", margins=(0, 16, 0, 0))
        c3.lay.itemAt(0).widget().setContentsMargins(18, 0, 18, 0)
        c3.add(self.top)
        self.top.setMinimumHeight(300)
        c4 = Card("Over limit", margins=(0, 16, 0, 0))
        c4.lay.itemAt(0).widget().setContentsMargins(18, 0, 18, 0)
        c4.add(self.exceeded)
        self.exceeded.setMinimumHeight(190)
        c5 = Card("Cards not registered")
        c5.add(self.unreg)
        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(c4, 1)
        right.addWidget(c5)
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.addWidget(c3, 3)
        row2.addLayout(right, 2)
    
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 8, 0)
        il.setSpacing(16)
        il.addLayout(kpis)
        il.addLayout(row1)
        il.addLayout(row2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(inner)
        self.body.addWidget(scroll, 1)
    
    def show_data(self, data):
        d = analytics.dashboard(self.db, data)
        self.subtitle.setText(f"Period {d['period']}  -  {data.source.name}")
        self.k_litres.set(f"{d['total_litres']:,.1f} L")
        self.k_value.set(f"{d['total_value']:,.0f}")
        self.k_cards.set(str(d["cards_used"]))
        self.k_over.set(str(len(d["exceeded"])))
        self.daily.set_data(d["daily_usage"])
        self.cat.set_data(list(d["category_usage"].items()))
        fill_table(self.top, [(u.card, u.vehicle, u.name, u.category, u.fills, round(u.litres, 3), u.limit)
                              for u in d["top_cards"]])
        fill_table(self.exceeded, [(u.card, u.vehicle, round(u.litres, 3), u.limit,
                                    round(u.litres - u.limit, 3)) for u in d["exceeded"]])
        self.unreg.setPlainText("\n".join(d["unregistered"]) or "None - every card is registered.")
    
    
# ------------------------------------------ cards page ------------------------------------------------
class CardDialog(QDialog):
    def __init__(self, db, card=None, parent=None):
        super().__init__(parent)
        self.db, self.card = db, card
        self.setWindowTitle("Edit card" if card else "Add card")
        self.setMinimumWidth(420)
        self.number = QLineEdit(card["card_number"] if card else "")
        self.number.setEnabled(card is None)
        self.vehicle = QLineEdit(card["vehicle_number"] if card else "")
        self.name = QLineEdit(card["name"] if card else "")
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems([""] + db.category_names())
        if card:
            self.category.setCurrentText(card["category"])
        self.limit = QDoubleSpinBox()
        self.limit.setRange(0, 1_000_000)
        self.limit.setDecimals(1)
        self.limit.setSuffix(" L")
        self.limit.setValue(card["limit_liters"] if card else 0)
        self.effective = QDateEdit(QDate.currentDate())
        self.effective.setCalendarPopup(True)
        self.effective.setDisplayFormat("yyyy-MM-dd")
        self.escort = QCheckBox("Escort vehicle")
        self.escort.setChecked(bool(card and card["is_escort"]))
    
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Card number", self.number)
        form.addRow("Vehicle", self.vehicle)
        form.addRow("Name", self.name)
        form.addRow("Category", self.category)
        form.addRow("Monthly limit", self.limit)
        if card:                                                
            form.addRow("Limit effective from", self.effective)
        form.addRow("", self.escort)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setProperty("kind", "primary")
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(16)
        lay.addLayout(form)
        lay.addWidget(bb)
    
    def save(self):
        try:
            cat = self.category.currentText().strip()
            if self.card:
                num = self.card["card_number"]
                self.db.update_card(num, vehicle_number=self.vehicle.text().strip(),
                                    name=self.name.text().strip(), category=cat,
                                    is_escort=self.escort.isChecked(), create_category=True)
                if abs(self.limit.value() - self.card["limit_liters"]) > 1e-9:
                    self.db.set_limit(num, self.limit.value(),
                                      self.effective.date().toString("yyyy-MM-dd"))
            else:
                self.db.add_card(self.number.text().strip(), self.vehicle.text().strip(),
                                 self.name.text().strip(), cat, self.limit.value(),
                                 self.escort.isChecked(), create_category=True)
        except KNOWN_ERRORS as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.accept()
    
    
class CardsPage(Page):
    HEADERS = ["Card", "Vehicle", "Name", "Category", "Limit (L)", "Escort", "Status"]
     
    def __init__(self, db, on_data_changed):
        super().__init__("Cards", "Every fuel card, its vehicle, category and monthly limit.")
        self.db, self.on_data_changed = db, on_data_changed
        self.table = make_table(self.HEADERS)
        self.table.doubleClicked.connect(self.edit)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search card, vehicle or name...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.show_removed = QCheckBox("Show removed")
        self.show_removed.toggled.connect(self.refresh)
        self.count = QLabel("")
        self.count.setObjectName("muted")

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_removed)
        bar.addWidget(button("Import from Excel...", self.import_cards))
        bar.addWidget(button("Blank template...", self.template))
        bar.addWidget(button("Add card", self.add, "primary"))
    
        card = Card(margins=(0, 0, 0, 0))
        card.add(self.table, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(18, 0, 18, 12)
        foot.addWidget(self.count)
        foot.addStretch(1)
        foot.addWidget(button("Edit", self.edit))
        foot.addWidget(button("Remove", self.remove, "danger"))
        card.lay.addLayout(foot)
        self.body.addLayout(bar)
        self.body.addWidget(card, 1)
        self.refresh()
    
    def refresh(self, *_):
        needle = self.search.text().strip().lower()
        cards = self.db.list_cards(include_inactive=self.show_removed.isChecked())
        if needle:
            cards = [c for c in cards if needle in
                     f"{c['card_number']} {c['vehicle_number']} {c['name']}".lower()]
        fill_table(self.table, [
            (c["card_number"], c["vehicle_number"], c["name"], c["category"],
             c["limit_liters"], "Yes" if c["is_escort"] else "",
             "" if c["is_active"] else "Removed") for c in cards])
        self.count.setText(f"{len(cards)} cards")
    
    def _selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, APP_NAME, "Select a card first.")
            return None
        return self.table.item(row, 0).text()
    
    def add(self, *_):
        if CardDialog(self.db, parent=self).exec():
            self.refresh()
            self.on_data_changed()
    
    @guarded
    def edit(self):
        num = self._selected()
        if num and CardDialog(self.db, self.db.get_card(num), self).exec():
            self.refresh()
            self.on_data_changed()
    
    @guarded
    def remove(self):
        num = self._selected()
        if num and QMessageBox.question(
                self, APP_NAME, f"Remove card {num}? Its history is kept.") == QMessageBox.Yes:
            self.db.deactivate_card(num)
            self.refresh()

    @guarded
    def import_cards(self):
        path, _ = QFileDialog.getOpenFileName(self, "Card list", "", "Excel/CSV (*.xlsx *.xls *.csv)")
        if not path:
            return
        ask = QMessageBox.question(
            self, APP_NAME, "Update cards that already exist?\n\nYes = update them, No = only add new cards.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if ask == QMessageBox.Cancel:
            return
        res = cards_io.import_cards_file(self.db, path, update_existing=(ask == QMessageBox.Yes))
        msg = f"Added {res.added}, updated {res.updated}."
        msg += "".join(f"\nERROR {a}: {b}" for a, b in res.errors)
        msg += "".join(f"\nnote: {w}" for w in res.warnings)
        QMessageBox.information(self, APP_NAME, msg)
        self.refresh()
        self.on_data_changed()

    @guarded
    def template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save blank card list", "cards.xlsx", "Excel (*.xlsx)")
        if path:
            cards_io.write_cards_template(path)
            open_path(path)


# -------------------------------------------------------- categories page
class CategoriesPage(Page):
    def __init__(self, db, on_data_changed):
        super().__init__("Categories", "The sections of the report, in the order they appear. "
                                       "Colours are used for the section headings.")
        self.db, self.store, self.on_data_changed = db, ProfileStore(db), on_data_changed
        self.list = QListWidget()
        card = Card()
        card.add(self.list, 1)

        side = Card()
        side.setFixedWidth(210)
        for text, slot, kind in [("Add category", self.add, "primary"), ("Rename", self.rename, "secondary"),
                                 ("Move up", self.move_up, "secondary"), ("Move down", self.move_down, "secondary"),
                                 ("Set colour...", self.colour, "secondary"),
                                 ("Clear colour", self.clear_colour, "secondary"),
                                 ("Remove", self.remove, "danger")]:
            side.add(button(text, slot, kind))
        side.lay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(card, 1)
        row.addWidget(side)
        self.body.addLayout(row, 1)
        self.refresh()

    def refresh(self, select_id=None):
        if select_id is None and self.list.currentItem():
            select_id = self.list.currentItem().data(Qt.UserRole)   # keep the selection
        self.list.clear()
        for n, c in enumerate(self.db.list_categories(), 1):
            item = QListWidgetItem(f"{n}.   {c['name']}")
            item.setData(Qt.UserRole, c["id"])
            item.setData(Qt.UserRole + 1, c["name"])
            if c["color"]:
                item.setBackground(QColor("#" + c["color"].lstrip("#")))
                item.setForeground(QColor("#111827"))
            self.list.addItem(item)
            if c["id"] == select_id:
                self.list.setCurrentItem(item)

    def _cur(self):
        item = self.list.currentItem()
        if not item:
            QMessageBox.information(self, APP_NAME, "Select a category first.")
            return None
        return item.data(Qt.UserRole), item.data(Qt.UserRole + 1)
    
    @guarded
    def add(self):
        name, ok = QInputDialog.getText(self, APP_NAME, "New category name:")
        if ok and name.strip():
            self.refresh(self.db.add_category(name.strip()))
            self.on_data_changed()
    
    @guarded
    def rename(self):
        cur = self._cur()
        if cur:
            name, ok = QInputDialog.getText(self, APP_NAME, "New name:", text=cur[1])
            if ok and name.strip():
                self.db.rename_category(cur[0], name.strip())
                self.refresh(cur[0])
                self.on_data_changed()
    
    @guarded
    def remove(self):
        cur = self._cur()
        if cur and QMessageBox.question(self, APP_NAME, f"Remove category '{cur[1]}'?") == QMessageBox.Yes:
            QMessageBox.information(self, APP_NAME, f"Category {self.db.remove_category(cur[0])}.")
            self.refresh()
            self.on_data_changed()

    def _move(self, step):
        cur = self._cur()
        if cur:
            ids = [c["id"] for c in self.db.list_categories()]
            i = ids.index(cur[0])
            j = i + step
            if 0 <= j < len(ids):
                ids[i], ids[j] = ids[j], ids[i]
                self.db.reorder_categories(ids)
                self.refresh(cur[0])
                self.on_data_changed()

    @guarded
    def move_up(self):
        self._move(-1)

    @guarded
    def move_down(self):
        self._move(1)

    @guarded
    def colour(self):
        cur = self._cur()
        if cur:
            col = QColorDialog.getColor(parent=self)
            if col.isValid():
                self.store.set_category_color(cur[1], col.name().upper())
                self.refresh(cur[0])

    @guarded
    def clear_colour(self):
        cur = self._cur()
        if cur:
            self.store.set_category_color(cur[1], "")
            self.refresh(cur[0])


# ------------------------------------------------------------ history page
class HistoryPage(Page):
    def __init__(self, db):
        super().__init__("History", "Reports made so far. Double-click a row to open the file.")
        self.db = db
        self.table = make_table(["-"], stretch=False)
        self.table.doubleClicked.connect(self.open_row)
        card = Card(margins=(0, 0, 0, 0))
        card.add(self.table, 1)
        self.body.addWidget(card, 1)
        self.runs = []
        self.refresh()

    def refresh(self):
        self.runs = self.db.list_runs()
        keys = list(self.runs[0].keys()) if self.runs else ["id", "period", "output_path"]
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels([k.replace("_", " ").title() for k in keys])
        fill_table(self.table, [[r[k] for k in keys] for r in self.runs])
          
    def open_row(self, *_):
        row = self.table.currentRow()
        if 0 <= row < len(self.runs) and self.runs[row].get("output_path"):
            open_path(self.runs[row]["output_path"])
        
        
# ------------------------------------------------------------- main window
# ------------------------------------------------------------- layout editor
from PySide6.QtWidgets import QGridLayout, QSpinBox, QTabWidget

TAB_STYLE = """
QTabWidget::pane { border: none; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: #6B7280; padding: 10px 18px; margin-right: 6px;
               border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:hover { color: #111827; }
QTabBar::tab:selected { color: #2563EB; border-bottom: 2px solid #2563EB; }
QSpinBox { background: white; border: 1px solid #D1D5DB; border-radius: 8px; padding: 7px 10px; }
QSpinBox:focus { border: 1px solid #2563EB; }
QLabel#hint { color: #6B7280; font-size: 9pt; }
QLabel#status { color: #047857; font-weight: 600; }
"""

COLUMN_NAMES = {
    "card_number": "Card number", "vehicle": "Vehicle number", "holder": "Card holder / name",
    "category": "Category", "limit": "Monthly limit (budget)", "day_grid": "Daily litres (one column per day)",
    "total_litres": "Total litres", "total_value": "Total value (Rs.)", "status": "Status",
    "fills": "Number of fills", "avg_price": "Average price per litre", "last_fill": "Date of last fill",
    "block_limit": "Budget (block)", "block_actual": "Actual (block)", "block_balance": "Balance (block)",
}
SORT_CHOICES = [("As in the card list (manual order)", "manual"), ("Card number", "card_number"),
                ("Vehicle number", "vehicle"), ("Name (A-Z)", "name"), ("Most fuel used first", "litres_desc")]
WORDING = [("over_limit_text", "Card is over its limit"), ("near_limit_text", "Card is near its limit"),
           ("ok_text", "Card is within its limit"), ("no_limit_text", "Card has no limit set"),
           ("new_card_text", "Card is not in the card list"), ("inactive_text", "Removed card that still has fuel")]
COLOURS_HEADINGS = [("header_fill", "Card details heading"), ("totals_fill", "Totals heading"),
                    ("block_fill", "Budget / actual / balance heading"), ("section_fill", "Category section bar"),
                    ("day_header_font", "Day numbers (text)")]
COLOURS_ROWS = [("over_fill", "Over limit - row"), ("over_font", "Over limit - text"),
                ("warn_fill", "Near limit - row"), ("unregistered_fill", "Not registered - row"),
                ("totals_cell_fill", "Totals cells"), ("grand_total_fill", "Grand total row")]

COLUMNS = P.COLUMNS
_UNSET = object()


class ColorButton(QPushButton):
    """A colour swatch; click it to choose another colour."""
    def __init__(self, color="FFFFFF"):
        super().__init__()
        self.setFixedSize(104, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.color = "FFFFFF"
        self.set_color(color)
        self.clicked.connect(self.choose)

    def set_color(self, color):
        self.color = str(color).lstrip("#").upper()
        qc = QColor("#" + self.color)
        bright = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
        text = "#111827" if bright > 150 else "#FFFFFF"
        self.setText("#" + self.color)
        self.setStyleSheet(f"QPushButton {{ background: #{self.color}; color: {text}; border: 1px solid #9CA3AF;"
                           f" border-radius: 6px; padding: 0; font-weight: 600; }}"
                           f"QPushButton:hover {{ border: 2px solid #2563EB; }}")

    def choose(self, *_):
        col = QColorDialog.getColor(QColor("#" + self.color), self)
        if col.isValid():
            self.set_color(col.name())


def hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def scrolled(inner):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.NoFrame)
    s.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                    "QScrollArea > QWidget > QWidget { background: transparent; }")
    s.setWidget(inner)
    return s


def form_tab():
    w = QWidget()
    f = QFormLayout(w)
    f.setContentsMargins(4, 14, 14, 14)
    f.setHorizontalSpacing(22)
    f.setVerticalSpacing(12)
    f.setLabelAlignment(Qt.AlignLeft)
    return w, f


def capped(widget, width=520):
    widget.setMaximumWidth(width)
    return widget


def set_combo(combo, value, label=None):
    i = combo.findData(value)
    if i < 0:
        combo.addItem(label or str(value), value)
        i = combo.count() - 1
    combo.setCurrentIndex(i)


class LayoutPage(Page):
    def __init__(self, db, on_data_changed):
        super().__init__("Report Layout", "Set how each client's monthly report looks: "
                                          "title, columns, wording and colours.")
        self.db, self.store, self.on_data_changed = db, ProfileStore(db), on_data_changed
        self.current = _UNSET

        self.pick = QComboBox()
        self.pick.currentIndexChanged.connect(self._picked)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel("Layout:"))
        bar.addWidget(self.pick, 1)
        bar.addWidget(button("New...", self.new_layout))
        bar.addWidget(button("Set as default", self.make_default))
        bar.addWidget(button("Export...", self.export_layout))
        bar.addWidget(button("Import...", self.import_layout))
        bar.addWidget(button("Delete", self.delete_layout, "danger"))

        tabs = QTabWidget()
        tabs.addTab(scrolled(self._general_tab()), "General")
        tabs.addTab(self._columns_tab(), "Columns")
        tabs.addTab(scrolled(self._rules_tab()), "Wording && rules")
        tabs.addTab(scrolled(self._colours_tab()), "Colours")
        card = Card(margins=(18, 6, 18, 12))
        card.add(tabs, 1)

        self.status = QLabel("")
        self.status.setObjectName("status")
        foot = QHBoxLayout()
        foot.addWidget(self.status)
        foot.addStretch(1)
        foot.addWidget(button("Reset to standard", self.reset))
        foot.addWidget(button("Save layout", self.save, "primary"))

        self.body.addLayout(bar)
        self.body.addWidget(card, 1)
        self.body.addLayout(foot)
        self.refresh_list()

    # ------------------------------------------------------------- tabs
    def _general_tab(self):
        w, f = form_tab()
        self.name = capped(QLineEdit())
        self.name.setMaxLength(60)
        self.org = capped(QLineEdit())
        self.org.setPlaceholderText("e.g. Acme Security (Pvt) Ltd")
        self.title = capped(QLineEdit())
        self.title.setMaxLength(120)
        self.title.setPlaceholderText("e.g. {org} - Fuel Report {period}")
        self.sheet = capped(QLineEdit())
        self.sheet.setMaxLength(31)
        self.prefix = capped(QLineEdit())
        self.prefix.setMaxLength(40)
        self.sort = capped(QComboBox())
        for label, value in SORT_CHOICES:
            self.sort.addItem(label, value)
        self.freeze = capped(QComboBox())
        self.freeze.addItem("Automatic", "auto")
        self.freeze.addItem("No frozen rows or columns", "none")
        self.grand_total = QCheckBox("Add a grand total row at the bottom")
        self.grand_label = capped(QLineEdit())
        self.grand_label.setMaxLength(40)
        self.grand_total.toggled.connect(self.grand_label.setEnabled)
        self.summary = QCheckBox("Add a Summary sheet")
        self.formulas = QCheckBox("Write totals as Excel formulas (the client can edit the numbers)")

        f.addRow("Layout name", self.name)
        f.addRow("", hint("Change the name and save to make a copy for another client."))
        f.addRow("Company name", self.org)
        f.addRow("Report title", self.title)
        f.addRow("", hint("Use {org} for the company name and {period} for the month, e.g. 2026-10. "
                          "Leave empty for no title row."))
        f.addRow("Excel sheet name", self.sheet)
        f.addRow("File name starts with", self.prefix)
        f.addRow("Sort cards by", self.sort)
        f.addRow("Frozen panes", self.freeze)
        f.addRow("", self.grand_total)
        f.addRow("Grand total label", self.grand_label)
        f.addRow("", self.summary)
        f.addRow("", self.formulas)
        return w

    def _columns_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(hint("Tick the columns to include and use Move up / Move down to set their order. "
                           "Double-click a heading or a width to change it."))
        self.cols = make_table(["Show", "Column", "Heading in report", "Width"], stretch=False)
        hdr = self.cols.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.cols.setColumnWidth(0, 64)
        self.cols.setColumnWidth(1, 260)
        self.cols.setColumnWidth(3, 84)
        self.cols.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        side = QVBoxLayout()
        side.addWidget(button("Move up", self.col_up))
        side.addWidget(button("Move down", self.col_down))
        side.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.cols, 1)
        row.addLayout(side)
        lay.addLayout(row, 1)
        self.days = QComboBox()
        self.days.addItem("All 31 days (1-31)", "1-31")
        self.days.addItem("Only the days of the report month", "month")
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Day columns show:"))
        drow.addWidget(self.days)
        drow.addStretch(1)
        lay.addLayout(drow)
        return w

    def _rules_tab(self):
        w, f = form_tab()
        self.wording = {}
        f.addRow("", hint("The wording shown in the Status column:"))
        for key, label in WORDING:
            edit = capped(QLineEdit())
            edit.setMaxLength(40)
            self.wording[key] = edit
            f.addRow(label, edit)
        self.warn = QSpinBox()
        self.warn.setRange(0, 100)
        self.warn.setSuffix(" %")
        self.warn.setFixedWidth(110)
        f.addRow("Warn when a card has used", self.warn)
        f.addRow("", hint("0 turns the near-limit warning off."))
        self.zero = capped(QComboBox())
        self.zero.addItem("Show 'no limit set' wording", "show_no_limit")
        self.zero.addItem("Show the 'within limit' wording", "show_ok")
        f.addRow("Cards with no limit", self.zero)
        self.unused = QCheckBox("List cards that bought no fuel this month")
        f.addRow("", self.unused)
        return w

    def _colours_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(4, 14, 14, 14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.colours = {}
        for col, (title, fields) in enumerate([("Headings", COLOURS_HEADINGS), ("Highlights", COLOURS_ROWS)]):
            head = QLabel(title)
            head.setObjectName("cardTitle")
            grid.addWidget(head, 0, col * 3, 1, 3)
            for r, (key, label) in enumerate(fields, 1):
                btn = ColorButton()
                self.colours[key] = btn
                grid.addWidget(QLabel(label), r, col * 3)
                grid.addWidget(btn, r, col * 3 + 1)
            grid.setColumnMinimumWidth(col * 3 + 2, 40)
        grid.setColumnStretch(6, 1)
        outer.addLayout(grid)
        self.use_cat = QCheckBox("Use each category's own colour for its section bar")
        outer.addSpacing(8)
        outer.addWidget(self.use_cat)
        outer.addWidget(hint("Category colours are set on the Categories page."))
        outer.addStretch(1)
        return w

    # ---------------------------------------------------- columns helpers
    def _fill_columns(self, columns):
        have = {c["id"] for c in columns}
        rows = list(columns) + [dict(id=i, label=COLUMNS[i]["label"], show=False, width=COLUMNS[i]["width"],
                                     format="") for i in COLUMNS if i not in have]
        self.cols.setRowCount(0)
        for c in rows:
            r = self.cols.rowCount()
            self.cols.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if c["show"] else Qt.Unchecked)
            name = QTableWidgetItem(COLUMN_NAMES.get(c["id"], c["id"]))
            name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            name.setData(Qt.UserRole, c["id"])
            name.setData(Qt.UserRole + 1, c.get("format", ""))
            for j, item in enumerate((chk, name, QTableWidgetItem(c["label"]), QTableWidgetItem(str(c["width"])))):
                self.cols.setItem(r, j, item)

    def _collect_columns(self):
        out = []
        for r in range(self.cols.rowCount()):
            ident = self.cols.item(r, 1)
            entry = {"id": ident.data(Qt.UserRole),
                     "show": self.cols.item(r, 0).checkState() == Qt.Checked,
                     "label": self.cols.item(r, 2).text().strip(),
                     "width": self.cols.item(r, 3).text().strip(),
                     "format": ident.data(Qt.UserRole + 1) or ""}
            if entry["id"] == "day_grid":
                entry["days"] = self.days.currentData()
            out.append(entry)
        return out

    def _move_col(self, step):
        r = self.cols.currentRow()
        t = r + step
        if r < 0 or not 0 <= t < self.cols.rowCount():
            return
        a = [self.cols.takeItem(r, c) for c in range(4)]
        b = [self.cols.takeItem(t, c) for c in range(4)]
        for c in range(4):
            self.cols.setItem(r, c, b[c])
            self.cols.setItem(t, c, a[c])
        self.cols.selectRow(t)

    def col_up(self, *_):
        self._move_col(-1)

    def col_down(self, *_):
        self._move_col(1)

    # ------------------------------------------------- load / collect
    def _fill(self, prof):
        self.name.setText(prof["name"])
        self.org.setText(self.db.get_setting("org_name", "") or "")
        self.title.setText(prof["title"])
        out, rules, style = prof["output"], prof["rules"], prof["style"]
        self.sheet.setText(out["sheet_name"])
        self.prefix.setText(out["file_prefix"])
        set_combo(self.sort, prof["sorting"]["cards"])
        set_combo(self.freeze, style["freeze"], f"Freeze at {style['freeze']}")
        self.grand_total.setChecked(out["grand_total"])
        self.grand_label.setText(out["grand_total_label"])
        self.grand_label.setEnabled(out["grand_total"])
        self.summary.setChecked(out["summary_sheet"])
        self.formulas.setChecked(out["formulas"])
        day = next((c for c in prof["columns"] if c["id"] == "day_grid"), None)
        set_combo(self.days, day["days"] if day else "1-31", f"Days {day['days']}" if day else None)
        self._fill_columns(prof["columns"])
        for key, edit in self.wording.items():
            edit.setText(rules[key])
        self.warn.setValue(int(rules["warn_at_percent"]))
        set_combo(self.zero, rules["zero_limit"])
        self.unused.setChecked(rules["show_unused_cards"])
        for key, btn in self.colours.items():
            btn.set_color(style[key])
        self.use_cat.setChecked(style["use_category_colors"])

    def collect(self):
        return {
            "name": self.name.text(), "title": self.title.text(),
            "columns": self._collect_columns(), "categories": [],
            "rules": {**{k: e.text() for k, e in self.wording.items()},
                      "zero_limit": self.zero.currentData(), "warn_at_percent": self.warn.value(),
                      "show_unused_cards": self.unused.isChecked()},
            "sorting": {"cards": self.sort.currentData()},
            "style": {**{k: b.color for k, b in self.colours.items()},
                      "freeze": self.freeze.currentData(), "use_category_colors": self.use_cat.isChecked()},
            "output": {"formulas": self.formulas.isChecked(), "grand_total": self.grand_total.isChecked(),
                       "grand_total_label": self.grand_label.text(), "summary_sheet": self.summary.isChecked(),
                       "sheet_name": self.sheet.text(), "file_prefix": self.prefix.text()},
        }

    def load(self, name):
        try:
            prof = self.store.get(name) if name else P.default_profile()
        except KNOWN_ERRORS as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.current = name
        self._fill(prof)
        self.status.setText("")

    def refresh_list(self):
        names = self.store.names()
        default = self.store.default_name()
        target = self.current if self.current in names else (default if names else None)
        self.pick.blockSignals(True)
        self.pick.clear()
        if not names:
            self.pick.addItem("Standard layout (not saved yet)", None)
        for n in names:
            self.pick.addItem(n + ("  (default)" if n == default else ""), n)
        self.pick.setCurrentIndex(max(0, self.pick.findData(target)))
        self.pick.blockSignals(False)
        if target != self.current:
            self.load(target)

    def _picked(self, *_):
        name = self.pick.currentData()
        if name != self.current:
            self.load(name)

    # ---------------------------------------------------------- actions
    @guarded
    def save(self):
        prof = self.store.save(self.collect())                     # validates everything
        self.db.set_setting("org_name", self.org.text().strip())
        self.current = prof["name"]
        self.on_data_changed()
        self.status.setText(f"Saved '{prof['name']}'.")

    @guarded
    def reset(self):
        prof = P.default_profile()
        prof["name"] = self.name.text().strip() or prof["name"]
        self._fill(prof)
        self.status.setText("Standard settings loaded - click Save layout to keep them.")

    @guarded
    def new_layout(self):
        name, ok = QInputDialog.getText(self, APP_NAME, "Name for the new layout:")
        if ok and name.strip():
            prof = P.default_profile()
            prof["name"] = name.strip()
            saved = self.store.save(prof)
            self.current = saved["name"]
            self.on_data_changed()
            self.load(saved["name"])

    @guarded
    def make_default(self):
        if self.current in (_UNSET, None):
            QMessageBox.information(self, APP_NAME, "Save the layout first.")
            return
        self.store.set_default(self.current)
        self.on_data_changed()
        self.status.setText(f"'{self.current}' is now the default layout.")

    @guarded
    def delete_layout(self):
        if self.current in (_UNSET, None):
            QMessageBox.information(self, APP_NAME, "This layout has not been saved yet.")
            return
        if QMessageBox.question(self, APP_NAME, f"Delete the layout '{self.current}'?") == QMessageBox.Yes:
            self.store.delete(self.current)
            self.current = _UNSET
            self.on_data_changed()

    @guarded
    def export_layout(self):
        name = self.current if self.current not in (_UNSET, None) else None
        path, _ = QFileDialog.getSaveFileName(self, "Export layout", f"{name or 'layout'}.json",
                                              "Layout file (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(P.to_json(self.store.export_bundle(name)))
            self.status.setText("Exported the saved version of this layout, with its categories.")

    @guarded
    def import_layout(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import layout", "", "Layout file (*.json)")
        if not path:
            return
        with open(path, encoding="utf-8") as fh:
            prof = P.from_json(fh.read())
        if prof["name"] in self.store.names() and QMessageBox.question(
                self, APP_NAME, f"A layout called '{prof['name']}' already exists. Replace it?"
        ) != QMessageBox.Yes:
            return
        saved = self.store.import_bundle(prof, make_default=False)
        self.current = saved["name"]
        self.on_data_changed()
        self.load(saved["name"])
        self.status.setText(f"Imported '{saved['name']}' (its categories were added too).")


# ------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 660)
        self.db = Database()

        self.dashboard = DashboardPage(self.db)
        self.history = HistoryPage(self.db)
        self.cards = CardsPage(self.db, self.data_changed)
        self.categories = CategoriesPage(self.db, self.data_changed)
        self.layouts_page = LayoutPage(self.db, self.data_changed)
        self.report = ReportPage(self.db, self.dashboard.show_data, self.history.refresh,
                                 self.data_changed, lambda: self.goto(1))

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 24, 16, 16)
        sl.setSpacing(4)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        sub = QLabel("Fuel card reporting")
        sub.setObjectName("brandSub")
        sl.addWidget(brand)
        sl.addWidget(sub)
        sl.addSpacing(22)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, (label, page) in enumerate([
                ("Monthly Report", self.report), ("Dashboard", self.dashboard), ("Cards", self.cards),
                ("Categories", self.categories), ("Report Layout", self.layouts_page),
                ("History", self.history)]):
            b = QPushButton(label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=i: self.goto(n))
            self.nav.addButton(b, i)
            sl.addWidget(b)
            self.stack.addWidget(page)
        sl.addStretch(1)
        foot = QLabel(f"v{VERSION}\n{self.db.path}")
        foot.setObjectName("sideFoot")
        foot.setWordWrap(True)
        sl.addWidget(foot)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(side)
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.goto(0)

    def goto(self, index):
        self.nav.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)

    def data_changed(self):
        """Called when cards, categories or layouts change in any page."""
        self.cards.refresh()
        self.categories.refresh()
        self.report.refresh_profiles()
        self.layouts_page.refresh_list()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(STYLE + TAB_STYLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
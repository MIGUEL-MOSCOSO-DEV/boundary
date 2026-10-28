import json
import re
from datetime import datetime

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

BG = "#090D14"
SURFACE = "#111827"
SECONDARY = "#151E2B"
BORDER = "#263244"
TEXT = "#F1F5F9"
MUTED = "#94A3B8"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
ERROR = "#EF4444"
ICONS = {
    "dashboard": "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    "scope": "M12 3v4 M12 17v4 M3 12h4 M17 12h4 M12 7a5 5 0 1 0 0 10a5 5 0 0 0 0-10",
    "target": "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18 M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8",
    "servers": "M4 3h16v7H4z M4 14h16v7H4z M7 6h1 M7 17h1 M12 6h5 M12 17h5",
    "evidence": "M6 3h9l4 4v14H6z M14 3v5h5 M9 12h7 M9 16h5",
    "report": "M5 3h14v18H5z M8 15v3 M12 11v7 M16 7v11",
    "settings": "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
    "users": "M9 3a3 3 0 1 0 0 6a3 3 0 0 0 0-6 M3 19v-2a6 6 0 0 1 12 0v2 M17 4a3 3 0 0 1 0 6 M18 13a5 5 0 0 1 3 4v2",
    "shield": "M12 3l8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6z M8 12l3 3 5-6",
    "grid": "M3 3h18v18H3z M3 9h18 M3 15h18 M9 3v18 M15 3v18",
    "network": "M9 3h6v6H9z M2 16h6v6H2z M16 16h6v6h-6z M12 9v4 M5 16v-3h14v3",
    "capture": "M6 3h9l4 4v14H6z M14 3v5h5 M8 13h2l2-3 2 6 2-3h2",
    "flows": "M3 7h14l-3-3 M17 7l-3 3 M21 17H7l3-3 M7 17l3 3",
    "protocol": "M5 5h14v4H5z M5 15h14v4H5z M12 9v6",
    "alert": "M12 3l10 18H2z M12 9v5 M12 17h.01",
    "search": "M10 3a7 7 0 1 0 0 14a7 7 0 0 0 0-14 M15 15l6 6",
    "plus": "M12 4v16 M4 12h16",
    "play": "M7 4l13 8-13 8z",
    "stop": "M6 6h12v12H6z",
    "upload": "M12 16V3 M7 8l5-5 5 5 M4 15v6h16v-6",
    "download": "M12 3v13 M7 11l5 5 5-5 M4 17v4h16v-4",
    "folder": "M3 6h7l2 2h9v12H3z",
    "check": "M5 12l4 4L19 6",
    "close": "M6 6l12 12 M18 6L6 18",
    "clock": "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18 M12 7v6l4 2",
    "key": "M8 3a5 5 0 1 0 0 10a5 5 0 0 0 0-10 M12 12l9 9 M17 17l3-3",
    "lock": "M6 10h12v11H6z M8 10V7a4 4 0 0 1 8 0v3",
    "eye": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6",
    "info": "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18 M12 11v6 M12 7h.01",
    "chevron": "M9 5l7 7-7 7",
}


def icon(name, color=MUTED, size=20):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{ICONS.get(name, ICONS["evidence"])}" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    renderer = QSvgRenderer(svg.encode())
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label(text, kind="body", wrap=False):
    result = QLabel(text)
    result.setObjectName(kind)
    result.setWordWrap(wrap)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


def row(*widgets, spacing=10):
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch()
        else:
            layout.addWidget(widget)
    return layout


def column(parent=None, spacing=16, margins=0):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(spacing)
    return layout


def style(accent):
    return f"""
    QWidget{{background:{BG};color:{TEXT};font-family:'Segoe UI Variable','Segoe UI';font-size:13px;}}
    QMainWindow{{background:{BG};}}
    QFrame#sidebar{{background:#0D131E;border-right:1px solid #1D2838;}}
    QFrame#card,QFrame#panel{{background:{SURFACE};border:1px solid #202C3E;border-radius:12px;}}
    QFrame#toolbar{{background:{SURFACE};border:1px solid #202C3E;border-radius:10px;}}
    QFrame#sidebar QLabel,QFrame#card QLabel,QFrame#panel QLabel{{background:transparent;}}
    QLabel#title{{font-size:25px;font-weight:650;letter-spacing:-0.5px;}}
    QLabel#hero{{font-size:29px;font-weight:650;letter-spacing:-0.5px;}}
    QLabel#section{{font-size:16px;font-weight:600;}}
    QLabel#muted{{color:{MUTED};}}
    QLabel#eyebrow{{color:{MUTED};font-size:11px;font-weight:600;}}
    QLabel#mono{{font-family:'Cascadia Code','Consolas';font-size:12px;color:#B1C3D8;}}
    QLabel#stat{{font-size:29px;font-weight:650;}}
    QPushButton{{background:#182335;border:1px solid #2B3A50;border-radius:8px;padding:9px 14px;font-weight:550;}}
    QPushButton:hover{{background:#213047;border-color:#40536D;}}
    QPushButton:pressed{{background:#101B2B;}}
    QPushButton:disabled{{color:#58677D;background:#101823;border-color:#1D293B;}}
    QPushButton[primary='true']{{background:{accent};border-color:{accent};color:#071018;font-weight:650;}}
    QPushButton[primary='true']:hover{{background:{QColor(accent).lighter(112).name()};}}
    QPushButton[primary='true']:disabled{{background:#193344;border-color:#244150;color:#6B8292;}}
    QPushButton[quiet='true']{{background:transparent;border-color:transparent;color:{MUTED};}}
    QPushButton[quiet='true']:hover{{background:#182335;color:{TEXT};}}
    QPushButton:focus{{border-color:{accent};}}
    QLineEdit,QPlainTextEdit,QTextEdit,QSpinBox,QComboBox{{background:#0D1522;border:1px solid #29374B;border-radius:8px;padding:9px 11px;selection-background-color:#334A6B;color:{TEXT};}}
    QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus,QSpinBox:focus{{border-color:{accent};}}
    QLineEdit[invalid='true']{{border-color:{ERROR};}}
    QLineEdit:disabled{{color:#687990;}}
    QPlainTextEdit{{font-family:'Cascadia Code','Consolas';font-size:12px;}}
    QComboBox::drop-down{{border:0;width:24px;}}
    QComboBox QAbstractItemView{{background:{SURFACE};border:1px solid {BORDER};selection-background-color:#293A55;padding:6px;}}
    QListWidget#navigation{{background:transparent;border:0;outline:0;}}
    QListWidget#navigation::item{{padding:11px 12px;border-radius:8px;color:#9BAAC0;margin-bottom:3px;}}
    QListWidget#navigation::item:hover{{background:#152134;color:{TEXT};}}
    QListWidget#navigation::item:selected{{background:#192C40;color:{accent};}}
    QTableWidget{{background:{SURFACE};alternate-background-color:#111B2A;border:0;gridline-color:#1F2B3D;outline:0;selection-background-color:#20334C;selection-color:{TEXT};}}
    QTableWidget::item{{padding:9px;border-bottom:1px solid #1D2A3C;}}
    QTableWidget::item:hover{{background:#18273B;}}
    QHeaderView::section{{background:#111A28;color:#8FA1B9;border:0;border-bottom:1px solid #28364A;padding:12px 10px;font-size:11px;font-weight:600;}}
    QTableCornerButton::section{{background:#111A28;border:0;}}
    QScrollBar:vertical{{background:transparent;width:7px;margin:2px;}}
    QScrollBar::handle:vertical{{background:#314158;border-radius:3px;min-height:28px;}}
    QScrollBar::handle:vertical:hover{{background:#506582;}}
    QScrollBar:horizontal{{background:transparent;height:7px;margin:2px;}}
    QScrollBar::handle:horizontal{{background:#314158;border-radius:3px;min-width:28px;}}
    QScrollBar::add-line,QScrollBar::sub-line{{width:0;height:0;}}
    QScrollBar::add-page,QScrollBar::sub-page{{background:transparent;}}
    QCheckBox{{spacing:9px;background:transparent;}}
    QCheckBox::indicator{{width:16px;height:16px;border:1px solid #405069;border-radius:4px;background:#0D1522;}}
    QCheckBox::indicator:checked{{background:{accent};border-color:{accent};}}
    QProgressBar{{background:#18263B;border:0;border-radius:3px;max-height:5px;}}
    QProgressBar::chunk{{background:{accent};border-radius:3px;}}
    QTabWidget::pane{{border:1px solid #263244;border-radius:10px;background:{SURFACE};}}
    QTabBar::tab{{padding:11px 17px;background:transparent;color:{MUTED};border-bottom:2px solid transparent;}}
    QTabBar::tab:selected{{color:{TEXT};border-bottom-color:{accent};}}
    QSplitter::handle{{background:#1D2A3B;}}
    QSplitter::handle:horizontal{{width:2px;}}
    QSplitter::handle:vertical{{height:2px;}}
    QToolTip{{background:#1B2A40;color:{TEXT};border:1px solid #344762;padding:7px;border-radius:6px;}}
    QDialog{{background:{BG};}}
    QDialogButtonBox{{background:transparent;}}
    QMenu{{background:#131E2E;border:1px solid #304159;padding:7px;border-radius:8px;}}
    QMenu::item{{padding:8px 20px;border-radius:5px;}}
    QMenu::item:selected{{background:#243750;}}
    """


def initialize(app, accent):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, BG),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, SURFACE),
        (QPalette.ColorRole.AlternateBase, SECONDARY),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.Button, SURFACE),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.Highlight, "#253D5B"),
        (QPalette.ColorRole.HighlightedText, TEXT),
        (QPalette.ColorRole.ToolTipBase, SECONDARY),
        (QPalette.ColorRole.ToolTipText, TEXT),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(style(accent))
    if hasattr(app.styleHints(), "setColorScheme"):
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)


class Button(QPushButton):
    def __init__(
        self, text, callback=None, glyph=None, accent="#22D3EE", primary=False, quiet=False
    ):
        super().__init__(text)
        self.setProperty("primary", primary)
        self.setProperty("quiet", quiet)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        if glyph:
            self.setIcon(icon(glyph, "#071018" if primary else MUTED, 18))
            self.setIconSize(QSize(18, 18))
        if callback:
            self.clicked.connect(callback)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(1)
        self.hover = QPropertyAnimation(self.effect, b"opacity", self)
        self.hover.setDuration(140)

    def enterEvent(self, event):
        self.hover.stop()
        self.hover.setStartValue(0.78)
        self.hover.setEndValue(1)
        self.hover.start()
        super().enterEvent(event)


class Card(QFrame):
    def __init__(self, title=None, description=None):
        super().__init__()
        self.setObjectName("card")
        self.box = column(self, 14, 20)
        if title:
            self.box.addWidget(label(title, "section"))
        if description:
            self.box.addWidget(label(description, "muted", True))


class Metric(Card):
    def __init__(self, title, glyph, accent):
        super().__init__()
        top = QHBoxLayout()
        top.addWidget(label(title, "muted"))
        top.addStretch()
        image = QLabel()
        image.setPixmap(icon(glyph, accent, 19).pixmap(19, 19))
        top.addWidget(image)
        self.box.addLayout(top)
        self.value = label("—", "stat")
        self.note = label("Sin ejecución", "muted")
        self.box.addWidget(self.value)
        self.box.addWidget(self.note)
        self.setMinimumWidth(155)
        self.setMaximumHeight(130)

    def set(self, value, note="Observado en el reporte"):
        self.value.setText(str(value))
        self.note.setText(note)


class Empty(QFrame):
    def __init__(self, title, description, glyph, accent, action=None, callback=None):
        super().__init__()
        self.setObjectName("panel")
        box = column(self, 14, 28)
        box.addStretch()
        image = QLabel()
        image.setPixmap(icon(glyph, accent, 46).pixmap(46, 46))
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(image)
        heading = label(title, "hero", True)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(heading)
        text = label(description, "muted", True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(text)
        if action:
            center = QHBoxLayout()
            center.addStretch()
            center.addWidget(Button(action, callback, "plus", accent, True))
            center.addStretch()
            box.addLayout(center)
        box.addStretch()


class Search(QLineEdit):
    def __init__(self, placeholder):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(440)


class BadgeDelegate(QStyledItemDelegate):
    COLORS = {
        "complete": (SUCCESS, "Completado"),
        "error": (ERROR, "Error"),
        "blocked": (WARNING, "Bloqueado"),
        "pass": (SUCCESS, "Correcto"),
        "violation": (ERROR, "Violación"),
        "review": (WARNING, "Revisar"),
        "inconclusive": (MUTED, "Inconcluso"),
        "high": (ERROR, "Alta"),
        "warning": (WARNING, "Advertencia"),
        "info": ("#22D3EE", "Información"),
        "allowed": (SUCCESS, "Permitido"),
        "denied": ("#A5B4FC", "Denegado"),
        "pending": (MUTED, "No evaluado"),
    }

    def paint(self, painter, option, index):
        state = index.data(Qt.ItemDataRole.UserRole + 1)
        if state not in self.COLORS:
            super().paint(painter, option, index)
            return
        painter.save()
        background = "#20334C" if option.state & QStyle.StateFlag.State_Selected else SURFACE
        painter.fillRect(option.rect, QColor(background))
        color, text = self.COLORS[state]
        width = min(option.rect.width() - 14, option.fontMetrics.horizontalAdvance(text) + 35)
        rect = QRectF(option.rect.x() + 8, option.rect.center().y() - 12, width, 24)
        tint = QColor(color)
        tint.setAlpha(24)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(rect.left() + 9, rect.center().y() - 2, 4, 4))
        painter.setPen(QColor(color))
        painter.drawText(rect.adjusted(20, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


class Table(QTableWidget):
    selected = Signal(object)
    activated = Signal(object)

    def __init__(self, headers, status_columns=()):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(44)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setMinimumSectionSize(70)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setMouseTracking(True)
        for index in status_columns:
            self.setItemDelegateForColumn(index, BadgeDelegate(self))
        self.itemSelectionChanged.connect(self.emit_selection)
        self.itemDoubleClicked.connect(lambda item: self.activated.emit(self.payload(item.row())))
        self.setMinimumHeight(160)

    def payload(self, row):
        item = self.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def emit_selection(self):
        if self.currentRow() >= 0:
            self.selected.emit(self.payload(self.currentRow()))

    def fill(self, rows):
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for row_index, (values, payload, states) in enumerate(rows):
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value) if value is not None else "—")
                if type(value) in (int, float):
                    item.setData(Qt.ItemDataRole.DisplayRole, value)
                item.setToolTip(item.text())
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, payload)
                if column_index in states:
                    item.setData(Qt.ItemDataRole.UserRole + 1, states[column_index])
                self.setItem(row_index, column_index, item)
        self.setSortingEnabled(True)


class Inspector(Card):
    def __init__(self, title="Inspector de evidencia"):
        super().__init__(title, "Selecciona un registro para inspeccionar sus datos.")
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setPlaceholderText(
            "La evidencia aparecerá aquí. No se muestran cuerpos de respuesta ni credenciales."
        )
        self.box.addWidget(self.content, 1)
        self.setMinimumWidth(250)

    def display(self, value):
        self.content.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))


class Worker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    note = Signal(str)
    ended = Signal()

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(self.operation(self.note.emit))
        except Exception as error:
            self.failed.emit(str(error) or type(error).__name__)
        finally:
            self.ended.emit()


class Toast(QFrame):
    def __init__(self, parent, text, color):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setFixedWidth(360)
        box = QHBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        image = QLabel()
        image.setPixmap(icon("info", color, 22).pixmap(22, 22))
        box.addWidget(image)
        body = label(text, wrap=True)
        box.addWidget(body, 1)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setDuration(160)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.adjustSize()
        self.show()
        self.raise_()
        self.animation.start()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(4800, self.deleteLater)


class Shell(QMainWindow):
    def __init__(self, name, subtitle, accent, brand_icon):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.name, self.accent = name, accent
        self.busy = False
        self.pending_close = False
        self.thread = None
        self.worker = None
        self.task_callback = None
        self.cancel_callback = None
        self.toast = None
        self.setWindowTitle(name + " / " + subtitle)
        self.setWindowIcon(icon(brand_icon, accent, 32))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1400, screen.width() - 70), min(940, screen.height() - 70))
        self.setMinimumSize(1060, 740)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(216)
        side = column(sidebar, 8, 16)
        brand = QHBoxLayout()
        symbol = QLabel()
        symbol.setPixmap(icon(brand_icon, accent, 27).pixmap(27, 27))
        brand.addWidget(symbol)
        brand.addWidget(label(name, "section"))
        side.addLayout(brand)
        side.addWidget(label(subtitle, "muted", True))
        side.addSpacing(28)
        side.addWidget(label("Workspace", "eyebrow"))
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setIconSize(QSize(19, 19))
        side.addWidget(self.navigation, 1)
        side.addWidget(label("Datos locales", "eyebrow"))
        side.addWidget(label("Sin telemetría ni servicios externos.", "muted", True))
        self.workspace_label = label("Proyecto sin cargar", "mono", True)
        side.addWidget(self.workspace_label)
        outer.addWidget(sidebar)
        self.main = QWidget()
        main = column(self.main, 0, 0)
        self.header = QFrame()
        self.header.setObjectName("toolbar")
        self.header.setStyleSheet("QFrame#toolbar{border-radius:0;border-width:0 0 1px 0;}")
        header_box = QHBoxLayout(self.header)
        header_box.setContentsMargins(28, 18, 28, 18)
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.breadcrumb = label(name + " / Workspace", "eyebrow")
        self.page_title = label("Resumen", "title")
        titles.addWidget(self.breadcrumb)
        titles.addWidget(self.page_title)
        header_box.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(10)
        header_box.addLayout(self.header_actions)
        main.addWidget(self.header)
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        main.addWidget(self.progress)
        footer = QWidget()
        footer_box = QHBoxLayout(footer)
        footer_box.setContentsMargins(28, 10, 28, 12)
        self.status = label("Listo. No hay operaciones activas.", "muted")
        self.status.setWordWrap(True)
        footer_box.addWidget(self.status, 1)
        self.stop_button = Button("Cancelar", self.cancel_task, "stop", accent, quiet=True)
        self.stop_button.hide()
        footer_box.addWidget(self.stop_button)
        main.addWidget(footer)
        outer.addWidget(self.main, 1)
        self.pages = {}
        self.page_titles = []
        self.navigation.currentRowChanged.connect(self.navigate)
        self.log = []
        self.fade = QPropertyAnimation(self.stack, b"windowOpacity", self)

    def add_page(self, title, glyph):
        page = QWidget()
        layout = column(page, 20, 28)
        self.stack.addWidget(page)
        item = QListWidgetItem(icon(glyph), title)
        self.navigation.addItem(item)
        self.pages[title] = (page, layout)
        self.page_titles.append(title)
        if self.navigation.currentRow() < 0:
            self.navigation.setCurrentRow(0)
        return layout

    def show_page(self, title):
        self.navigation.setCurrentRow(self.page_titles.index(title))

    @Slot(int)
    def navigate(self, index):
        if index < 0 or index >= len(self.page_titles):
            return
        self.stack.setCurrentIndex(index)
        self.page_title.setText(self.page_titles[index])
        self.breadcrumb.setText(self.name + " / " + self.page_titles[index])
        effect = QGraphicsOpacityEffect(self.stack.currentWidget())
        self.stack.currentWidget().setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(140)
        animation.setStartValue(0.5)
        animation.setEndValue(1)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._page_animation = animation

    def shortcut(self, sequence, callback):
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.activated.connect(callback)
        return shortcut

    def notify(self, text, error=False):
        self.status.setText(text)
        self.log.append(
            {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "event": text}
        )
        self.log = self.log[-100:]
        if self.toast:
            try:
                self.toast.deleteLater()
            except RuntimeError:
                pass
        self.toast = Toast(self.main, text, ERROR if error else self.accent)
        self.place_toast()

    def place_toast(self):
        if self.toast:
            try:
                self.toast.move(max(12, self.main.width() - self.toast.width() - 24), 100)
            except RuntimeError:
                self.toast = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.place_toast()

    def task(self, title, operation, callback, cancel=None):
        if self.busy:
            self.notify("Hay una operación activa. Espera o cancélala antes de continuar.")
            return
        self.busy = True
        self.status.setText(title)
        self.task_callback = callback
        self.cancel_callback = cancel
        self.progress.setRange(0, 0)
        self.progress.show()
        self.stop_button.setVisible(cancel is not None)
        self.thread = QThread(self)
        self.worker = Worker(operation)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.note.connect(self.task_note)
        self.worker.succeeded.connect(self.task_success)
        self.worker.failed.connect(self.task_failed)
        self.worker.ended.connect(self.thread.quit)
        self.worker.ended.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.task_ended)
        self.thread.start()
        self.update_actions()

    @Slot(str)
    def task_note(self, text):
        self.status.setText(text)
        match = re.search(r"(?:Progress|Casos procesados:)\s*(\d+)/(\d+)", text)
        if match:
            self.progress.setRange(0, int(match.group(2)))
            self.progress.setValue(int(match.group(1)))

    @Slot(object)
    def task_success(self, value):
        try:
            if self.task_callback:
                self.task_callback(value)
        except Exception as error:
            self.notify(str(error) or type(error).__name__, True)

    @Slot(str)
    def task_failed(self, message):
        self.notify(message, True)

    @Slot()
    def task_ended(self):
        self.busy = False
        self.progress.hide()
        self.stop_button.hide()
        self.worker = None
        self.task_callback = None
        self.cancel_callback = None
        thread = self.thread
        self.thread = None
        thread.wait()
        thread.deleteLater()
        self.update_actions()
        if self.pending_close:
            self.close()

    def update_actions(self):
        pass

    def cancel_task(self):
        if self.cancel_callback:
            self.cancel_callback()
            self.status.setText(
                "Cancelación solicitada. Esperando el cierre seguro de la operación…"
            )

    def closeEvent(self, event):
        if self.busy:
            if self.pending_close or confirm(
                self,
                "Operación activa",
                "¿Detener la operación y cerrar? Se conservarán los resultados que el motor haya completado.",
                "Detener y cerrar",
            ):
                self.pending_close = True
                self.cancel_task()
            event.ignore()
        else:
            for animation in self.findChildren(QPropertyAnimation):
                animation.stop()
            event.accept()


def confirm(parent, title, text, accept="Continuar"):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(440)
    box = column(dialog, 18, 24)
    box.addWidget(label(title, "section"))
    box.addWidget(label(text, "muted", True))
    buttons = QHBoxLayout()
    buttons.addStretch()
    cancel = Button("Volver", dialog.reject, quiet=True)
    proceed = Button(accept, dialog.accept, accent=parent.accent, primary=True)
    buttons.addWidget(cancel)
    buttons.addWidget(proceed)
    box.addLayout(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted


def text_field(title, tooltip=None, multiline=False):
    wrapper = QWidget()
    box = column(wrapper, 7, 0)
    box.addWidget(label(title, "muted"))
    edit = QPlainTextEdit() if multiline else QLineEdit()
    if multiline:
        edit.setMinimumHeight(85)
        edit.setMaximumHeight(145)
    if tooltip:
        edit.setToolTip(tooltip)
    box.addWidget(edit)
    return wrapper, edit


def scrollable(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll

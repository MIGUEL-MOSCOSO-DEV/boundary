import math
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QWidget,
)

from .design import BORDER, MUTED, TEXT, BadgeDelegate


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class Bars(QWidget):
    def __init__(self, accent, unit=""):
        super().__init__()
        self.accent = accent
        self.unit = unit
        self.values = []
        self.hits = []
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def set_values(self, values):
        self.values = list(values)[:8]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Segoe UI Variable", 10))
        if not self.values:
            painter.setPen(QColor(MUTED))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin observaciones para representar"
            )
            return
        maximum = max(float(value) for _, value in self.values) or 1
        available = self.width() - 170
        height = max(27, min(38, (self.height() - 14) / len(self.values)))
        self.hits = []
        for index, (name, value) in enumerate(self.values):
            y = index * height + 10
            painter.setPen(QColor(MUTED))
            painter.drawText(
                QRectF(0, y - 3, 115, 23), Qt.AlignmentFlag.AlignVCenter, str(name)[:22]
            )
            rect = QRectF(122, y + 3, max(2, available * float(value) / maximum), 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1D2A3F"))
            painter.drawRoundedRect(QRectF(122, y + 3, available, 8), 4, 4)
            painter.setBrush(QColor(self.accent))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(TEXT))
            painter.drawText(
                QRectF(self.width() - 47, y - 3, 47, 23),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(value),
            )
            self.hits.append((QRectF(0, y, self.width(), height), f"{name}: {value} {self.unit}"))

    def mouseMoveEvent(self, event):
        for rect, text in self.hits:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), text, self)
                return


class Activity(QWidget):
    selected = Signal(object)

    def __init__(self, accent):
        super().__init__()
        self.accent = accent
        self.report = None
        self.bins = []
        self.hover = -1
        self.setMinimumHeight(160)
        self.setMouseTracking(True)

    def set_report(self, report):
        self.report = report
        self.bins = []
        if report and report.get("first"):
            first, last = timestamp(report["first"]), timestamp(report["last"])
            span = max(0.001, last - first)
            counts = [0] * 24
            for flow in report.get("flows", []):
                index = min(23, max(0, int((timestamp(flow["first"]) - first) / span * 24)))
                counts[index] += 1
            self.bins = [
                (first + span * i / 24, first + span * (i + 1) / 24, count)
                for i, count in enumerate(counts)
            ]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.bins:
            painter.setPen(QColor(MUTED))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "La actividad aparecerá con los flujos observados",
            )
            return
        width = (self.width() - 10) / 24
        maximum = max(item[2] for item in self.bins) or 1
        baseline = self.height() - 30
        height = self.height() - 50
        for fraction in [0.25, 0.5, 0.75, 1]:
            painter.setPen(QPen(QColor("#243046"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(
                0,
                int(baseline - height * fraction),
                self.width(),
                int(baseline - height * fraction),
            )
        for index, (_, _, count) in enumerate(self.bins):
            painter.setPen(Qt.PenStyle.NoPen)
            color = QColor(self.accent)
            color.setAlpha(240 if index == self.hover else 155)
            painter.setBrush(color)
            h = height * count / maximum
            if count:
                painter.drawRoundedRect(QRectF(index * width + 3, baseline - h, width - 6, h), 3, 3)
        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("Consolas", 9))
        first = datetime.fromtimestamp(self.bins[0][0], timezone.utc).strftime("%H:%M:%S")
        last = datetime.fromtimestamp(self.bins[-1][1], timezone.utc).strftime("%H:%M:%S UTC")
        painter.drawText(0, self.height() - 8, first)
        painter.drawText(
            QRectF(self.width() - 140, self.height() - 25, 140, 22),
            Qt.AlignmentFlag.AlignRight,
            last,
        )

    def mouseMoveEvent(self, event):
        if self.bins:
            self.hover = min(23, max(0, int(event.position().x() / max(1, self.width()) * 24)))
            first, last, count = self.bins[self.hover]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{count} inicios de flujo / {datetime.fromtimestamp(first, timezone.utc).strftime('%H:%M:%S')}–{datetime.fromtimestamp(last, timezone.utc).strftime('%H:%M:%S')} UTC",
                self,
            )
            self.update()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()

    def mousePressEvent(self, event):
        if self.bins and 0 <= self.hover < len(self.bins):
            self.selected.emit(self.bins[self.hover][:2])


class AssetMap(QWidget):
    selected = Signal(object)

    def __init__(self, accent):
        super().__init__()
        self.accent = accent
        self.assets = []
        self.rects = []
        self.setMinimumHeight(270)
        self.setMouseTracking(True)

    def set_assets(self, assets):
        self.assets = list(assets)[:18]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.rects = []
        if not self.assets:
            painter.setPen(QColor(MUTED))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "El mapa aparece después de una observación",
            )
            return
        columns = max(2, min(4, self.width() // 235))
        w = self.width() / columns
        centers = []
        for index, asset in enumerate(self.assets):
            centers.append(QPointF(w * (index % columns + 0.5), 50 + 95 * (index // columns)))
        seen = {}
        painter.setPen(QPen(QColor("#245269"), 1.4, Qt.PenStyle.DashLine))
        for index, asset in enumerate(self.assets):
            for address in (asset.get("visits") or [{}])[-1].get("addresses", []):
                if address in seen:
                    painter.drawLine(centers[seen[address]], centers[index])
                else:
                    seen[address] = index
        for index, asset in enumerate(self.assets):
            point = centers[index]
            rect = QRectF(point.x() - w / 2 + 7, point.y() - 32, w - 14, 64)
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.setBrush(QColor("#111F2E"))
            painter.drawRoundedRect(rect, 9, 9)
            color = {"complete": "#10B981", "blocked": "#F59E0B", "error": "#EF4444"}.get(
                asset["outcome"], self.accent
            )
            painter.setPen(QColor(TEXT))
            painter.setFont(QFont("Consolas", 9))
            target = asset["target"].split("://", 1)[-1]
            painter.drawText(
                rect.adjusted(13, 8, -8, -25), Qt.AlignmentFlag.AlignVCenter, target[:27]
            )
            painter.setPen(QColor(color))
            painter.setFont(QFont("Segoe UI Variable", 9))
            painter.drawText(
                rect.adjusted(13, 31, -8, -5), Qt.AlignmentFlag.AlignVCenter, asset["outcome"]
            )
            self.rects.append((rect, asset))
        self.setMinimumHeight(max(270, math.ceil(len(self.assets) / columns) * 95))

    def mouseMoveEvent(self, event):
        for rect, asset in self.rects:
            if rect.contains(event.position()):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                QToolTip.showText(event.globalPosition().toPoint(), asset["target"], self)
                return
        self.unsetCursor()

    def mousePressEvent(self, event):
        for rect, asset in self.rects:
            if rect.contains(event.position()):
                self.selected.emit(asset)
                return


class PermissionMatrix(QTableWidget):
    selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(60)
        self.horizontalHeader().setMinimumSectionSize(120)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cellClicked.connect(self.inspect)

    def set_context(self, config, report=None, observed=True):
        if report and observed:
            cases = report.get("cases", [])
            identities = list(
                dict.fromkeys(result["identity"] for case in cases for result in case["results"])
            )
        else:
            cases = config.get("cases", [])
            identities = list(config.get("identities", {}))
        self.setColumnCount(1 + len(identities))
        self.setHorizontalHeaderLabels(["Recurso / Política", *identities])
        self.setRowCount(len(cases))
        self.setColumnWidth(0, 300)
        for column in range(1, 1 + len(identities)):
            self.setColumnWidth(column, 155)
            self.setItemDelegateForColumn(column, BadgeDelegate(self))
        for row_index, case in enumerate(cases):
            self.setItem(
                row_index,
                0,
                QTableWidgetItem(
                    case["name"]
                    + "\n"
                    + case.get("method", "GET")
                    + " "
                    + case.get("path", case.get("url", ""))
                ),
            )
            results = {result["identity"]: result for result in case.get("results", [])}
            for column, identity in enumerate(identities, 1):
                result = results.get(identity)
                expected = (
                    result["expected"]
                    if result
                    else "allow"
                    if identity in case.get("allow", [])
                    else "deny"
                )
                if result and observed:
                    state = (
                        ("allowed" if expected == "allow" else "denied")
                        if result["verdict"] == "pass"
                        else result["verdict"]
                    )
                elif observed:
                    state = "pending"
                else:
                    state = "allowed" if expected == "allow" else "denied"
                display = BadgeDelegate.COLORS[state][1]
                item = QTableWidgetItem(display)
                payload = {
                    "case": case["name"],
                    "identity": identity,
                    "expected": expected,
                    "observed": result or "No evaluado",
                }
                item.setData(Qt.ItemDataRole.UserRole, payload)
                item.setData(Qt.ItemDataRole.UserRole + 1, state)
                item.setToolTip(
                    "Política esperada: " + ("Permitido" if expected == "allow" else "Denegado")
                )
                self.setItem(row_index, column, item)

    def inspect(self, row, column):
        item = self.item(row, column)
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.selected.emit(item.data(Qt.ItemDataRole.UserRole))

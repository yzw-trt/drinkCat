"""半透明置顶浮窗与快速记录。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCloseEvent, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# 半透明玻璃感按钮；子控件关闭 WA_TranslucentBackground，减轻 Win 上文字不绘制问题
_FLOAT_BTN_QSS = """
QPushButton {
    background-color: rgba(70, 145, 220, 0.52);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.55);
    border-radius: 8px;
    padding: 4px 8px;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 9pt;
    font-weight: 600;
    min-width: 46px;
}
QPushButton:hover {
    background-color: rgba(90, 165, 235, 0.68);
    border: 1px solid rgba(255, 255, 255, 0.75);
}
QPushButton:pressed {
    background-color: rgba(45, 115, 190, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.5);
}
"""


class FloatingPanel(QWidget):
    """可拖拽的小型浮窗。"""

    add_water = pyqtSignal(int)
    open_settings = pyqtSignal()
    hide_to_tray = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DrinkCatFloat")
        self._drag_pos: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._title = QLabel("喝水喵")
        self._title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))

        self._stats = QLabel("")
        self._stats.setFont(QFont("Microsoft YaHei UI", 9))
        self._stats.setWordWrap(True)

        self._hint = QLabel("")
        self._hint.setFont(QFont("Microsoft YaHei UI", 8))
        self._hint.setStyleSheet("color: rgba(255,255,255,160);")

        row = QHBoxLayout()
        for ml in (100, 200, 250, 500):
            b = QPushButton(f"+{ml} ml")
            b.setFixedHeight(30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            b.setStyleSheet(_FLOAT_BTN_QSS)
            b.clicked.connect(lambda _=False, m=ml: self.add_water.emit(m))
            row.addWidget(b)

        settings_btn = QPushButton("设置")
        settings_btn.setFixedHeight(30)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        settings_btn.setStyleSheet(_FLOAT_BTN_QSS)
        settings_btn.clicked.connect(self.open_settings.emit)
        row.addWidget(settings_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._stats)
        layout.addWidget(self._hint)
        layout.addLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)

        self.setFixedWidth(360)
        # 无边框 + 样式表后，布局 sizeHint 常略小于 Windows 实际所需高度，会触发 setGeometry 警告
        self.updateGeometry()
        _h = max(self.sizeHint().height(), 156)
        self.setMinimumHeight(_h)

    def set_opacity(self, alpha: float) -> None:
        a = max(0.35, min(1.0, alpha))
        self.setWindowOpacity(a)

    def update_display(
        self,
        today_ml: int,
        goal_ml: int,
        interval_min: int,
        last_drink_line: str,
        advice_line: str,
    ) -> None:
        core = (
            f"今日：{today_ml} / {goal_ml} ml\n"
            f"建议间隔：约 {interval_min} 分钟\n"
            f"{last_drink_line}"
        )
        if goal_ml > 0 and today_ml >= goal_ml:
            self._stats.setTextFormat(Qt.TextFormat.RichText)
            self._stats.setText(
                core
                + "<br><span style='color:#a8f5cf;font-weight:600;'>"
                "今日目标已达成 · 给自己点个赞吧</span>"
            )
        else:
            self._stats.setTextFormat(Qt.TextFormat.PlainText)
            self._stats.setText(core)
        self._hint.setText(advice_line[:120] + ("…" if len(advice_line) > 120 else ""))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        p.setBrush(QColor(28, 32, 40, 210))
        p.drawRoundedRect(rect, 12, 12)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()
        self.hide_to_tray.emit()

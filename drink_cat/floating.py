"""半透明置顶浮窗与快速记录。"""

from __future__ import annotations

import base64
from urllib.parse import unquote_to_bytes

from PyQt6.QtCore import QByteArray, QPoint, QRectF, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QCloseEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtSvg import QSvgRenderer

    _HAS_QSVG = True
except ImportError:
    QSvgRenderer = None  # type: ignore[misc, assignment]
    _HAS_QSVG = False

_WEATHER_ICON_CORNER_RADIUS = 15


def _bytes_to_weather_pixmap(raw: bytes) -> QPixmap | None:
    """
    PNG/WebP 等走 QImageReader；SVG 在打包环境常缺 imageformats/qsvg 插件，
    需用 QSvgRenderer 栅格化（不依赖插件）。
    """
    pix = QPixmap()
    if pix.loadFromData(raw):
        return pix
    if not _HAS_QSVG or QSvgRenderer is None:
        return None
    renderer = QSvgRenderer(QByteArray(raw))
    if not renderer.isValid():
        return None
    # 固定输出栅格边长，避免 defaultSize 为 0 或过小；与后续 scaled(52) 衔接
    out = 64
    img = QImage(out, out, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    renderer.render(p, QRectF(0, 0, out, out))
    p.end()
    return QPixmap.fromImage(img)


def _pixmap_from_data_url(url: str) -> QPixmap | None:
    """本地解析 data: URL；不使用 QNetworkAccessManager。"""
    if not url.startswith("data:"):
        return None
    comma = url.find(",")
    if comma < 0:
        return None
    meta = url[5:comma].lower()
    payload = url[comma + 1 :]
    try:
        if ";base64" in meta:
            raw = base64.b64decode(payload.encode("ascii"), validate=False)
        else:
            raw = unquote_to_bytes(payload)
    except Exception:
        return None
    return _bytes_to_weather_pixmap(raw)


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


class RoundedWeatherIconLabel(QLabel):
    """天气 PNG 按圆角矩形裁剪显示，与浮窗整体圆角风格一致。"""

    def __init__(self, corner_radius: int = _WEATHER_ICON_CORNER_RADIUS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._corner_radius = corner_radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        pm = self.pixmap()
        if pm is None or pm.isNull():
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rr = float(self._corner_radius)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), rr, rr)
        p.setClipPath(path)
        x = (self.width() - pm.width()) // 2
        y = (self.height() - pm.height()) // 2
        p.drawPixmap(x, y, pm)


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

        self._nam = QNetworkAccessManager(self)
        self._icon_reply: QNetworkReply | None = None
        self._pending_icon_url: str | None = None
        self._last_loaded_icon_url: str | None = None

        self._title = QLabel("喝水汪")
        self._title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))

        self._stats = QLabel("")
        self._stats.setFont(QFont("Microsoft YaHei UI", 9))
        self._stats.setWordWrap(True)
        self._stats.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._stats.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._weather_icon = RoundedWeatherIconLabel()
        self._weather_icon.setFixedSize(56, 56)
        self._weather_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weather_icon.setScaledContents(False)
        # 勿对 WA_TranslucentBackground 的子控件套 QGraphicsOpacityEffect，Win 上易导致 pixmap 整片不画

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 2, 0, 0)
        right_col.setSpacing(0)
        right_col.addWidget(self._weather_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        right_col.addStretch(1)

        self._weather_strip = QWidget()
        self._weather_strip.setLayout(right_col)
        self._weather_strip.setFixedWidth(60)
        self._weather_strip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(2)
        left_col.addWidget(self._title)
        left_col.addWidget(self._stats)
        left_col.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        top_row.addLayout(left_col, stretch=1)
        top_row.addWidget(self._weather_strip, 0, Qt.AlignmentFlag.AlignTop)

        self._hint = QLabel("")
        self._hint.setFont(QFont("Microsoft YaHei UI", 8))
        self._hint.setWordWrap(True)
        self._hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

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
        layout.addLayout(top_row)
        layout.addWidget(self._hint)
        layout.addLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)

        self.setFixedWidth(360)
        self.updateGeometry()
        _h = max(self.sizeHint().height(), 156)
        self.setMinimumHeight(_h)

    def set_opacity(self, alpha: float) -> None:
        a = max(0.35, min(1.0, alpha))
        self.setWindowOpacity(a)

    def _abort_icon_request(self) -> None:
        reply = self._icon_reply
        self._icon_reply = None
        if reply is None:
            return
        # abort() 会同步触发 finished；若不断开，槽内已 deleteLater 并把 _icon_reply 清空后会与下面逻辑打架
        try:
            reply.finished.disconnect(self._on_weather_icon_finished)
        except TypeError:
            pass
        reply.abort()
        reply.deleteLater()

    def _on_weather_icon_finished(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        if reply != self._icon_reply:
            reply.deleteLater()
            return
        self._icon_reply = None
        url_done = reply.url().toString()
        if self._pending_icon_url and url_done != self._pending_icon_url:
            reply.deleteLater()
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            self._weather_icon.clear()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        pix = _bytes_to_weather_pixmap(data)
        if pix is None or pix.isNull():
            self._weather_icon.clear()
            return
        self._apply_weather_pixmap(pix, url_done)

    def _apply_weather_pixmap(self, pix: QPixmap, url_for_cache: str) -> None:
        self._last_loaded_icon_url = url_for_cache
        scaled = pix.scaled(
            52,
            52,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._weather_icon.setPixmap(scaled)

    def _set_weather_icon_url(self, url: str | None) -> None:
        self._abort_icon_request()
        if not url:
            self._pending_icon_url = None
            self._last_loaded_icon_url = None
            self._weather_icon.clear()
            return
        pm = self._weather_icon.pixmap()
        if url == self._last_loaded_icon_url and pm is not None and not pm.isNull():
            return
        self._pending_icon_url = url
        if url.startswith("data:"):
            loaded = _pixmap_from_data_url(url)
            if loaded is None or loaded.isNull():
                self._weather_icon.clear()
                self._pending_icon_url = None
                self._last_loaded_icon_url = None
                return
            self._apply_weather_pixmap(loaded, url)
            return
        req = QNetworkRequest(QUrl(url))
        self._icon_reply = self._nam.get(req)
        self._icon_reply.finished.connect(self._on_weather_icon_finished)

    def update_display(
        self,
        today_ml: int,
        goal_ml: int,
        since_last_drink_line: str,
        last_drink_line: str,
        advice_line: str,
        *,
        weather_icon_url: str | None = None,
    ) -> None:
        core = (
            f"今日：{today_ml} / {goal_ml} ml\n"
            f"{since_last_drink_line}\n"
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

        # 右侧仅实时天气图标；最后一行说明在 _hint 独占整行（文案为当日代表时次，可与图标不一致）
        self._weather_strip.setVisible(bool(weather_icon_url))
        if weather_icon_url:
            self._weather_icon.show()
            self._set_weather_icon_url(weather_icon_url)
        else:
            self._weather_icon.hide()
            self._abort_icon_request()
            self._pending_icon_url = None
            self._last_loaded_icon_url = None

        # 天气说明整行展示，少截断
        self._hint.setText(advice_line[:400] + ("…" if len(advice_line) > 400 else ""))

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
        self._abort_icon_request()
        event.ignore()
        self.hide()
        self.hide_to_tray.emit()

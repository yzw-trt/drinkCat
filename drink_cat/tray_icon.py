"""托盘图标：按今日饮水进度绘制水杯液面，达标时高亮庆祝样式。"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


def _ratio(current_ml: int, goal_ml: int) -> float:
    if goal_ml <= 0:
        return 0.0
    return max(0.0, min(1.0, current_ml / goal_ml))


def _draw_cup(size: int, ratio: float, complete: bool) -> QPixmap:
    dpr = 2  # 小图标在高分屏更清晰
    s = size * dpr
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(dpr, dpr)

    pad = max(2.0, size * 0.12)
    bw = max(1.0, size * 0.06)
    inner = QRectF(pad, pad + size * 0.08, size - 2 * pad, size - 2 * pad - size * 0.06)

    cup = QPainterPath()
    cup.addRoundedRect(inner, size * 0.12, size * 0.12)

    # 液面（自下而上）
    fill_h = inner.height() * ratio
    if fill_h > 0:
        fill_top = inner.bottom() - fill_h
        fill_rect = QRectF(inner.left(), fill_top, inner.width(), fill_h)
        clip = QPainterPath()
        clip.addRoundedRect(inner, size * 0.12, size * 0.12)
        clip_rect = fill_rect.intersected(inner)
        p.setClipPath(clip)
        g = QLinearGradient(QPointF(inner.left(), fill_top), QPointF(inner.left(), inner.bottom()))
        if complete:
            g.setColorAt(0.0, QColor(110, 220, 160))
            g.setColorAt(0.55, QColor(50, 180, 120))
            g.setColorAt(1.0, QColor(30, 140, 95))
        else:
            g.setColorAt(0.0, QColor(150, 220, 255))
            g.setColorAt(0.5, QColor(70, 170, 240))
            g.setColorAt(1.0, QColor(35, 120, 210))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRect(clip_rect)
        p.setClipping(False)

    # 杯身外框
    line = QColor(55, 70, 95) if not complete else QColor(35, 110, 75)
    p.setPen(QPen(line, bw))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(cup)

    # 达标：白色对勾
    if complete:
        pw = max(1.2, bw * 1.25)
        p.setPen(
            QPen(
                QColor(255, 255, 255),
                pw,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        x0 = inner.left() + inner.width() * 0.22
        y0 = inner.center().y() + inner.height() * 0.06
        xm = inner.center().x() - inner.width() * 0.02
        ym = inner.bottom() - inner.height() * 0.30
        x1 = inner.right() - inner.width() * 0.20
        y1 = inner.top() + inner.height() * 0.32
        p.drawLine(QPointF(x0, y0), QPointF(xm, ym))
        p.drawLine(QPointF(xm, ym), QPointF(x1, y1))

    p.end()
    pm.setDevicePixelRatio(float(dpr))
    return pm


def build_tray_icon(current_ml: int, goal_ml: int) -> QIcon:
    r = _ratio(current_ml, goal_ml)
    complete = goal_ml > 0 and current_ml >= goal_ml
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(_draw_cup(sz, r, complete))
    return icon

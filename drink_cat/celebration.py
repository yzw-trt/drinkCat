"""达成今日饮水目标时的正向反馈（托盘 + 对话框）。"""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QSystemTrayIcon


_BUNDLES = [
    (
        "今天也超棒的！",
        "今日喝水目标达成啦！",
        (
            "你刚刚完成了一件看起来很小、但对身体很重要的事。\n"
            "水分到位的时候，整个人都会更清醒、更舒服一点。\n\n"
            "认真照顾自己的你，值得被好好夸一句——真行！"
        ),
    ),
    (
        "水分满格啦",
        "耶！今天的喝水 KPI 被你拿下了",
        (
            "每一口水都在帮身体运转得更顺畅。\n"
            "这份坚持超有力量，明天也一起轻松喝够吧～"
        ),
    ),
    (
        "DrinkCat 为你鼓掌",
        "今日饮水目标已达成",
        (
            "谢谢你愿意倾听身体发出的「口渴信号」。\n"
            "好好喝水的人，运气和状态都不会太差。\n\n"
            "去伸个懒腰、深呼吸一下，奖励自己十秒钟的发呆吧。"
        ),
    ),
    (
        "小小的胜利",
        "喝水任务：今日份 ✓",
        (
            "把目标拆成一次次小口，你就已经赢了。\n"
            "这种温柔又坚定的自律，特别好看。"
        ),
    ),
]


def show_goal_celebration(tray: QSystemTrayIcon | None, parent=None) -> None:
    title, headline, body = random.choice(_BUNDLES)
    if tray is not None:
        tray.showMessage(
            title,
            "给认真照顾自己的你点个赞，今日饮水目标已满格～",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )
    box = QMessageBox(parent)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(f"<p style='font-size:13pt; margin-bottom:8px;'><b>{headline}</b></p>")
    box.setInformativeText(body)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setDefaultButton(QMessageBox.StandardButton.Ok)
    box.setStyleSheet(
        "QMessageBox { background-color: #f8fafc; } "
        "QLabel { color: #1a2230; min-width: 320px; } "
        "QPushButton { min-width: 88px; padding: 8px 16px; }"
    )
    box.exec()

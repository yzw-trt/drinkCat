"""DrinkCat 统一界面风格（浅色、高对比，与浮窗配色一致）。"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

# 与浮窗深蓝灰 + 亮蓝强调色统一
PRIMARY = "#2f6fad"
PRIMARY_HOVER = "#3d84c9"
PRIMARY_PRESSED = "#265a8c"
BG_WINDOW = "#e8ecf3"
BG_SURFACE = "#ffffff"
TEXT = "#1a2230"
TEXT_MUTED = "#5a6578"
BORDER = "#c5cedd"
INPUT_BG = "#f7f9fc"

APP_STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 10pt;
}}
QDialog, QMessageBox {{
    background-color: {BG_SURFACE};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QMenu {{
    background-color: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 28px 8px 16px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: #dbe8f5;
    color: {TEXT};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}
QPushButton {{
    background-color: {PRIMARY};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    min-height: 20px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background-color: {PRIMARY_PRESSED};
}}
QPushButton:flat {{
    background: transparent;
    color: {PRIMARY};
    font-weight: 500;
}}
QPushButton:flat:hover {{
    background-color: #e8f0fa;
}}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 22px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #9eb4d0;
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    color: {TEXT};
    selection-background-color: #dbe8f5;
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
}}
QDialogButtonBox QPushButton {{
    min-width: 88px;
}}

/* 浮窗按钮样式在 floating.py 内联设置（避免 Win + 半透明窗体下全局 QSS 不绘制文字） */
#DrinkCatFloat QLabel {{
    color: #f0f4f8;
    background: transparent;
}}
"""


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

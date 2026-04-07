"""简单设置对话框。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from .store import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DrinkCat 设置")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(400)

        intro = QLabel(
            "以下为 DrinkCat 的全局设置。修改每日目标或提醒间隔为 0 表示使用联网自动建议。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("settingsIntro")
        intro.setStyleSheet("color: #5a6578; font-size: 9pt; margin-bottom: 8px;")

        self._gender = QComboBox()
        self._gender.addItems(["未指定", "男", "女"])
        gmap = {"unspecified": 0, "male": 1, "female": 2}
        self._gender.setCurrentIndex(gmap.get(settings.gender, 0))

        self._manual_goal = QSpinBox()
        self._manual_goal.setRange(0, 6000)
        self._manual_goal.setSpecialValueText("自动（联网建议）")
        self._manual_goal.setSuffix(" ml")
        if settings.manual_goal_ml:
            self._manual_goal.setValue(settings.manual_goal_ml)
        else:
            self._manual_goal.setValue(0)

        self._manual_interval = QSpinBox()
        self._manual_interval.setRange(0, 240)
        self._manual_interval.setSpecialValueText("自动")
        self._manual_interval.setSuffix(" 分钟")
        if settings.manual_interval_min:
            self._manual_interval.setValue(settings.manual_interval_min)
        else:
            self._manual_interval.setValue(0)

        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.35, 1.0)
        self._opacity.setSingleStep(0.05)
        self._opacity.setValue(settings.float_opacity)

        form = QFormLayout()
        form.addRow("性别（影响基础建议）", self._gender)
        form.addRow("每日目标", self._manual_goal)
        form.addRow("提醒间隔", self._manual_interval)
        form.addRow("浮窗不透明度", self._opacity)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 18, 20, 18)
        root.addWidget(intro)
        root.addLayout(form)
        root.addWidget(buttons)


def apply_from_dialog(old: Settings, dlg: SettingsDialog) -> Settings | None:
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    idx = dlg._gender.currentIndex()
    gender = ("unspecified", "male", "female")[idx]
    mg = dlg._manual_goal.value()
    mi = dlg._manual_interval.value()
    return Settings(
        gender=gender,
        manual_goal_ml=mg if mg > 0 else None,
        manual_interval_min=mi if mi > 0 else None,
        float_opacity=float(dlg._opacity.value()),
        window_x=old.window_x,
        window_y=old.window_y,
        float_visible=old.float_visible,
    )

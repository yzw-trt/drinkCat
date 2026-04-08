"""应用入口：托盘、提醒、状态刷新。"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from functools import partial

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .advice import advice_for_today_cached
from .celebration import show_goal_celebration
from .floating import FloatingPanel
from .settings_dialog import SettingsDialog, apply_from_dialog
from .store import State, load_state, save_state
from .theme import apply_app_theme
from .tray_icon import build_tray_icon
from .win_tray import try_promote_tray_icon

logger = logging.getLogger(__name__)


class DrinkCatApp:
    def __init__(self) -> None:
        self._state: State = load_state()
        # 每次启动默认显示浮窗（不改动上次退出前隐藏时的配置文件，仅在内存中展示）
        self._state.settings.float_visible = True
        self._session_start = datetime.now()
        self._last_reminder_at: datetime | None = None
        self._advice_goal = 2300
        self._advice_interval = 90
        self._advice_detail = ""

        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("DrinkCat")
        apply_app_theme(self._app)

        self._float = FloatingPanel()
        self._float.add_water.connect(self._on_add_water)
        self._float.open_settings.connect(self._open_settings)
        self._float.hide_to_tray.connect(self._hide_float)

        self._tray = QSystemTrayIcon(self._app)

        menu = self._build_tray_menu()
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(15_000)

        self._advice_refresh_timer = QTimer()
        # 每小时重新拉取建议与天气（优先百度页），更新文案与天气图标
        self._advice_refresh_timer.setInterval(60 * 60 * 1000)
        self._advice_refresh_timer.timeout.connect(self._periodic_refresh_advice)
        self._advice_refresh_timer.start()

        # 每次启动重新拉取天气与建议，不用昨日同日的磁盘缓存
        self._state.cached_advice_day = ""
        self._refresh_advice()
        self._restore_float_geometry()
        self._apply_float_visibility()
        self._refresh_ui()
        # 必须在 setIcon 之后再 show，否则会报 QSystemTrayIcon::setVisible: No Icon set
        self._tray.show()
        # Windows：系统注册托盘后才会写入 NotifyIconSettings，延迟尝试「始终显示在任务栏」
        QTimer.singleShot(2500, try_promote_tray_icon)
        QTimer.singleShot(12000, try_promote_tray_icon)
        # 启动后再次置顶，避免被其它窗口挡住或任务栏后未显示
        QTimer.singleShot(0, self._bring_float_to_front)
        QTimer.singleShot(200, self._bring_float_to_front)

    def _build_tray_menu(self) -> QMenu:
        m = QMenu()
        act_show = QAction("显示浮窗", self._app)
        act_show.triggered.connect(self._show_float)
        m.addAction(act_show)
        act_hide = QAction("隐藏浮窗", self._app)
        act_hide.triggered.connect(self._hide_float)
        m.addAction(act_hide)
        m.addSeparator()
        act_refresh = QAction("刷新今日建议", self._app)
        act_refresh.triggered.connect(self._force_refresh_advice)
        m.addAction(act_refresh)
        act_settings = QAction("设置…", self._app)
        act_settings.triggered.connect(self._open_settings)
        m.addAction(act_settings)
        m.addSeparator()
        act_quit = QAction("退出", self._app)
        act_quit.triggered.connect(self._quit)
        m.addAction(act_quit)
        return m

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_float()

    def _toggle_float(self) -> None:
        if self._float.isVisible():
            self._hide_float()
        else:
            self._show_float()

    def _show_float(self) -> None:
        self._state.settings.float_visible = True
        self._float.show()
        self._persist()

    def _hide_float(self) -> None:
        self._state.settings.float_visible = False
        self._float.hide()
        self._persist()

    def _apply_float_visibility(self) -> None:
        # 每次打开程序默认显示浮窗（与设置里保存的 float_visible 无关）
        self._state.settings.float_visible = True
        self._float.show()
        self._bring_float_to_front()

    def _bring_float_to_front(self) -> None:
        if not self._float.isVisible():
            return
        self._float.show()
        self._float.raise_()
        self._float.activateWindow()

    def _restore_float_geometry(self) -> None:
        x, y = self._state.settings.window_x, self._state.settings.window_y
        if x is not None and y is not None:
            self._float.move(x, y)
        else:
            screen = self._app.primaryScreen()
            if screen:
                g = screen.availableGeometry()
                self._float.move(g.right() - self._float.width() - 24, g.bottom() - 200)
        self._float.set_opacity(self._state.settings.float_opacity)

    def _persist_geometry(self) -> None:
        p = self._float.pos()
        self._state.settings.window_x = p.x()
        self._state.settings.window_y = p.y()

    def _effective_goal_interval(self) -> tuple[int, int]:
        g = self._state.settings.manual_goal_ml or self._advice_goal
        i = self._state.settings.manual_interval_min or self._advice_interval
        return g, i

    def _refresh_advice(self) -> None:
        wa, cache, day = advice_for_today_cached(
            self._state.settings.gender,
            self._state.cached_advice,
            self._state.cached_advice_day,
        )
        self._state.cached_advice = cache
        self._state.cached_advice_day = day
        self._advice_goal = wa.daily_goal_ml
        self._advice_interval = wa.reminder_interval_minutes
        self._advice_detail = wa.detail
        save_state(self._state)

    def _periodic_refresh_advice(self) -> None:
        self._state.cached_advice_day = ""
        self._refresh_advice()
        self._refresh_ui()

    def _force_refresh_advice(self) -> None:
        self._periodic_refresh_advice()
        self._tray.showMessage("DrinkCat", "已重新获取今日饮水建议。", QSystemTrayIcon.MessageIcon.Information, 2500)

    def _last_drink_dt(self) -> datetime | None:
        raw = self._state.last_drink_iso
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def _reference_last_drink(self) -> datetime:
        """用于计算「多久没喝」：有记录用记录，否则用本次启动时间。"""
        d = self._last_drink_dt()
        if d:
            return d
        return self._session_start

    def _maybe_remind(self) -> None:
        goal, interval = self._effective_goal_interval()
        if goal > 0 and self._state.today_total_ml >= goal:
            self._last_reminder_at = None
            return
        ref = self._reference_last_drink()
        now = datetime.now()
        overdue = now - ref >= timedelta(minutes=interval)
        if not overdue:
            self._last_reminder_at = None
            return
        if self._last_reminder_at is None:
            self._send_reminder()
            self._last_reminder_at = now
            return
        if now - self._last_reminder_at >= timedelta(minutes=30):
            self._send_reminder()
            self._last_reminder_at = now

    def _send_reminder(self) -> None:
        _, interval = self._effective_goal_interval()
        self._tray.showMessage(
            "喝水提醒",
            f"已超过约 {interval} 分钟未记录喝水，记得补充水分。",
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )

    def _on_add_water(self, ml: int) -> None:
        self._state.add_water(ml)
        self._last_reminder_at = None
        self._persist()
        self._refresh_ui()
        self._maybe_celebrate_goal()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self._state.settings, None, on_clear_all_data=self._clear_all_user_data)
        new_s = apply_from_dialog(self._state.settings, dlg)
        if new_s is None:
            return
        self._state.settings = new_s
        self._float.set_opacity(new_s.float_opacity)
        self._persist()
        self._refresh_advice()
        self._refresh_ui()
        self._maybe_celebrate_goal()

    def _tick(self) -> None:
        self._state.touch_day()
        self._persist_geometry()
        self._maybe_remind()
        self._refresh_ui()

    def _last_drink_line(self) -> str:
        d = self._last_drink_dt()
        if not d:
            return "上次记录：今天还没有记录"
        return f"上次记录：{d.strftime('%H:%M')}"

    def _since_last_drink_line(self) -> str:
        ref = self._reference_last_drink()
        mins = max(0, int((datetime.now() - ref).total_seconds() // 60))
        if self._last_drink_dt():
            return f"距上次喝水：约 {mins} 分钟"
        return f"距上次喝水：尚无记录（自本次启动约 {mins} 分钟）"

    def _clear_all_user_data(self) -> None:
        self._state.clear_user_data()
        self._session_start = datetime.now()
        self._last_reminder_at = None
        save_state(self._state)
        self._refresh_advice()
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        goal, _ = self._effective_goal_interval()
        c = self._state.cached_advice
        self._float.update_display(
            self._state.today_total_ml,
            goal,
            self._since_last_drink_line(),
            self._last_drink_line(),
            self._advice_detail or "正在获取天气与饮水建议…",
            weather_icon_url=c.get("weather_icon_url") if isinstance(c.get("weather_icon_url"), str) else None,
        )
        self._update_tray_appearance()

    def _update_tray_appearance(self) -> None:
        goal, _ = self._effective_goal_interval()
        total = self._state.today_total_ml
        self._tray.setIcon(build_tray_icon(total, goal))
        if goal > 0:
            pct = min(100, int(100 * total / goal))
            if total >= goal:
                tip = f"DrinkCat — 今日 {total}/{goal} ml，目标已完成"
            else:
                tip = f"DrinkCat — 今日 {total}/{goal} ml（{pct}%）"
        else:
            tip = "DrinkCat — 喝水记录"
        self._tray.setToolTip(tip)

    def _maybe_celebrate_goal(self) -> None:
        goal, _ = self._effective_goal_interval()
        if goal <= 0:
            return
        self._state.touch_day()
        if self._state.today_total_ml < goal:
            return
        if self._state.celebrated_goal_day == self._state.day_key:
            return
        self._state.celebrated_goal_day = self._state.day_key
        save_state(self._state)
        QTimer.singleShot(400, partial(self._run_goal_celebration))

    def _run_goal_celebration(self) -> None:
        parent = self._float if self._float.isVisible() else None
        show_goal_celebration(self._tray, parent)

    def _persist(self) -> None:
        save_state(self._state)

    def _quit(self) -> None:
        self._persist_geometry()
        self._state.settings.float_visible = self._float.isVisible()
        save_state(self._state)
        self._app.quit()

    def run(self) -> int:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "DrinkCat", "当前环境不支持系统托盘，程序可能无法正常工作。")
        return self._app.exec()

"""本地持久化：饮水记录与设置。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "DrinkCat"
    return Path.home() / ".config" / "drink_cat"


def _data_path() -> Path:
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "data.json"


@dataclass
class Settings:
    gender: str = "unspecified"  # male / female / unspecified — 影响基础建议量
    manual_goal_ml: int | None = None  # 非空则覆盖联网目标
    manual_interval_min: int | None = None  # 非空则覆盖提醒间隔
    float_opacity: float = 0.88
    window_x: int | None = None
    window_y: int | None = None
    float_visible: bool = True


@dataclass
class State:
    settings: Settings = field(default_factory=Settings)
    # 当日累计（按本地日期）
    day_key: str = ""
    today_total_ml: int = 0
    last_drink_iso: str | None = None
    # 上次联网建议缓存
    cached_advice: dict[str, Any] = field(default_factory=dict)
    cached_advice_day: str = ""
    # 已为哪一天展示过「达成目标」庆祝（同日只触发一次）
    celebrated_goal_day: str = ""

    def touch_day(self) -> None:
        k = date.today().isoformat()
        if self.day_key != k:
            self.day_key = k
            self.today_total_ml = 0

    def add_water(self, ml: int) -> None:
        self.touch_day()
        self.today_total_ml += ml
        self.last_drink_iso = datetime.now().isoformat(timespec="seconds")


def default_state() -> State:
    s = State()
    s.touch_day()
    return s


def load_state() -> State:
    p = _data_path()
    if not p.is_file():
        return default_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()

    settings = Settings(**{k: v for k, v in raw.get("settings", {}).items() if k in Settings.__dataclass_fields__})
    st = State(
        settings=settings,
        day_key=raw.get("day_key", ""),
        today_total_ml=int(raw.get("today_total_ml", 0)),
        last_drink_iso=raw.get("last_drink_iso"),
        cached_advice=raw.get("cached_advice") or {},
        cached_advice_day=raw.get("cached_advice_day", ""),
        celebrated_goal_day=str(raw.get("celebrated_goal_day", "") or ""),
    )
    st.touch_day()
    return st


def save_state(state: State) -> None:
    p = _data_path()
    data = {
        "settings": asdict(state.settings),
        "day_key": state.day_key,
        "today_total_ml": state.today_total_ml,
        "last_drink_iso": state.last_drink_iso,
        "cached_advice": state.cached_advice,
        "cached_advice_day": state.cached_advice_day,
        "celebrated_goal_day": state.celebrated_goal_day,
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

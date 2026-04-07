"""从网络获取饮水建议：多源天气（国内网络下 Open-Meteo 常不可用，优先 wttr.in）。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

import requests

logger = logging.getLogger(__name__)

BASE_GOAL = {
    "male": 2500,
    "female": 2200,
    "unspecified": 2300,
}

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DrinkCat/1.0",
        "Accept": "application/json, text/plain, */*",
    }
)


@dataclass
class WaterAdvice:
    daily_goal_ml: int
    reminder_interval_minutes: int
    detail: str
    ok: bool


def _base_goal_ml(gender: str) -> int:
    return BASE_GOAL.get(gender, BASE_GOAL["unspecified"])


def _geo_geojs() -> tuple[float, float] | None:
    try:
        r = SESSION.get("https://get.geojs.io/v1/ip/geo.json", timeout=10)
        r.raise_for_status()
        j = r.json()
        lat, lon = j.get("latitude"), j.get("longitude")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception as e:
        logger.debug("geojs failed: %s", e)
        return None


def _geo_ipwho() -> tuple[float, float] | None:
    try:
        r = SESSION.get("https://ipwho.is/", timeout=10)
        r.raise_for_status()
        j = r.json()
        if j.get("success") is False:
            return None
        lat, lon = j.get("latitude"), j.get("longitude")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception as e:
        logger.debug("ipwho failed: %s", e)
        return None


def _geo_ip() -> tuple[float, float] | None:
    return _geo_geojs() or _geo_ipwho()


def _reference_place_pconline() -> str:
    """国内常用 IP 归属接口，返回中文省/市（比 wttr 英文地名更准确）。"""
    try:
        r = SESSION.get(
            "https://whois.pconline.com.cn/ipJson.jsp?json=true",
            timeout=10,
        )
        r.raise_for_status()
        text = None
        for enc in ("gbk", "gb18030", "utf-8-sig", "utf-8"):
            try:
                text = r.content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            return ""
        j = json.loads(text)
        pro = (j.get("pro") or "").strip()
        city = (j.get("city") or "").strip()
        if pro and city:
            return f"{pro}{city}"
        if city:
            return city
        if pro:
            return pro
        return (j.get("addr") or "").strip()
    except Exception as e:
        logger.debug("pconline ip geo failed: %s", e)
        return ""


def _reference_place_ipwho() -> str:
    """供参考地展示：市/省/国家。"""
    try:
        r = SESSION.get("https://ipwho.is/", timeout=8)
        r.raise_for_status()
        j = r.json()
        if j.get("success") is False:
            return ""
        city = (j.get("city") or "").strip()
        region = (j.get("region") or "").strip()
        country = (j.get("country") or "").strip()
        if city and region:
            return f"{region}{city}"
        if city:
            return city
        if region:
            return region
        return country
    except Exception as e:
        logger.debug("ipwho place failed: %s", e)
        return ""


def _today_max_temp_open_meteo(lat: float, lon: float) -> float | None:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&daily=temperature_2m_max"
            "&forecast_days=1"
            "&timezone=auto"
        )
        r = SESSION.get(url, timeout=10)
        r.raise_for_status()
        j = r.json()
        daily = j.get("daily") or {}
        arr = daily.get("temperature_2m_max") or []
        if not arr:
            return None
        return float(arr[0])
    except Exception as e:
        logger.info("Open-Meteo 不可用（部分网络会拦截）: %s", e)
        return None


def _en_weather_to_zh(raw: str) -> str:
    u = raw.strip().upper()
    if not u:
        return "未知"
    pairs = [
        ("THUNDER", "雷阵雨"),
        ("BLIZZARD", "暴雪"),
        ("SLEET", "雨夹雪"),
        ("DRIZZLE", "小雨"),
        ("RAIN", "雨"),
        ("SNOW", "雪"),
        ("FOG", "雾"),
        ("MIST", "薄雾"),
        ("OVERCAST", "阴"),
        ("PARTLY CLOUDY", "多云"),
        ("CLOUDY", "多云"),
        ("SUNNY", "晴"),
        ("CLEAR", "晴"),
    ]
    for en, zh in pairs:
        if en in u:
            return zh
    return "多云"


def _pick_representative_hourly(hourlies: list) -> dict:
    if not hourlies:
        return {}
    for h in hourlies:
        if str(h.get("time")) == "1200":
            return h
    return hourlies[len(hourlies) // 2]


def _wttr_area_place(j: dict) -> str:
    place_parts: list[str] = []
    na = (j.get("nearest_area") or [{}])[0]
    if isinstance(na, dict):
        for key in ("areaName", "region", "country"):
            block = na.get(key)
            if isinstance(block, list) and block:
                v = block[0]
                if isinstance(v, dict) and v.get("value"):
                    place_parts.append(str(v["value"]).strip())
    return "，".join(place_parts) if place_parts else ""


def _wttr_parse() -> tuple[float | None, str, str | None]:
    """返回：(最高温, 参考地, 天气简况中文或 None)。"""
    try:
        r = SESSION.get("https://wttr.in/?format=j1", timeout=14)
        r.raise_for_status()
        j = r.json()
        weather = j.get("weather") or []
        if not weather:
            return None, "", None
        day = weather[0]
        maxc = float(day["maxtempC"])
        place = _wttr_area_place(j)
        hourly = day.get("hourly") or []
        h = _pick_representative_hourly(hourly)
        desc_block = h.get("weatherDesc") if isinstance(h, dict) else None
        en = ""
        if isinstance(desc_block, list) and desc_block:
            v0 = desc_block[0]
            if isinstance(v0, dict) and v0.get("value"):
                en = str(v0["value"])
        weather_zh = _en_weather_to_zh(en) if en else None
        return maxc, place, weather_zh
    except Exception as e:
        logger.info("wttr.in 天气获取失败: %s", e)
        return None, "", None


def _format_weather_detail(
    temp_c: float | None,
    weather_zh: str | None,
    place: str,
) -> str:
    ref = (place or "").strip() or "未知"
    if temp_c is None:
        return "未能获取天气与气温，使用基础饮水建议。"
    t_int = int(round(temp_c))
    if weather_zh:
        return f"今日天气{weather_zh}，最高温度{t_int}℃，参考地：{ref}。"
    return f"今日最高温度{t_int}℃，参考地：{ref}。"


def _adjust_goal_ml(base_ml: int, temp_max_c: float | None) -> int:
    if temp_max_c is None:
        return base_ml
    extra = 0.0
    if temp_max_c > 28:
        extra = min(0.20, (temp_max_c - 28) * 0.015)
    elif temp_max_c < 10:
        extra = -0.05
    adjusted = int(round(base_ml * (1.0 + extra)))
    return max(1200, min(4000, adjusted))


def _interval_minutes(goal_ml: int) -> int:
    cups = max(1, round(goal_ml / 250))
    span = 16 * 60
    return max(45, min(120, span // cups))


def fetch_advice(gender: str) -> WaterAdvice:
    base = _base_goal_ml(gender)
    temp: float | None = None
    weather_zh: str | None = None

    wttr_temp, wttr_place, wttr_wx = _wttr_parse()
    # 参考地：中文 IP 库 > ipwho > wttr 英文地名（避免 Yenchuang 这类音译）
    place = (
        _reference_place_pconline()
        or _reference_place_ipwho()
        or (wttr_place or "").strip()
    )

    if wttr_temp is not None:
        temp = wttr_temp
        weather_zh = wttr_wx

    if temp is None:
        geo = _geo_ip()
        if geo:
            temp = _today_max_temp_open_meteo(geo[0], geo[1])
        weather_zh = None
        if temp is not None and not place:
            place = "IP 定位附近"

    detail = _format_weather_detail(temp, weather_zh, place)
    goal = _adjust_goal_ml(base, temp)
    interval = _interval_minutes(goal)
    return WaterAdvice(
        daily_goal_ml=goal,
        reminder_interval_minutes=interval,
        detail=detail,
        ok=temp is not None,
    )


def advice_for_today_cached(
    gender: str,
    cached: dict,
    cached_day: str,
) -> tuple[WaterAdvice, dict, str]:
    today = date.today().isoformat()
    if cached_day == today and cached.get("daily_goal_ml"):
        wa = WaterAdvice(
            daily_goal_ml=int(cached["daily_goal_ml"]),
            reminder_interval_minutes=int(cached.get("reminder_interval_minutes", 90)),
            detail=str(cached.get("detail", "")),
            ok=bool(cached.get("ok", True)),
        )
        return wa, cached, cached_day
    wa = fetch_advice(gender)
    new_cache = {
        "daily_goal_ml": wa.daily_goal_ml,
        "reminder_interval_minutes": wa.reminder_interval_minutes,
        "detail": wa.detail,
        "ok": wa.ok,
    }
    return wa, new_cache, today

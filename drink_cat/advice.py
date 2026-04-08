"""从网络获取饮水建议：优先百度天气 PC 页内嵌数据，失败时回退 wttr.in / Open-Meteo。"""

from __future__ import annotations

import base64
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

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

# 与 wttr.in 相同的 WorldWeatherOnline 图标 CDN，按百度页 weatherIcon / 天气关键字选用
_WWO_ICON_BASE = "https://cdn.worldweatheronline.com/images/wsymbols01_png_64/"
_BAIDU_ICON_KEY_TO_PNG: dict[str, str] = {
    "qingtian": "wsymbol_0001_sunny.png",
    "qing": "wsymbol_0001_sunny.png",
    "duoyun": "wsymbol_0003_white_cloud.png",
    "yin": "wsymbol_0004_black_low_cloud.png",
    "wu": "wsymbol_0006_mist.png",
    "mai": "wsymbol_0006_mist.png",
    "xiaoyu": "wsymbol_0017_cloudy_with_light_rain.png",
    "zhongyu": "wsymbol_0018_cloudy_with_heavy_rain.png",
    "dayu": "wsymbol_0018_cloudy_with_heavy_rain.png",
    "leizhenyu": "wsymbol_0024_thunderstorms.png",
    "xiaoxue": "wsymbol_0019_cloudy_with_light_snow.png",
    "zhongxue": "wsymbol_0020_cloudy_with_heavy_snow.png",
    "baoxue": "wsymbol_0020_cloudy_with_heavy_snow.png",
    "yujiaxue": "wsymbol_0017_cloudy_with_light_rain.png",
    "shachen": "wsymbol_0004_black_low_cloud.png",
    "longjuanfeng": "wsymbol_0024_thunderstorms.png",
}
_BAIDU_WEATHER_PC = "https://weathernew.pae.baidu.com/weathernew/pc"

# 缓存百度天气页引用的 biz 打包 JS（内含与官网一致的 gray* 天气 SVG）
_baidu_biz_cache: tuple[str, str] | None = None  # (script_path, js_text)


def _extract_window_json(html: str, var_name: str) -> dict[str, Any] | None:
    """解析页面内嵌的 `window.tplData` / `window.modifyData` JSON。"""
    needle = f"window.{var_name} = "
    idx = html.find(needle)
    if idx < 0:
        return None
    start = idx + len(needle)
    while start < len(html) and html[start] in " \n\t\r":
        start += 1
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, start)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _weather_query_from_place(place: str) -> str:
    """百度 query：省/市中文 +「天气」，与搜索「铜陵天气」一致。"""
    p = (place or "").strip()
    if not p:
        return "天气"
    if not p.endswith("天气"):
        return f"{p}天气"
    return p


def _biz_script_path_from_pc_html(html: str) -> str | None:
    m = re.search(r'src="(/static/weathernew/bundle/biz_[a-f0-9]+\.js)"', html)
    return m.group(1) if m else None


def _get_baidu_biz_js(html: str) -> str | None:
    global _baidu_biz_cache
    path = _biz_script_path_from_pc_html(html)
    if not path:
        return None
    if _baidu_biz_cache and _baidu_biz_cache[0] == path:
        return _baidu_biz_cache[1]
    try:
        r = SESSION.get(
            f"https://weathernew.pae.baidu.com{path}",
            timeout=20,
            headers={"Referer": "https://www.baidu.com/"},
        )
        r.raise_for_status()
        _baidu_biz_cache = (path, r.text)
        return r.text
    except Exception as e:
        logger.debug("百度 biz 打包 JS 拉取失败: %s", e)
        return None


def _extract_gray_symbol_children(js: str, icon_key: str) -> str | None:
    """从 biz 包中取出 `c(\"symbol\",{attrs:{id:\"gray…\"` 的子节点数组源码片段。"""
    k = icon_key.strip().lower()
    needle = f'attrs:{{id:"gray{k}",viewBox:"0 0 48 48"}}}},['
    idx = js.find(needle)
    if idx < 0:
        return None
    start = idx + len(needle) - 1
    if start >= len(js) or js[start] != "[":
        return None
    depth = 0
    for i in range(start, len(js)):
        if js[i] == "[":
            depth += 1
        elif js[i] == "]":
            depth -= 1
            if depth == 0:
                return js[start + 1 : i]
    return None


def _parse_js_string_at_open_quote(s: str, open_quote_idx: int) -> tuple[str, int] | None:
    """从开引号起解析 JS 字符串，返回 (内容, 闭合引号下一索引)。"""
    if open_quote_idx >= len(s) or s[open_quote_idx] != '"':
        return None
    i = open_quote_idx + 1
    parts: list[str] = []
    while i < len(s):
        c = s[i]
        if c == "\\":
            if i + 1 < len(s):
                parts.append(s[i : i + 2])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            raw = "".join(parts)
            raw = raw.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
            raw = re.sub(r"\s+", " ", raw).strip()
            return raw, i + 1
        parts.append(c)
        i += 1
    return None


def _sanitize_svg_path_d(d: str) -> str:
    """Qt SVG 对 path 很严格：字面换行、多空格会导致 Invalid path data / truncated。"""
    s = d.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_paths_from_gray_symbol_body(body: str) -> list[tuple[str, str]]:
    """解析 gray 图标里的 c(\"path\"…)，得到 (fill, d)。"""
    out: list[tuple[str, str]] = []
    i = 0
    # 不能用 find('d:"')：会命中 id:"…" 里的子串 d:"
    _d_attr = re.compile(r'([\,{])d\s*:\s*"')
    while True:
        j = body.find('c("path"', i)
        if j < 0:
            break
        next_p = body.find('c("path"', j + 8)
        seg = body[j : next_p if next_p >= 0 else len(body)]
        m = _d_attr.search(seg)
        if not m:
            i = j + 8
            continue
        open_q = m.end() - 1
        if open_q >= len(seg) or seg[open_q] != '"':
            i = j + 8
            continue
        parsed = _parse_js_string_at_open_quote(seg, open_q)
        if not parsed:
            i = j + 8
            continue
        d_val, _ = parsed
        fm = re.search(r'fill:"([^"]*)"', seg[: m.start()])
        fill = fm.group(1) if fm else "#FFFFFF"
        out.append((fill, d_val))
        i = j + 8
    return out


def _gray_paths_to_svg_base64_data_url(paths: list[tuple[str, str]]) -> str | None:
    """用 ElementTree 生成合法 XML，base64 data URL 避免百分号编码破坏 path。"""
    if not paths:
        return None
    svg = ET.Element("svg")
    svg.set("xmlns", "http://www.w3.org/2000/svg")
    svg.set("viewBox", "0 0 48 48")
    for fill, d in paths:
        d2 = _sanitize_svg_path_d(d)
        if not d2:
            continue
        pe = ET.SubElement(svg, "path")
        pe.set("fill", (fill or "#FFFFFF").strip() or "#FFFFFF")
        pe.set("d", d2)
    if not len(svg):
        return None
    xml_bytes = ET.tostring(svg, encoding="utf-8", xml_declaration=False)
    b64 = base64.standard_b64encode(xml_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _baidu_gray_icon_data_url(html: str, icon_key: str | None) -> str | None:
    """
    使用百度 PC 天气页同款内嵌 SVG（biz 包中 id=\"gray{icon_key}\"）。
    返回 data:image/svg+xml;base64,... 供本地 QSvgRenderer 栅格化。
    """
    if not icon_key:
        return None
    js = _get_baidu_biz_js(html)
    if not js:
        return None
    body = _extract_gray_symbol_children(js, icon_key)
    if not body:
        return None
    paths = _extract_paths_from_gray_symbol_body(body)
    return _gray_paths_to_svg_base64_data_url(paths)


def _baidu_today_weather_icon_key(modify: dict[str, Any] | None) -> str | None:
    if not modify:
        return None
    for row in modify.get("weather15DayData") or []:
        if not isinstance(row, dict):
            continue
        if row.get("formatWeek") == "今天":
            k = (row.get("weatherIcon") or "").strip()
            return k or None
    k = (modify.get("weatherIcon") or "").strip()
    return k or None


def _baidu_weather_icon_url_wwo_fallback(icon_key: str | None, weather_text: str) -> str | None:
    """百度未提供独立图标 URL；此为 WorldWeatherOnline PNG 近似替代。"""
    if icon_key:
        png = _BAIDU_ICON_KEY_TO_PNG.get(icon_key.lower().strip())
        if png:
            return f"{_WWO_ICON_BASE}{png}"
    t = (weather_text or "").strip()
    for frag, png in (
        ("雷", "wsymbol_0024_thunderstorms.png"),
        ("暴雨", "wsymbol_0018_cloudy_with_heavy_rain.png"),
        ("大雨", "wsymbol_0018_cloudy_with_heavy_rain.png"),
        ("中雨", "wsymbol_0018_cloudy_with_heavy_rain.png"),
        ("小雨", "wsymbol_0017_cloudy_with_light_rain.png"),
        ("雨", "wsymbol_0017_cloudy_with_light_rain.png"),
        ("雪", "wsymbol_0020_cloudy_with_heavy_snow.png"),
        ("雾", "wsymbol_0006_mist.png"),
        ("霾", "wsymbol_0006_mist.png"),
        ("晴", "wsymbol_0001_sunny.png"),
        ("多云", "wsymbol_0003_white_cloud.png"),
        ("阴", "wsymbol_0004_black_low_cloud.png"),
    ):
        if frag in t:
            return f"{_WWO_ICON_BASE}{png}"
    return None


def _parse_baidu_pc_page(html: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    tpl = _extract_window_json(html, "tplData")
    modify = _extract_window_json(html, "modifyData")
    if tpl is None and modify is None:
        return None
    return (tpl or {}), modify


def _fetch_baidu_weather_pc(query_text: str) -> tuple[
    float | None,
    float | None,
    str,
    str | None,
    str | None,
    float | None,
] | None:
    """
    请求百度天气 PC 页，解析横幅同款字段。
    返回：(夜间温, 白天温, 展示文案, 天气简况, 图标 URL, 用于饮水目标参考的最高温)；失败返回 None。
    """
    params = urlencode(
        {
            "query": query_text,
            "srcid": "4982",
            "forecast": "long_day_forecast",
        },
        encoding="utf-8",
    )
    url = f"{_BAIDU_WEATHER_PC}?{params}"
    try:
        r = SESSION.get(
            url,
            timeout=14,
            headers={"Referer": "https://www.baidu.com/"},
        )
        r.raise_for_status()
        text = r.text
    except Exception as e:
        logger.info("百度天气页获取失败: %s", e)
        return None

    parsed = _parse_baidu_pc_page(text)
    if not parsed:
        logger.info("百度天气页未找到 tplData/modifyData")
        return None
    tpl, modify = parsed
    w = (modify.get("weather") if isinstance(modify, dict) else None) or tpl.get("weather") or {}
    pos = (modify.get("position") if isinstance(modify, dict) else None) or tpl.get("position") or {}
    if not isinstance(w, dict):
        return None
    tday = w.get("temperature_day")
    tnight = w.get("temperature_night")
    if tday is None and tnight is None:
        return None
    try:
        hi = float(tday) if tday not in (None, "") else None
        lo = float(tnight) if tnight not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if hi is not None and lo is not None and lo > hi:
        lo, hi = hi, lo

    city = (pos.get("city") if isinstance(pos, dict) else None) or ""
    city = str(city).strip()
    wx = (w.get("weather_day") or w.get("weather_night") or "").strip()
    if not wx:
        wx = (w.get("weather") or "").strip()
    wdir_d = (w.get("wind_direction_day") or "").strip()
    wp_d = (w.get("wind_power_day") or "").strip()
    wdir_n = (w.get("wind_direction_night") or "").strip()
    wp_n = (w.get("wind_power_night") or "").strip()
    if wdir_d and wp_d:
        wind = f"{wdir_d}{wp_d}"
    elif wdir_n and wp_n:
        wind = f"{wdir_n}{wp_n}"
    else:
        wind = ((w.get("wind_direction") or "") + (w.get("wind_power") or "")).strip()

    lo_s = str(int(round(lo))) if lo is not None else "?"
    hi_s = str(int(round(hi))) if hi is not None else "?"
    parts = [f"{city} " if city else "", "今天：", wx, f"  {lo_s}°~{hi_s}°C"]
    line = "".join(parts)
    if wind:
        line = f"{line}  {wind}"

    icon_key = _baidu_today_weather_icon_key(modify)
    icon_url = _baidu_gray_icon_data_url(text, icon_key) or _baidu_weather_icon_url_wwo_fallback(
        icon_key, wx
    )

    goal_max: float | None = hi
    rf = w.get("real_feel_temperature")
    if rf not in (None, ""):
        try:
            rfv = float(rf)
            if goal_max is not None:
                goal_max = max(goal_max, rfv)
            else:
                goal_max = rfv
        except (TypeError, ValueError):
            pass

    return lo, hi, line, wx or None, icon_url, goal_max


@dataclass
class WaterAdvice:
    daily_goal_ml: int
    reminder_interval_minutes: int
    detail: str
    ok: bool
    # 浮窗右侧：天气图标 URL（百度 biz 内嵌 SVG 的 data: 地址、WWO 回退或 wttr）
    weather_icon_url: str | None = None


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


def _today_apparent_minmax_open_meteo(lat: float, lon: float) -> tuple[float | None, float | None]:
    """Open-Meteo 当日体感温度最低、最高。"""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&daily=apparent_temperature_max,apparent_temperature_min"
            "&forecast_days=1"
            "&timezone=auto"
        )
        r = SESSION.get(url, timeout=10)
        r.raise_for_status()
        j = r.json()
        daily = j.get("daily") or {}
        arr_max = daily.get("apparent_temperature_max") or []
        arr_min = daily.get("apparent_temperature_min") or []
        if not arr_max:
            return None, None
        tmax = float(arr_max[0])
        tmin = float(arr_min[0]) if arr_min else None
        return tmin, tmax
    except Exception as e:
        logger.info("Open-Meteo 不可用（部分网络会拦截）: %s", e)
        return None, None


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


def _wttr_payload(raw: dict) -> dict:
    """兼容 wttr 顶层或嵌套在 data 下的 JSON。"""
    d = raw.get("data")
    if isinstance(d, dict) and d.get("weather"):
        return d
    return raw


def _parse_wttr_float(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _wttr_feels_minmax_from_day(day: dict) -> tuple[float | None, float | None]:
    """当日逐小时 FeelsLikeC 的最小、最大；若无则退回 mintempC/maxtempC。"""
    hourlies = day.get("hourly") or []
    feels: list[float] = []
    for h in hourlies:
        if not isinstance(h, dict):
            continue
        for key in ("FeelsLikeC", "feelslikeC", "feelsLikeC"):
            v = _parse_wttr_float(h.get(key))
            if v is not None:
                feels.append(v)
                break
    if feels:
        return min(feels), max(feels)
    mn = _parse_wttr_float(day.get("mintempC"))
    mx = _parse_wttr_float(day.get("maxtempC"))
    if mn is not None and mx is not None:
        return mn, mx
    return None, None


def _wttr_weather_icon_url_from_block(block: dict) -> str | None:
    urls = block.get("weatherIconUrl")
    if isinstance(urls, list) and urls:
        v0 = urls[0]
        if isinstance(v0, dict) and v0.get("value"):
            u = str(v0["value"]).strip()
            return u or None
    return None


def _wttr_current_condition_icon_url(raw: dict, j: dict) -> str | None:
    """实时天气图标：current_condition[0].weatherIconUrl（兼容顶层 / data 嵌套）。"""
    candidates: list[object] = [
        j.get("current_condition"),
        raw.get("current_condition"),
    ]
    d = raw.get("data")
    if isinstance(d, dict):
        candidates.append(d.get("current_condition"))
    for cc in candidates:
        if isinstance(cc, list) and cc and isinstance(cc[0], dict):
            u = _wttr_weather_icon_url_from_block(cc[0])
            if u:
                return u
    return None


def _wttr_parse() -> tuple[float | None, float | None, str, str | None, str | None]:
    """返回：(体感最低℃, 体感最高℃, 参考地, 天气简况中文或 None, current_condition 天气图标 URL 或 None)。"""
    try:
        r = SESSION.get("https://wttr.in/?format=j1", timeout=14)
        r.raise_for_status()
        raw = r.json()
        j = _wttr_payload(raw)
        weather = j.get("weather") or []
        if not weather:
            return None, None, "", None, None
        day = weather[0]
        minc, maxc = _wttr_feels_minmax_from_day(day)
        place = _wttr_area_place(j) or _wttr_area_place(raw)
        hourly = day.get("hourly") or []
        h = _pick_representative_hourly(hourly)
        icon_url = _wttr_current_condition_icon_url(raw, j)
        desc_block = h.get("weatherDesc") if isinstance(h, dict) else None
        en = ""
        if isinstance(desc_block, list) and desc_block:
            v0 = desc_block[0]
            if isinstance(v0, dict) and v0.get("value"):
                en = str(v0["value"])
        weather_zh = _en_weather_to_zh(en) if en else None
        return minc, maxc, place, weather_zh, icon_url
    except Exception as e:
        logger.info("wttr.in 天气获取失败: %s", e)
        return None, None, "", None, None


def _format_weather_detail(
    feels_min_c: float | None,
    feels_max_c: float | None,
    weather_zh: str | None,
    place: str,
) -> str:
    ref = (place or "").strip() or "未知"
    if feels_max_c is None and feels_min_c is None:
        return "未能获取天气与体感温度，使用基础饮水建议。"
    if feels_min_c is not None and feels_max_c is not None:
        lo, hi = int(round(feels_min_c)), int(round(feels_max_c))
        if lo > hi:
            lo, hi = hi, lo
        temp_part = f"体感温度{lo}-{hi}℃"
    elif feels_max_c is not None:
        temp_part = f"体感温度{int(round(feels_max_c))}℃"
    else:
        assert feels_min_c is not None
        temp_part = f"体感温度{int(round(feels_min_c))}℃"
    if weather_zh:
        return f"今日天气{weather_zh}，{temp_part}，所在地：{ref}。"
    return f"今日{temp_part}，所在地：{ref}。"


def _adjust_goal_ml(base_ml: int, feels_max_c: float | None) -> int:
    """按当日体感最高温微调建议饮水量。"""
    if feels_max_c is None:
        return base_ml
    extra = 0.0
    if feels_max_c > 28:
        extra = min(0.20, (feels_max_c - 28) * 0.015)
    elif feels_max_c < 10:
        extra = -0.05
    adjusted = int(round(base_ml * (1.0 + extra)))
    return max(1200, min(4000, adjusted))


def _interval_minutes(goal_ml: int) -> int:
    cups = max(1, round(goal_ml / 250))
    span = 16 * 60
    return max(45, min(120, span // cups))


def fetch_advice(gender: str) -> WaterAdvice:
    base = _base_goal_ml(gender)
    tmin: float | None = None
    tmax: float | None = None
    weather_zh: str | None = None

    # 所在地：中文 IP 库 > ipwho（用于百度 query=…天气）
    place = _reference_place_pconline() or _reference_place_ipwho() or ""

    weather_icon_url: str | None = None
    detail: str
    goal_adj_temp: float | None = None

    baidu = _fetch_baidu_weather_pc(_weather_query_from_place(place))
    if baidu is not None:
        lo, hi, line, wx_zh, icon_u, goal_max = baidu
        tmin, tmax = lo, hi
        weather_zh = wx_zh
        weather_icon_url = icon_u
        goal_adj_temp = goal_max
        detail = f"{line} 请适量补水。"

    if baidu is None:
        wttr_min, wttr_max, wttr_place, wttr_wx, wttr_icon = _wttr_parse()
        if not place:
            place = (wttr_place or "").strip()
        if wttr_max is not None:
            tmin, tmax = wttr_min, wttr_max
            weather_zh = wttr_wx
            weather_icon_url = wttr_icon
            goal_adj_temp = tmax

        if tmax is None:
            geo = _geo_ip()
            if geo:
                om_min, om_max = _today_apparent_minmax_open_meteo(geo[0], geo[1])
                tmin, tmax = om_min, om_max
            weather_zh = None
            weather_icon_url = None
            goal_adj_temp = tmax
            if tmax is not None and not place:
                place = "IP 定位附近"

        detail = _format_weather_detail(tmin, tmax, weather_zh, place)

    goal = _adjust_goal_ml(base, goal_adj_temp if goal_adj_temp is not None else tmax)
    interval = _interval_minutes(goal)
    return WaterAdvice(
        daily_goal_ml=goal,
        reminder_interval_minutes=interval,
        detail=detail,
        ok=(tmax is not None or tmin is not None),
        weather_icon_url=weather_icon_url,
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
            weather_icon_url=cached.get("weather_icon_url") or None,
        )
        return wa, cached, cached_day
    wa = fetch_advice(gender)
    new_cache = {
        "daily_goal_ml": wa.daily_goal_ml,
        "reminder_interval_minutes": wa.reminder_interval_minutes,
        "detail": wa.detail,
        "ok": wa.ok,
        "weather_icon_url": wa.weather_icon_url,
    }
    return wa, new_cache, today

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_traditional_and_solar_1965_2030.py

Generates a unified config.ini-style file (1965–2030) combining:
1) 8 traditional festivals:
   - 春节、元宵节、清明节、母亲节、端午节、七夕节、中秋节、重阳节
2) 24 Solar Terms (二十四节气):
   - 立春、雨水、惊蛰、春分、清明、谷雨、立夏、小满、芒种、夏至、
     小暑、大暑、立秋、处暑、白露、秋分、寒露、霜降、立冬、小雪、
     大雪、冬至、小寒、大寒

Rules:
- Output format: "YYYYMMDD = 名称"
- No duplicates by date. If a solar term falls on a date already used by a festival,
  the festival takes precedence (e.g., 清明节 already added → skip the solar-term "清明").
- Ordering per year: 春节/元宵节/清明节/母亲节/端午节/七夕节/中秋节/重阳节 → all solar terms (date ascending).

Offline priority (no scraping):
- For lunar festivals: lunardate
- For Qingming: chinese_calendar → sxtwl → formula fallback
- For 24 terms: sxtwl → chinese_calendar
Install (recommend all three):
    pip install lunardate chinese-calendar sxtwl
"""

from __future__ import annotations
import sys
import math
import datetime as dt
from typing import Dict, Optional, List, Tuple, Set

# ---------- Soft dependencies ----------
_has_cc = False
try:
    import chinese_calendar  # type: ignore
    _has_cc = True
except Exception:
    _has_cc = False

_has_lunardate = False
try:
    from lunardate import LunarDate  # type: ignore
    _has_lunardate = True
except Exception:
    _has_lunardate = False

_has_sxtwl = False
try:
    import sxtwl  # type: ignore
    _has_sxtwl = True
except Exception:
    _has_sxtwl = False

YEAR_START = 1965
YEAR_END   = 2075

JQ_NAMES = [
    "立春","雨水","惊蛰","春分","清明","谷雨",
    "立夏","小满","芒种","夏至","小暑","大暑",
    "立秋","处暑","白露","秋分","寒露","霜降",
    "立冬","小雪","大雪","冬至","小寒","大寒"
]

def ymd(d: dt.date) -> str:
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

# ---------- Mother's Day ----------
def mothers_day(year: int) -> dt.date:
    d = dt.date(year, 5, 1)
    first_sun = 1 + ((6 - d.weekday()) % 7)  # Monday=0..Sunday=6
    second = first_sun + 7
    return dt.date(year, 5, second)

# ---------- Qingming detection ----------
def qingming_via_chinese_calendar(year: int) -> Optional[dt.date]:
    if not _has_cc:
        return None
    # 1) 日历假日名
    for day in range(3, 7):  # Apr 3..6
        d = dt.date(year, 4, day)
        try:
            get_detail = getattr(chinese_calendar, "get_holiday_detail", None)
            if callable(get_detail):
                detail = get_detail(d)
                nm = None
                if isinstance(detail, tuple) and len(detail) >= 2:
                    nm = getattr(detail[1], "name", str(detail[1]))
                else:
                    nm = getattr(detail, "name", str(detail))
                if nm and "清明" in str(nm):
                    return d
        except Exception:
            pass
    # 2) 节气名称
    try:
        getter = getattr(chinese_calendar, "get_solar_terms", None)
        if callable(getter):
            for day in range(1, 11):
                d = dt.date(year, 4, day)
                nm = getter(d)
                if nm and "清明" in str(nm):
                    return d
    except Exception:
        pass
    return None

def qingming_via_sxtwl(year: int) -> Optional[dt.date]:
    if not _has_sxtwl:
        return None
    try:
        lunar = sxtwl.Lunar()
        for day in range(1, 11):
            d = dt.date(year, 4, day)
            sobj = lunar.getDayBySolar(d.year, d.month, d.day)
            if hasattr(sobj, "hasJieQi") and sobj.hasJieQi():
                jq = sobj.getJieQi()
                name = None
                if hasattr(sxtwl, "getJieQiName"):
                    name = sxtwl.getJieQiName(jq)
                elif hasattr(sxtwl, "JQ"):
                    try:
                        name = sxtwl.JQ[jq]
                    except Exception:
                        name = None
                if name and "清明" in str(name):
                    return d
    except Exception:
        return None
    return None

def qingming_formula(year: int) -> dt.date:
    if 1900 <= year <= 1999:
        day = math.floor((year - 1900) * 0.2422 + 5.59) - math.floor((year - 1900) / 4)
        adjust_plus  = {1965, 1979, 1983, 1987, 1991, 1995, 1999}
        adjust_minus = {1966, 1970, 1974, 1978, 1982, 1986, 1990, 1994, 1998}
        if year in adjust_plus:  day += 1
        if year in adjust_minus: day -= 1
        return dt.date(year, 4, max(3, min(6, day)))
    elif 2000 <= year <= 2099:
        day = math.floor((year - 2000) * 0.2422 + 4.81) - math.floor((year - 2000) / 4)
        adjust_plus  = {2003, 2007, 2011, 2015, 2019, 2023, 2027}
        adjust_minus = {2002, 2006, 2010, 2014, 2018, 2021, 2025, 2029}
        if year in adjust_plus:  day += 1
        if year in adjust_minus: day -= 1
        return dt.date(year, 4, max(3, min(6, day)))
    else:
        return dt.date(year, 4, 4)

def qingming_date(year: int) -> dt.date:
    d = qingming_via_chinese_calendar(year)
    if d: return d
    d = qingming_via_sxtwl(year)
    if d: return d
    return qingming_formula(year)

# ---------- Lunar-based festivals ----------
def lunar_to_solar(year: int, lmonth: int, lday: int) -> dt.date:
    if not _has_lunardate:
        raise RuntimeError("缺少依赖：请先 `pip install lunardate` 再运行本脚本。")
    # 兼容不同版本
    try:
        return LunarDate(year, lmonth, lday).toSolarDate()
    except TypeError:
        return LunarDate(year, lmonth, lday, isleap=False).toSolarDate()

def build_traditional_for_year(year: int) -> Dict[str, dt.date]:
    r: Dict[str, dt.date] = {}
    r["春节"]   = lunar_to_solar(year, 1, 1)
    r["元宵节"] = lunar_to_solar(year, 1, 15)
    r["清明节"] = qingming_date(year)
    r["母亲节"] = mothers_day(year)
    r["端午节"] = lunar_to_solar(year, 5, 5)
    r["七夕节"] = lunar_to_solar(year, 7, 7)
    r["中秋节"] = lunar_to_solar(year, 8, 15)
    r["重阳节"] = lunar_to_solar(year, 9, 9)
    return r

# ---------- 24 Solar Terms ----------
def collect_terms_sxtwl(year: int):
    found = []
    start = dt.date(year, 1, 1)
    end   = dt.date(year, 12, 31)
    cur = start

    while cur <= end:
        sobj = sxtwl.fromSolar(cur.year, cur.month, cur.day)
        if sobj.hasJieQi():
            jq = sobj.getJieQi()
            # 名称获取兼容
            name = None
            if hasattr(sxtwl, "getJieQiName"):
                name = sxtwl.getJieQiName(jq)
            elif hasattr(sxtwl, "JQ"):
                try:
                    name = sxtwl.JQ[jq]
                except Exception:
                    pass
            if name:
                found.append((cur, str(name)))
        cur += dt.timedelta(days=1)

    return sorted(found, key=lambda x: x[0])

def collect_terms_cc(year: int) -> List[Tuple[dt.date, str]]:
    found: List[Tuple[dt.date, str]] = []
    getter = getattr(chinese_calendar, "get_solar_terms", None) if _has_cc else None
    if not callable(getter):
        return found
    start = dt.date(year, 1, 1)
    end   = dt.date(year, 12, 31)
    cur = start
    while cur <= end:
        try:
            nm = getter(cur)
            if nm:
                found.append((cur, str(nm)))
        except Exception:
            pass
        cur += dt.timedelta(days=1)
    found.sort(key=lambda x: x[0])
    return found

def collect_terms_for_year(year: int) -> List[Tuple[dt.date, str]]:
    if _has_sxtwl:
        data = collect_terms_sxtwl(year)
        if data:
            return data
    if _has_cc:
        data = collect_terms_cc(year)
        if data:
            return data
    return []

# ---------- Build + Write ----------
def main():
    if not _has_lunardate:
        print("缺少依赖：请先安装 lunardate（建议同时安装 chinese-calendar、sxtwl）：", file=sys.stderr)
        print("  pip install lunardate chinese-calendar sxtwl", file=sys.stderr)
        sys.exit(2)

    lines: List[str] = []
    lines.append("# 传统节日 + 二十四节气（1965-2030）")
    total = 0

    for y in range(YEAR_START, YEAR_END + 1):
        trad = build_traditional_for_year(y)
        used_dates: Set[str] = set()

        # 先写 8 个传统节日（固定顺序）
        for key in ["春节","元宵节","清明节","母亲节","端午节","七夕节","中秋节","重阳节"]:
            d = trad[key]
            k = ymd(d)
            lines.append(f"{k} = {key}")
            used_dates.add(k)
            total += 1

        # 再写 24 节气（不重复日期；若名称含“清明”且该日已有“清明节”，则跳过）
        terms = collect_terms_for_year(y)
        for d, name in terms:
            k = ymd(d)
            if k in used_dates:
                # 常见重叠：清明(节气) 在同一天已有 “清明节”
                continue
            # 额外保护：若是清明节气名称且同日已有“清明节”，也跳过
            if "清明" in name and k in used_dates:
                continue
            lines.append(f"{k} = {name}")
            used_dates.add(k)
            total += 1

    out_path = "config_traditional_and_solar_1965_2030.ini"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {out_path} with {total} entries.")

if __name__ == "__main__":
    main()

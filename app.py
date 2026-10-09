import ast
import configparser
import datetime
import json
import os
import re
import time

import requests
from flask import Flask, jsonify, render_template, request
try:
    import sxtwl  # type: ignore
except Exception:
    sxtwl = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
HISTORY_PATH = os.path.join(CACHE_DIR, "history.json")
KARL_TIP_HISTORY_PATH = os.path.join(CACHE_DIR, "karl_tip_history.json")
TRAD_SOLAR_CONFIG_PATH = os.path.join(
    BASE_DIR, "config_traditional_and_solar_1965_2030.ini"
)
DEFAULT_WEATHER_CONFIG = {
    "api_url": "https://api.open-meteo.com/v1/forecast",
    "timezone": "Asia/Shanghai",
    "timeout": 12,
    "default_city": "上海金山",
}
DEFAULT_WEATHER_CITIES = {
    "上海金山": {"lat": 30.8311, "lon": 121.344},
}
WEATHER_CODE_MAP = {
    0: "晴朗",
    1: "大部晴朗",
    2: "局部多云",
    3: "多云",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    56: "小冻毛毛雨",
    57: "大冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "小冻雨",
    67: "大冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "大阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}
JIEQI_NAMES = [
    "小寒",
    "大寒",
    "立春",
    "雨水",
    "惊蛰",
    "春分",
    "清明",
    "谷雨",
    "立夏",
    "小满",
    "芒种",
    "夏至",
    "小暑",
    "大暑",
    "立秋",
    "处暑",
    "白露",
    "秋分",
    "寒露",
    "霜降",
    "立冬",
    "小雪",
    "大雪",
    "冬至",
]
JIEQI_DESC = {
    "小寒": "小寒，天气寒冷但未到极致，注意保暖。",
    "大寒": "大寒是一年中最冷的节气，注意防寒保暖。",
    "立春": "立春标志春季开始，万物复苏。",
    "雨水": "雨水表示降雨增多，气温回升，适合春耕准备。",
    "惊蛰": "惊蛰春雷初动，万物苏醒。",
    "春分": "春分昼夜平分，气温回暖。",
    "清明": "清明气清景明，踏青祭扫。",
    "谷雨": "谷雨降水增多，有利于谷物生长。",
    "立夏": "立夏标志夏季开始，气温明显升高。",
    "小满": "小满麦类渐饱满，未全熟。",
    "芒种": "芒种适合播种有芒作物。",
    "夏至": "夏至白昼最长，进入盛夏。",
    "小暑": "小暑天气开始炎热，尚未最热。",
    "大暑": "大暑是一年中最热的时期，注意防暑。",
    "立秋": "立秋标志秋季开始，暑热渐退。",
    "处暑": "处暑暑气止，天气转凉。",
    "白露": "白露昼夜温差增大，露水增多。",
    "秋分": "秋分昼夜平分，秋意渐浓。",
    "寒露": "寒露气温下降，露水转寒。",
    "霜降": "霜降天气转冷，霜开始出现。",
    "立冬": "立冬标志冬季开始。",
    "小雪": "小雪气温下降，可能出现初雪。",
    "大雪": "大雪降雪增多，注意保暖出行。",
    "冬至": "冬至白昼最短，阴极之至。",
}
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
ZODIAC = [
    "\u9f20",
    "\u725b",
    "\u864e",
    "\u5154",
    "\u9f99",
    "\u86c7",
    "\u9a6c",
    "\u7f8a",
    "\u7334",
    "\u9e21",
    "\u72d7",
    "\u732a",
]


def parse_city_coords(value):
    if not value:
        return None
    parts = re.split(r"[,\\s]+", value.strip())
    if len(parts) < 2:
        return None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None
    return {"lat": lat, "lon": lon}


def load_traditional_solar_map(path):
    festivals = {}
    jieqi = {}
    if not os.path.exists(path):
        return festivals, jieqi
    for line in open(path, "r", encoding="utf-8"):
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.isdigit() or len(key) != 8 or not value:
            continue
        date_str = f"{key[:4]}-{key[4:6]}-{key[6:]}"
        if value in JIEQI_NAMES:
            jieqi[date_str] = value
        else:
            festivals.setdefault(date_str, []).append(value)
    return festivals, jieqi


def load_config():
    parser = configparser.ConfigParser()
    parser.optionxform = str
    if not parser.read(CONFIG_PATH, encoding="utf-8"):
        raise RuntimeError(f"Missing config.ini at {CONFIG_PATH}")
    if "deepseek" not in parser:
        raise RuntimeError("Missing [deepseek] section in config.ini")

    ds = parser["deepseek"]
    models = {
        "推理模型": {
            "model": ds.get("reasoner_model", "deepseek-flash").strip(),
            "desc": ds.get("reasoner_desc", "deepseek-flash(1M上下文)").strip(),
        },
        "基础模型": {
            "model": ds.get("chat_model", "deepseek-flash").strip(),
            "desc": ds.get("chat_desc", "deepseek-flash(1M上下文)").strip(),
        },
    }
    current_model = ds.get("current_model", "推理模型").strip()
    if current_model not in models:
        current_model = "推理模型"

    deepseek_config = {
        "api_url": ds.get("api_url", "").strip(),
        "api_key": ds.get("api_key", "").strip(),
        "model": models[current_model]["model"],
        "temperature": ds.getfloat("temperature", 0.3),
        "max_tokens": ds.getint("max_tokens", 8000),
        "top_p": ds.getfloat("top_p", 0.9),
        "frequency_penalty": ds.getfloat("frequency_penalty", 0.5),
        "presence_penalty": ds.getfloat("presence_penalty", 0.7),
        "stream": ds.getboolean("stream", False),
        "disable_thinking": ds.getboolean("disable_thinking", True),
        "timeout": ds.getint("request_timeout", 60),
        "retry_count": ds.getint("retry_count", 2),
        "retry_backoff": ds.getfloat("retry_backoff", 2.0),
        "retry_backoff_max": ds.getfloat("retry_backoff_max", 12.0),
    }

    weather_config = DEFAULT_WEATHER_CONFIG.copy()
    if "weather" in parser:
        wcfg = parser["weather"]
        weather_config["api_url"] = wcfg.get("api_url", weather_config["api_url"]).strip()
        weather_config["timezone"] = wcfg.get("timezone", weather_config["timezone"]).strip()
        weather_config["timeout"] = wcfg.getint("timeout", weather_config["timeout"])
        weather_config["default_city"] = wcfg.get(
            "default_city", weather_config["default_city"]
        ).strip()

    weather_cities = {}
    if "weather_cities" in parser:
        for name, value in parser["weather_cities"].items():
            coords = parse_city_coords(value)
            if coords:
                weather_cities[name.strip()] = coords

    if not weather_cities:
        weather_cities.update(DEFAULT_WEATHER_CITIES)

    if weather_config["default_city"] not in weather_cities:
        weather_config["default_city"] = next(iter(weather_cities.keys()))

    return models, current_model, deepseek_config, weather_config, weather_cities


DEEPSEEK_MODELS, CURRENT_MODEL, DEEPSEEK_CONFIG, WEATHER_CONFIG, WEATHER_CITIES = (
    load_config()
)
TRADITIONAL_FESTIVALS, JIEQI_BY_DATE = load_traditional_solar_map(
    TRAD_SOLAR_CONFIG_PATH
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.json.ensure_ascii = False

PROMPT_TEMPLATE = """
你是严谨的日历信息生成器。

【输出要求】
1. 只输出严格 JSON。
2. 不允许 Markdown，不允许解释，不允许任何额外文字。
3. 所有键名和字符串必须使用双引号。
4. 不允许尾随逗号。
5. 所有字段必须存在，不允许缺失。
6. 若确实未知，请填写暂无。

----------------------------------------
【强制校验规则（不可违反）】

1. 当前日期：{{DATE}}
2. 当前月日：{{MONTH_DAY}}

3. history.china 与 history.world：
   - 每条记录必须包含 "year"、"month_day"、"event"
   - "month_day" 必须严格等于 "{{MONTH_DAY}}"
   - 禁止使用其他月日的事件
   - 若查无资料，可输出 1 条：
     {"year":"不详","month_day":"{{MONTH_DAY}}","event":"暂无"}

4. people.births 与 people.deaths：
   - 每条记录必须包含 "year"、"month_day"、"name"、"desc"、"quote"
   - "month_day" 必须严格等于 "{{MONTH_DAY}}"
   - 禁止使用其他月日人物
   - 若查无资料，可输出 1 条占位记录，字段内容填暂无

----------------------------------------
【内容生成要求（建议范围）】

1. history.china：建议 3-6 条（上限可扩展到 36 条）
2. history.world：建议 3-6 条（上限可扩展到 36 条）
3. people.births：建议 2-5 条（上限可扩展到 25 条）
4. people.deaths：建议 2-5 条（上限可扩展到 25 条）

（若真实资料不足，可减少数量，不得编造）

----------------------------------------
【字段生成要求】

1. solar：
   - date 必须为 "{{DATE}}"
   - weekday 必须为中文星期X
   - quarter 格式为 Q1/Q2/Q3/Q4

2. lunar：
   - 提供干支年、月、日、生肖
   - 不可为空

3. jieqi：
   - 若当天非节气，可填写：
     {"name":"暂无","desc":"暂无"}

4. huangli：
   - yi / ji / ji_shen / xiong_shen / ji_shi 为数组
   - 优先输出真实可用内容，不要全部填“暂无”
   - yi / ji 建议至少各 3 条，ji_shen / xiong_shen 至少各 1 条，ji_shi 至少 2 条

5. festivals / memorial_days：
   - 数组形式
   - 优先输出该月日真实节日与纪念日
   - 若确无，festivals 输出 [{"name":"无全国性固定节日","type":"说明"}]
   - 若确无，memorial_days 输出 [{"name":"无通用纪念日","type":"说明"}]

6. culture：
   - quote_cn：一句中文名言
   - quote_en：对应英文
   - work：数组
   - greeting：一句问候语

7. lifestyle：
   - food：数组
   - tips：数组
   - clothing：一句可执行穿衣建议

8. daily_wellness：
   - tip：需包含 饮食调理、运动指导、作息安排、情绪调节
   - breakfast / lunch / dinner 必须分别给出建议

9. wellness_tip：
   - 内容必须等价于 daily_wellness.tip

10. ai_notice：
   - 固定输出：
     "以上信息由AI生成，仅供参考"

----------------------------------------
【最终 JSON 结构】

{
  "solar": {
    "date": "",
    "weekday": "",
    "week_of_year": 0,
    "quarter": "",
    "moon_phase": ""
  },
  "lunar": {
    "year": "",
    "month": "",
    "day": "",
    "is_leap_month": false,
    "ganzhi_year": "",
    "ganzhi_month": "",
    "ganzhi_day": "",
    "zodiac": ""
  },
  "jieqi": {
    "name": "",
    "desc": ""
  },
  "huangli": {
    "yi": [],
    "ji": [],
    "chong_sha": "",
    "ji_shen": [],
    "xiong_shen": [],
    "ji_shi": []
  },
  "festivals": [],
  "memorial_days": [],
  "history": {
    "china": [],
    "world": []
  },
  "people": {
    "births": [],
    "deaths": []
  },
  "culture": {
    "quote_cn": "",
    "quote_en": "",
    "work": [],
    "greeting": ""
  },
  "lifestyle": {
    "food": [],
    "tips": [],
    "clothing": ""
  },
  "daily_wellness": {
    "tip": "",
    "breakfast": "",
    "lunch": "",
    "dinner": ""
  },
  "wellness_tip": "",
  "ai_notice": ""
}
""".strip()


def get_model_id(name):
    return DEEPSEEK_MODELS.get(name, {}).get("model", DEEPSEEK_CONFIG["model"])


def ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_date(date_str):
    if not date_str:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_child_birth_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_cache_path(date_str):
    return os.path.join(CACHE_DIR, f"{date_str}.json")


def read_cache(date_str):
    path = get_cache_path(date_str)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_history():
    if not os.path.exists(HISTORY_PATH):
        return {"last_date": "", "items": []}
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"last_date": "", "items": []}
    if not isinstance(data, dict):
        return {"last_date": "", "items": []}
    data.setdefault("last_date", "")
    data.setdefault("items", [])
    if not isinstance(data["items"], list):
        data["items"] = []
    return data


def write_history(data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_history(date_str, model_name, created_at):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    history = read_history()
    items = history.get("items", [])
    existing = None
    for item in items:
        if isinstance(item, dict) and item.get("date") == date_str:
            existing = item
            break

    if existing is None:
        existing = {"date": date_str}
        items.append(existing)

    existing["model"] = model_name
    existing["created_at"] = created_at
    existing["last_query_at"] = now

    items = [i for i in items if isinstance(i, dict) and i.get("date")]
    items.sort(key=lambda x: x.get("last_query_at", ""), reverse=True)

    history["items"] = items
    history["last_date"] = date_str
    write_history(history)


def _is_date_filename(name):
    return re.match(r"^\d{4}-\d{2}-\d{2}\.json$", name) is not None


def find_latest_cache_date():
    if not os.path.isdir(CACHE_DIR):
        return ""
    latest = ("", 0.0)
    for name in os.listdir(CACHE_DIR):
        if name == "history.json":
            continue
        if not _is_date_filename(name):
            continue
        path = os.path.join(CACHE_DIR, name)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime > latest[1]:
            latest = (name, mtime)
    if latest[0]:
        return latest[0].replace(".json", "")
    return ""


def build_history_from_cache():
    items = []
    if not os.path.isdir(CACHE_DIR):
        return items
    for name in os.listdir(CACHE_DIR):
        if name == "history.json":
            continue
        if not _is_date_filename(name):
            continue
        path = os.path.join(CACHE_DIR, name)
        date_str = name.replace(".json", "")
        payload = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            payload = {}

        model_name = CURRENT_MODEL
        created_at = ""
        if isinstance(payload, dict):
            model_name = payload.get("model", model_name) or model_name
            created_at = payload.get("created_at", "") or ""

        last_query_at = created_at
        if not last_query_at:
            try:
                mtime = os.path.getmtime(path)
                last_query_at = datetime.datetime.fromtimestamp(mtime).isoformat(
                    timespec="seconds"
                )
            except OSError:
                last_query_at = ""

        items.append(
            {
                "date": date_str,
                "model": model_name,
                "created_at": created_at,
                "last_query_at": last_query_at,
            }
        )

    items = [i for i in items if isinstance(i, dict) and i.get("date")]
    items.sort(key=lambda x: x.get("last_query_at", ""), reverse=True)
    return items


def write_cache(date_str, data, model_name, created_at):
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "data": data,
        "created_at": created_at,
        "model": model_name,
    }
    path = get_cache_path(date_str)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _safe_city_name(city):
    return re.sub(r"[\\\\/:*?\"<>|]", "_", city)


def get_weather_cache_path(city, date_str):
    safe_city = _safe_city_name(city)
    return os.path.join(CACHE_DIR, f"weather-{safe_city}-{date_str}.json")


def read_weather_cache(city, date_str):
    path = get_weather_cache_path(city, date_str)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def write_weather_cache(city, date_str, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = get_weather_cache_path(city, date_str)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def resolve_weather_city(city):
    if not city:
        city = WEATHER_CONFIG.get("default_city", "")
    if city not in WEATHER_CITIES:
        city = WEATHER_CONFIG.get("default_city", "")
    coords = WEATHER_CITIES.get(city)
    return city, coords


def fetch_weather_from_api(city, date_str):
    city, coords = resolve_weather_city(city)
    if not coords:
        raise RuntimeError("Weather city not configured")
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "timezone": WEATHER_CONFIG["timezone"],
        "current_weather": True,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
    }
    resp = requests.get(
        WEATHER_CONFIG["api_url"],
        params=params,
        timeout=WEATHER_CONFIG["timeout"],
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Weather error: {resp.status_code} {resp.text}")
    data = resp.json()
    daily = data.get("daily", {}) or {}
    times = daily.get("time", []) or []
    if not times:
        raise RuntimeError("Weather data missing daily.time")

    try:
        idx = times.index(date_str)
    except ValueError:
        idx = 0

    def pick_list(key):
        values = daily.get(key, []) or []
        if idx < len(values):
            return values[idx]
        return None

    weather_code = pick_list("weathercode")
    desc = WEATHER_CODE_MAP.get(weather_code, "多云")
    temp_max = pick_list("temperature_2m_max")
    temp_min = pick_list("temperature_2m_min")
    precip_prob = pick_list("precipitation_probability_max")

    current = data.get("current_weather", {}) or {}
    wind_speed = current.get("windspeed")
    temperature = current.get("temperature")

    return {
        "location": city,
        "date": date_str,
        "desc": desc,
        "temp_max": temp_max,
        "temp_min": temp_min,
        "temperature": temperature,
        "precip_prob": precip_prob,
        "wind_speed": wind_speed,
        "source": "Open-Meteo",
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def get_today_weather(city):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    city, _ = resolve_weather_city(city)
    cached = read_weather_cache(city, today_str)
    if cached:
        return cached
    data = fetch_weather_from_api(city, today_str)
    write_weather_cache(city, today_str, data)
    return data


def _gz_to_str(gz):
    return GAN[gz.tg] + ZHI[gz.dz]


def _lunar_month_name(month):
    names = [
        "正",
        "二",
        "三",
        "四",
        "五",
        "六",
        "七",
        "八",
        "九",
        "十",
        "冬",
        "腊",
    ]
    if 1 <= month <= 12:
        return f"{names[month - 1]}月"
    return "暂无"


def _lunar_day_name(day):
    if not (1 <= day <= 30):
        return "暂无"
    if day == 10:
        return "初十"
    if day == 20:
        return "二十"
    if day == 30:
        return "三十"
    tens = day // 10
    ones = day % 10
    prefix = ["初", "十", "廿", "三"][tens]
    nums = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    return prefix + nums[ones]


def get_lunar_info(date_obj):
    if not sxtwl:
        return {}
    day = sxtwl.fromSolar(date_obj.year, date_obj.month, date_obj.day)
    year_gz = _gz_to_str(day.getYearGZ())
    month_gz = _gz_to_str(day.getMonthGZ())
    day_gz = _gz_to_str(day.getDayGZ())
    zodiac = ZODIAC[day.getYearGZ().dz]
    month = day.getLunarMonth()
    day_num = day.getLunarDay()
    is_leap = day.isLunarLeap()
    lunar_month = _lunar_month_name(month)
    lunar_day = _lunar_day_name(day_num)
    return {
        "year": f"{year_gz}年",
        "month": lunar_month,
        "day": lunar_day,
        "is_leap_month": bool(is_leap),
        "ganzhi_year": year_gz,
        "ganzhi_month": month_gz,
        "ganzhi_day": day_gz,
        "zodiac": zodiac,
    }


def _jieqi_name_from_idx(idx):
    if idx is None:
        return ""
    if idx <= 0:
        return ""
    pos = idx - 1
    if pos < 0 or pos >= len(JIEQI_NAMES):
        return ""
    return JIEQI_NAMES[pos]


def get_current_jieqi(date_obj):
    if not sxtwl:
        return "", None
    cur = date_obj
    for _ in range(40):
        day = sxtwl.fromSolar(cur.year, cur.month, cur.day)
        if day.hasJieQi():
            name = _jieqi_name_from_idx(day.getJieQi())
            if name:
                return name, cur
        cur -= datetime.timedelta(days=1)
    return "", None


def get_jieqi_info(date_str, date_obj):
    name = JIEQI_BY_DATE.get(date_str, "")
    term_date = None
    if not name:
        name, term_date = get_current_jieqi(date_obj)
    desc = JIEQI_DESC.get(name, "暂无") if name else "暂无"
    if term_date:
        day_no = (date_obj - term_date).days + 1
        if day_no < 1:
            day_no = 1
        if term_date.strftime("%Y-%m-%d") != date_str:
            desc = (
                f"{desc}（本节气开始于{term_date.strftime('%Y-%m-%d')}，"
                f"第{day_no}天）"
            )
        else:
            desc = f"{desc}（第{day_no}天）"
    return {"name": name or "暂无", "desc": desc}


def _season_name(date_obj):
    month = date_obj.month
    if month in (12, 1, 2):
        return "冬季"
    if month in (3, 4, 5):
        return "春季"
    if month in (6, 7, 8):
        return "夏季"
    return "秋季"


def _build_special_info(data):
    parts = []
    jieqi_name = (data.get("jieqi", {}) or {}).get("name", "")
    if isinstance(jieqi_name, str) and jieqi_name.strip() and jieqi_name.strip() != "暂无":
        parts.append(f"节气为{jieqi_name.strip()}")

    festivals = []
    for item in ensure_list(data.get("festivals")):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name and name != "暂无":
                festivals.append(name)
    if festivals:
        parts.append(f"节日信息：{'、'.join(festivals[:2])}")

    memorial_days = []
    for item in ensure_list(data.get("memorial_days")):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name and name != "暂无":
                memorial_days.append(name)
    if memorial_days:
        parts.append(f"纪念日信息：{'、'.join(memorial_days[:2])}")

    if not parts:
        return "暂无明显特殊节日或节气提示"
    return "；".join(parts)


def _normalize_clothing_advice(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("clothing", "advice", "tip", "suggestion"):
            raw = value.get(key, "")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "，".join(parts)
    return ""


def _fallback_clothing_advice(date_obj, data):
    season = _season_name(date_obj)
    jieqi_name = (data.get("jieqi", {}) or {}).get("name", "").strip()
    mapping = {
        "春季": "建议采用“洋葱式”穿搭：长袖打底+薄外套，早晚适当加一层，午后体感升温可及时减衣。",
        "夏季": "建议轻薄透气为主：短袖+防晒外层，外出带帽，出汗后及时擦干并更换干爽衣物。",
        "秋季": "建议长袖或薄针织搭轻外套，关注颈背与脚踝保暖，昼夜温差大时随身备开衫。",
        "冬季": "建议三层保暖：排汗内层+保温中层+防风外层，重点保护头颈、腰腹和足部。",
    }
    advice = mapping.get(season, "建议按体感分层穿衣，注意保暖与透气平衡，避免忽冷忽热。")
    if jieqi_name and jieqi_name != "暂无":
        advice += f" 当前节气为{jieqi_name}，可按当天体感微调增减。"
    return advice


def _build_clothing_prompt(date_obj, data):
    season = _season_name(date_obj)
    special_info = _build_special_info(data)
    weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][date_obj.weekday()]
    return f"""
今天是 {date_obj.strftime('%Y年%m月%d日')}，星期{weekday_cn}，当前处于{season}，{special_info}。
请生成一条“今日穿衣建议”。要求：
1. 内容具体可执行，需包含上装/外层增减或保暖防晒要点；
2. 只写一句话，40-90字，口吻简洁亲切；
3. 可结合节气或节日做简短提醒；
4. 请仅输出严格JSON，不要任何解释，格式如下：
{{
  "clothing": "今日穿衣建议"
}}
""".strip()


def generate_clothing_advice(date_obj, data):
    prompt = _build_clothing_prompt(date_obj, data)
    messages = [
        {"role": "system", "content": "你是中文生活方式助手，只输出严格JSON。"},
        {"role": "user", "content": prompt},
    ]
    model_id = get_model_id("基础模型")
    content = _deepseek_request(messages, model_id).strip()
    try:
        parsed = extract_json(content)
    except Exception:
        parsed = {}
    clothing = _normalize_clothing_advice(parsed)
    if len(clothing) > 140:
        clothing = clothing[:137].rstrip() + "..."
    return clothing


def ensure_lifestyle_clothing(data, date_obj, allow_llm=True):
    lifestyle = data.setdefault("lifestyle", {})
    if not isinstance(lifestyle, dict):
        lifestyle = {}
        data["lifestyle"] = lifestyle

    existing = _normalize_clothing_advice(lifestyle.get("clothing"))
    if existing and existing != "暂无":
        lifestyle["clothing"] = existing
        return data

    if allow_llm:
        try:
            generated = generate_clothing_advice(date_obj, data)
            if generated and generated != "暂无":
                lifestyle["clothing"] = generated
                return data
        except Exception:
            pass

    lifestyle["clothing"] = _fallback_clothing_advice(date_obj, data)
    return data


def _normalize_daily_wellness(value):
    out = {"tip": "", "breakfast": "", "lunch": "", "dinner": ""}
    if not isinstance(value, dict):
        return out

    for key in out.keys():
        raw = value.get(key, "")
        if isinstance(raw, str):
            out[key] = raw.strip()

    meals = value.get("meals")
    if isinstance(meals, dict):
        for key in ("breakfast", "lunch", "dinner"):
            meal_value = meals.get(key, "")
            if isinstance(meal_value, str) and meal_value.strip():
                out[key] = meal_value.strip()

    return out


def _is_daily_wellness_complete(value):
    bundle = _normalize_daily_wellness(value)
    for key in ("tip", "breakfast", "lunch", "dinner"):
        item = bundle.get(key, "")
        if not item or item == "暂无":
            return False
    return True


def _fallback_daily_wellness(date_obj, data):
    season = _season_name(date_obj)
    jieqi_name = (data.get("jieqi", {}) or {}).get("name", "暂无")
    return {
        "tip": (
            f"• 饮食调理：{season}建议清淡均衡，三餐定时，晚餐七分饱并注意补水。\n"
            "• 运动指导：进行20-40分钟中低强度运动，如快走、拉伸或轻力量训练。\n"
            "• 作息安排：尽量23点前入睡，晨起接触自然光10分钟，稳定生物节律。\n"
            f"• 情绪调节：结合“{jieqi_name}”做3-5分钟呼吸放松，睡前记录1件积极小事。"
        ),
        "breakfast": f"{season}早餐建议：燕麦或杂粮粥+鸡蛋+当季水果，避免空腹只喝咖啡。",
        "lunch": "午餐建议：优质蛋白（鱼/鸡胸/豆腐）+两份蔬菜+少量杂粮饭，八分饱为宜。",
        "dinner": "晚餐建议：清淡易消化（蔬菜汤+蒸蛋+少量粗粮），尽量在睡前3小时完成。",
    }


def _build_daily_wellness_prompt(date_obj, data):
    season = _season_name(date_obj)
    special_info = _build_special_info(data)
    weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][date_obj.weekday()]
    return f"""
今天是 {date_obj.strftime('%Y年%m月%d日')}，星期{weekday_cn}，当前处于{season}，{special_info}。
请根据以上日期信息，为今天的用户生成一份实用的养生建议。要求：
1. 建议应包含：饮食调理、运动指导、作息安排、情绪调节；
2. 结合当天季节/节气或特殊日期，给出具体可执行建议；
3. 语言亲切易懂，避免过于专业术语；
4. 同时给出当日三餐建议（早餐、午餐、晚餐）。
5. 以分点形式呈现，总字数控制在500字以内；

请仅输出严格JSON，不要任何解释，格式如下：
{{
  "tip": "分点养生建议文本",
  "meals": {{
    "breakfast": "早餐建议",
    "lunch": "午餐建议",
    "dinner": "晚餐建议"
  }}
}}
""".strip()


def generate_daily_wellness(date_obj, data):
    prompt = _build_daily_wellness_prompt(date_obj, data)
    messages = [
        {"role": "system", "content": "你是温和、务实的中文养生顾问，只输出严格JSON。"},
        {"role": "user", "content": prompt},
    ]
    model_id = get_model_id("基础模型")
    content = _deepseek_request(messages, model_id).strip()
    try:
        parsed = extract_json(content)
    except Exception:
        parsed = {}
    bundle = _normalize_daily_wellness(parsed)
    if not bundle.get("tip"):
        tip_text = content
        if len(tip_text) > 320:
            tip_text = tip_text[:317].rstrip() + "..."
        bundle["tip"] = tip_text
    return bundle


def ensure_daily_wellness_data(data, date_obj, allow_llm=True):
    existing_bundle = _normalize_daily_wellness(data.get("daily_wellness"))
    if (
        not existing_bundle.get("tip")
        and isinstance(data.get("wellness_tip"), str)
        and data.get("wellness_tip", "").strip()
        and data.get("wellness_tip", "").strip() != "暂无"
    ):
        existing_bundle["tip"] = data.get("wellness_tip", "").strip()

    if _is_daily_wellness_complete(existing_bundle):
        data["daily_wellness"] = existing_bundle
        data["wellness_tip"] = existing_bundle["tip"]
        return data

    fallback_bundle = _fallback_daily_wellness(date_obj, data)
    if allow_llm:
        try:
            generated_bundle = generate_daily_wellness(date_obj, data)
            merged_bundle = fallback_bundle.copy()
            for key in ("tip", "breakfast", "lunch", "dinner"):
                value = generated_bundle.get(key, "")
                if isinstance(value, str) and value.strip():
                    merged_bundle[key] = value.strip()
            data["daily_wellness"] = merged_bundle
            data["wellness_tip"] = merged_bundle["tip"]
            return data
        except Exception:
            pass

    merged_bundle = fallback_bundle.copy()
    for key in ("tip", "breakfast", "lunch", "dinner"):
        value = existing_bundle.get(key, "")
        if isinstance(value, str) and value.strip() and value.strip() != "暂无":
            merged_bundle[key] = value.strip()
    data["daily_wellness"] = merged_bundle
    data["wellness_tip"] = merged_bundle["tip"]
    return data


def _age_ymd(birth_date, target_date):
    years = target_date.year - birth_date.year
    months = target_date.month - birth_date.month
    days = target_date.day - birth_date.day

    if days < 0:
        last_month_day = (target_date.replace(day=1) - datetime.timedelta(days=1)).day
        days += last_month_day
        months -= 1

    if months < 0:
        months += 12
        years -= 1

    return years, months, days


def _get_karl_fine_stage(total_months):
    if total_months <= 3:
        return ("0-3个月（新生适应期）", "重点建立安全依恋，稳定喂养与睡眠节律。")
    if total_months <= 6:
        return ("4-6个月（感觉统合启动期）", "通过触觉、听觉、视觉刺激，提升注意与回应。")
    if total_months <= 9:
        return ("7-9个月（动作探索期）", "鼓励翻身、爬行与抓握，建立手眼协调。")
    if total_months <= 12:
        return ("10-12个月（理解与模仿期）", "强化指令理解、动作模仿与共同注意。")
    if total_months <= 18:
        return ("13-18个月（词汇爆发准备期）", "用高频命名和情境复述，促进听懂到会说。")
    if total_months <= 24:
        return ("19-24个月（双词句萌芽期）", "鼓励名词加动作表达，建立初步规则意识。")
    if total_months <= 30:
        return ("25-30个月（规则意识起步期）", "训练轮流、等待、收纳与步骤执行。")
    if total_months <= 36:
        return ("31-36个月（自我表达扩展期）", "加强情绪命名、事件复述与选择决策。")
    if total_months <= 48:
        return ("3-4岁（想象与叙事期）", "通过角色扮演和故事接龙训练连续叙事。")
    if total_months <= 60:
        return ("4-5岁（逻辑分类期）", "发展比较、分类、排序与简单推理。")
    if total_months <= 72:
        return ("5-6岁（入学准备期）", "提升专注、任务完成与规则执行能力。")
    if total_months <= 96:
        return ("6-8岁（基础学习习惯期）", "稳定阅读、作业节律、时间管理与复盘习惯。")
    if total_months <= 132:
        return ("9-11岁（抽象思维萌芽期）", "强化提问能力、证据意识与多角度思考。")
    if total_months <= 168:
        return ("12-14岁（青春前期自我建构期）", "支持价值观形成、同伴关系管理和情绪调节。")
    if total_months <= 216:
        return ("15-18岁（目标与身份探索期）", "训练目标拆解、执行与责任承担。")
    return ("18岁以上（青年自驱深化期）", "聚焦长期规划、独立决策与持续行动。")


KARL_THEME_POOLS = {
    "0-2": ["感官探索", "语言输入", "动作协同", "依恋互动", "生活节律", "情绪安抚"],
    "2-6": ["表达叙事", "规则执行", "专注训练", "社交合作", "逻辑分类", "情绪识别"],
    "6-12": ["阅读理解", "计划复盘", "科学探究", "表达思辨", "时间管理", "项目实践"],
    "12+": ["目标拆解", "自我管理", "情绪韧性", "沟通协商", "批判思维", "责任担当"],
}

KARL_ACTIVITY_POOL = {
    "0-2": {
        "main": [
            "围绕“{theme}”做一轮{duration}亲子互动：看实物-命名-等待回应，重复8到12次。",
            "安排{duration}共玩：家长先示范动作，再请孩子模仿并用简单词汇描述。",
            "进行{duration}轮流小游戏：你来我往地发声、拍手或传球，强化互动节律。",
        ],
        "backup": [
            "状态一般时改为5分钟轻量版：只做看图命名和微笑回应，保持节奏稳定。",
            "把任务拆成两次短练：每次3到5分钟，优先保证正向互动体验。",
            "先做拥抱与安抚，再用1本小绘本做简短共读，结束即表扬。",
        ],
        "advanced": [
            "在主任务后加1轮“指令-动作”练习，例如“把球给妈妈”。",
            "把今天新词放入生活场景中复现3次，促进理解到表达迁移。",
            "加入1次共同注意训练：指向同一物体并等待孩子眼神/手势回应。",
        ],
        "observation": [
            "记录孩子是否更快回应名字与指令，是否出现主动发声或手势。",
            "观察专注持续时长、情绪波动点以及安抚后的恢复速度。",
            "关注抓握/模仿是否更稳定，是否出现新的互动信号。",
        ],
        "review": [
            "今天哪一个互动环节孩子最投入？下次先从这个环节开始。",
            "孩子在哪一步容易分心？明天如何把步骤再简化一点？",
            "今天你给出的表扬是否具体？明天想强化哪一句鼓励语？",
        ],
    },
    "2-6": {
        "main": [
            "围绕“{theme}”进行{duration}任务：先示范，再让孩子独立完成1轮并复述过程。",
            "安排{duration}游戏化训练：目标明确、步骤不超过3步，完成后即时反馈。",
            "做{duration}情景活动：让孩子在规则内自主选择并说出理由。",
        ],
        "backup": [
            "孩子疲劳时改为10分钟迷你任务，只保留“开始-执行-收尾”三步。",
            "把目标拆成两个小回合，每回合结束给一次具体表扬。",
            "改用绘本或角色扮演同主题练习，降低任务阻力。",
        ],
        "advanced": [
            "增加1次“轮流与等待”挑战，练习规则执行和冲动控制。",
            "让孩子把活动讲给家人听，训练连续叙事与表达清晰度。",
            "加入“如果...那么...”的小推理题，强化因果思维。",
        ],
        "observation": [
            "关注是否能按步骤完成任务，遇到困难时是否愿意再次尝试。",
            "观察表达完整度、规则遵守度和情绪恢复速度。",
            "记录孩子主动提问次数与独立解决问题的信号。",
        ],
        "review": [
            "今天孩子最擅长的是哪一步？明天是否可以提高半级难度？",
            "哪条规则执行最稳定？下次是否能加入一个新规则？",
            "你今天的反馈是否具体到行为？明天想强化哪类行为？",
        ],
    },
    "6-12": {
        "main": [
            "围绕“{theme}”做{duration}单任务训练：先计划，再执行，最后口头复盘。",
            "安排{duration}学习任务：孩子先说目标和步骤，再独立完成并自评。",
            "进行{duration}项目化练习：产出一个可展示结果（笔记/图表/短讲）。",
        ],
        "backup": [
            "如果状态波动，改为15分钟聚焦练习，保证“完成度”优先于“难度”。",
            "把大任务拆成两段，中间加2分钟放松并回顾目标。",
            "先做一道热身题建立成功体验，再进入主任务。",
        ],
        "advanced": [
            "加入证据链提问：观点是什么，证据是什么，还缺什么信息。",
            "增加1次错因分析：错误来自审题、步骤还是计算/表达。",
            "让孩子制定明日计划并给出可量化完成标准。",
        ],
        "observation": [
            "记录专注时长、任务完成率和复盘质量是否提升。",
            "观察是否能主动提问、主动查证并修正自己的结论。",
            "关注时间分配是否合理，是否出现拖延与回避。",
        ],
        "review": [
            "今天最有效的学习方法是什么？明天是否继续沿用？",
            "哪个步骤最耗时？可以怎样提前准备来提速？",
            "复盘是否落到可执行改进点？明天先验证哪一条？",
        ],
    },
    "12+": {
        "main": [
            "围绕“{theme}”安排{duration}自主任务：目标拆解、执行打卡、结果复盘。",
            "进行{duration}自我管理练习：先定优先级，再完成最关键任务。",
            "做{duration}现实议题讨论：提出观点、证据和可执行方案。",
        ],
        "backup": [
            "状态不稳时改为20分钟核心任务冲刺，优先完成最关键一步。",
            "把任务拆成“准备-执行-复盘”三段，每段设置明确时限。",
            "先做5分钟情绪整理，再进入主任务，降低内耗。",
        ],
        "advanced": [
            "加入一次责任承担环节：独立汇报结果并提出下一步计划。",
            "完成后写3行复盘：有效策略、失误原因、改进动作。",
            "增加“反方视角”推演，训练多角度思考与沟通。",
        ],
        "observation": [
            "关注任务启动速度、坚持度、复盘深度和责任意识。",
            "观察是否能在压力下保持表达清晰与情绪稳定。",
            "记录是否出现主动规划与主动求助的行为信号。",
        ],
        "review": [
            "今天的目标是否足够具体？明天第一步是什么？",
            "哪件事最容易拖延？能否设置更小的启动动作？",
            "今天的决策依据是什么？是否有更优替代方案？",
        ],
    },
}

KARL_BANNED_TERMS = [
    "体罚",
    "羞辱",
    "恐吓",
    "辱骂",
    "长时间刷屏",
    "熬夜学习",
    "极限训练",
]


def _karl_phase_profile(total_months):
    if total_months < 24:
        return (
            "0-2岁：感官与语言启蒙",
            "以高质量陪伴和重复交互为主，强化表达与安全感。",
            "语言启蒙与亲子依恋",
            "0-2",
        )
    if total_months < 72:
        return (
            "2-6岁：兴趣驱动与习惯养成",
            "以短时高频替代长时灌输，在游戏中建立秩序与自主。",
            "观察表达与规则习惯",
            "2-6",
        )
    if total_months < 144:
        return (
            "6-12岁：思维训练与自主学习",
            "从被动听转向主动问，形成计划-执行-复盘闭环。",
            "学习方法与思维训练",
            "6-12",
        )
    return (
        "12岁以上：自驱与品格发展",
        "将他律管理过渡为自我管理，强化目标感、责任感与韧性。",
        "自我管理与长期目标",
        "12+",
    )


def _karl_duration_text(total_months):
    if total_months < 24:
        return "8-12分钟"
    if total_months < 72:
        return "12-20分钟"
    if total_months < 144:
        return "20-30分钟"
    return "25-40分钟"


def _karl_seed(*parts):
    text = "|".join(str(p) for p in parts)
    score = 0
    for idx, ch in enumerate(text):
        score += (idx + 1) * ord(ch)
    return score


def _pick_from_pool(items, seed, offset=0):
    if not items:
        return ""
    return items[(seed + offset) % len(items)]


def _read_karl_tip_history():
    if not os.path.exists(KARL_TIP_HISTORY_PATH):
        return {"items": []}
    with open(KARL_TIP_HISTORY_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"items": []}
    if not isinstance(data, dict):
        return {"items": []}
    items = data.get("items", [])
    if not isinstance(items, list):
        items = []
    data["items"] = [x for x in items if isinstance(x, dict)]
    return data


def _write_karl_tip_history(data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(KARL_TIP_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find_karl_cached_record(history_data, birth_date_str, date_str):
    for item in history_data.get("items", []):
        if (
            item.get("birth_date") == birth_date_str
            and item.get("date") == date_str
        ):
            return item
    return None


def _collect_karl_recent_records(history_data, birth_date_str, phase_key, date_str, limit=7):
    rows = []
    for item in history_data.get("items", []):
        if item.get("birth_date") != birth_date_str:
            continue
        if item.get("phase_key") != phase_key:
            continue
        item_date = str(item.get("date", "")).strip()
        if not item_date or item_date >= date_str:
            continue
        rows.append(item)
    rows.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    return rows[:limit]


def _choose_karl_theme(phase_key, birth_date_str, date_obj, recent_records):
    pool = KARL_THEME_POOLS.get(phase_key, KARL_THEME_POOLS["2-6"])
    recent_themes = [str(x.get("theme", "")).strip() for x in recent_records[:4]]
    candidates = [x for x in pool if x and x not in recent_themes]
    if not candidates:
        candidates = pool
    seed = _karl_seed(birth_date_str, date_obj.strftime("%Y-%m-%d"), phase_key, "theme")
    return _pick_from_pool(candidates, seed)


def _build_local_karl_plan(
    date_obj,
    birth_date_str,
    phase_key,
    theme,
    stage_task,
    fine_focus,
    duration_text,
):
    pool = KARL_ACTIVITY_POOL.get(phase_key, KARL_ACTIVITY_POOL["2-6"])
    seed = _karl_seed(birth_date_str, date_obj.strftime("%Y-%m-%d"), phase_key, theme)
    plan = {
        "tip_main": _pick_from_pool(pool.get("main", []), seed, 0),
        "tip_backup": _pick_from_pool(pool.get("backup", []), seed, 1),
        "tip_advanced": _pick_from_pool(pool.get("advanced", []), seed, 2),
        "observation": _pick_from_pool(pool.get("observation", []), seed, 3),
        "review_question": _pick_from_pool(pool.get("review", []), seed, 4),
        "tip": "",
    }

    for key in ("tip_main", "tip_backup", "tip_advanced", "observation", "review_question"):
        text = plan.get(key, "")
        if isinstance(text, str):
            plan[key] = text.format(
                theme=theme,
                duration=duration_text,
                stage_task=stage_task,
                fine_focus=fine_focus,
            ).strip()
        else:
            plan[key] = ""

    if not plan["tip_main"]:
        plan["tip_main"] = (
            f"围绕“{theme}”进行1次{duration_text}亲子任务，先示范再让孩子独立尝试。"
        )
    if not plan["tip_backup"]:
        plan["tip_backup"] = "状态一般时将任务拆成两段短练，保持积极反馈。"
    if not plan["tip_advanced"]:
        plan["tip_advanced"] = "完成后做1次简短复述，巩固今天的关键能力。"
    if not plan["observation"]:
        plan["observation"] = "观察专注时长、指令理解和主动表达变化。"
    if not plan["review_question"]:
        plan["review_question"] = "今天哪一步最有效，明天先从哪一步开始？"
    return plan


def _normalize_karl_plan_payload(value):
    out = {
        "tip_main": "",
        "tip_backup": "",
        "tip_advanced": "",
        "observation": "",
        "review_question": "",
        "tip": "",
    }
    if not isinstance(value, dict):
        return out
    for key in out:
        raw = value.get(key, "")
        if isinstance(raw, str):
            out[key] = raw.strip()
    return out


def _normalize_text_compact(text):
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _text_signature(text):
    text = _normalize_text_compact(text)
    text = re.sub(r"[，。！？；：、“”‘’（）()【】\[\]\-—,.!?;:'\"\\s]", "", text)
    return text


def _contains_karl_banned_terms(text):
    value = _normalize_text_compact(text)
    return any(word in value for word in KARL_BANNED_TERMS)


def _karl_text_usable(text, min_len=8):
    value = _normalize_text_compact(text)
    if not value:
        return False
    if value in {"暂无", "不详", "未知"}:
        return False
    if len(value) < min_len:
        return False
    if _contains_karl_banned_terms(value):
        return False
    return True


def _karl_text_repeated(candidate, recent_texts):
    sig = _text_signature(candidate)
    if len(sig) < 8:
        return False
    for text in recent_texts:
        if sig == _text_signature(text):
            return True
    return False


def _build_karl_api_prompt(
    date_obj,
    age_text,
    phase,
    fine_phase,
    fine_focus,
    principle,
    stage_task,
    theme,
    duration_text,
    local_plan,
    recent_main_texts,
):
    recent_block = "\n".join(f"- {x}" for x in recent_main_texts[:7]) or "- 无"
    return f"""
你是儿童发展与家庭教育助手，请基于固定条件生成“卡尔·威特今日育儿提示”。

固定条件：
- 日期：{date_obj.strftime('%Y-%m-%d')}
- 当日年龄：{age_text}
- 大阶段：{phase}
- 精细阶段：{fine_phase}
- 当前关键能力：{fine_focus}
- 理念要点：{principle}
- 今日主题：{stage_task} / {theme}
- 建议时长：{duration_text}

最近7天主任务（避免重复）：
{recent_block}

本地基准方案（请在不偏离目标的前提下优化文案）：
- 主任务：{local_plan.get('tip_main', '')}
- 备选任务：{local_plan.get('tip_backup', '')}
- 进阶任务：{local_plan.get('tip_advanced', '')}
- 观察点：{local_plan.get('observation', '')}

强制规则：
1) 只输出严格JSON，禁止Markdown和解释；
2) 必须包含字段：tip_main, tip_backup, tip_advanced, observation, review_question, tip；
3) 内容务实可执行，避免空话；不得包含体罚、羞辱、恐吓、熬夜等不当建议；
4) tip_main 必须包含时长信息（如“{duration_text}”）；
5) 与最近7天主任务避免同句重复。

输出格式：
{{
  "tip_main": "",
  "tip_backup": "",
  "tip_advanced": "",
  "observation": "",
  "review_question": "",
  "tip": ""
}}
""".strip()


def _generate_karl_plan_from_api(
    date_obj,
    age_text,
    phase,
    fine_phase,
    fine_focus,
    principle,
    stage_task,
    theme,
    duration_text,
    local_plan,
    recent_main_texts,
):
    prompt = _build_karl_api_prompt(
        date_obj=date_obj,
        age_text=age_text,
        phase=phase,
        fine_phase=fine_phase,
        fine_focus=fine_focus,
        principle=principle,
        stage_task=stage_task,
        theme=theme,
        duration_text=duration_text,
        local_plan=local_plan,
        recent_main_texts=recent_main_texts,
    )
    messages = [
        {
            "role": "system",
            "content": "你是严谨的育儿建议生成器，只输出严格JSON。",
        },
        {"role": "user", "content": prompt},
    ]
    model_id = get_model_id("基础模型")
    quick_timeout = min(25, int(DEEPSEEK_CONFIG.get("timeout", 60)))
    quick_tokens = min(1600, int(DEEPSEEK_CONFIG.get("max_tokens", 8000)))
    content = _deepseek_request(
        messages,
        model_id,
        timeout=quick_timeout,
        retry_count=0,
        max_tokens=quick_tokens,
    ).strip()
    try:
        parsed = extract_json(content)
    except Exception:
        parsed = {}
    return _normalize_karl_plan_payload(parsed)


def _merge_karl_plan(local_plan, generated_plan, recent_main_texts, duration_text):
    merged = dict(local_plan)
    for key, min_len in (
        ("tip_main", 12),
        ("tip_backup", 8),
        ("tip_advanced", 8),
        ("observation", 8),
        ("review_question", 8),
    ):
        candidate = generated_plan.get(key, "")
        if not _karl_text_usable(candidate, min_len=min_len):
            continue
        if key in {"tip_main", "tip_backup", "tip_advanced"} and _karl_text_repeated(
            candidate, recent_main_texts
        ):
            continue
        merged[key] = _normalize_text_compact(candidate)

    if "分钟" not in merged.get("tip_main", ""):
        merged["tip_main"] = f"{merged.get('tip_main', '').rstrip('。')}（建议时长：{duration_text}）。"

    tip_candidate = generated_plan.get("tip", "")
    if _karl_text_usable(tip_candidate, min_len=20):
        merged["tip"] = _normalize_text_compact(tip_candidate)
    else:
        merged["tip"] = ""
    return merged


def _compose_karl_tip(fine_focus, stage_task, theme, plan):
    return (
        f"精细阶段目标：{fine_focus} 今日主题：{stage_task}（{theme}）。"
        f"主任务：{plan.get('tip_main', '')} "
        f"备选任务：{plan.get('tip_backup', '')} "
        f"进阶任务：{plan.get('tip_advanced', '')} "
        f"观察点：{plan.get('observation', '')} "
        f"复盘提问：{plan.get('review_question', '')}"
    ).strip()


def _save_karl_tip_record(history_data, record):
    items = [x for x in history_data.get("items", []) if isinstance(x, dict)]
    updated = False
    for item in items:
        if (
            item.get("date") == record.get("date")
            and item.get("birth_date") == record.get("birth_date")
        ):
            item.update(record)
            updated = True
            break
    if not updated:
        items.append(record)
    items.sort(
        key=lambda x: (str(x.get("date", "")), str(x.get("created_at", ""))),
        reverse=True,
    )
    history_data["items"] = items[:1200]
    _write_karl_tip_history(history_data)


def get_karl_witte_tip(date_obj, birth_date=None):
    if birth_date is None:
        return {
            "birth_date": "",
            "age": "",
            "phase": "",
            "phase_fine": "",
            "fine_focus": "",
            "principle": "",
            "daily_theme": "",
            "tip_main": "",
            "tip_backup": "",
            "tip_advanced": "",
            "observation": "",
            "review_question": "",
            "tip": "输入儿童生日后生成育儿建议。",
        }

    date_str = date_obj.strftime("%Y-%m-%d")
    birth_date_str = birth_date.strftime("%Y-%m-%d")

    if date_obj < birth_date:
        return {
            "birth_date": birth_date_str,
            "age": "未出生",
            "phase": "家庭环境预备期",
            "phase_fine": "孕育准备期",
            "fine_focus": "先统一家庭养育方式与作息节律，准备稳定的亲子互动环境。",
            "principle": "先稳定亲子关系与作息节律，再开启系统能力训练。",
            "tip_main": "先完成阅读角和游戏角的安全布置。",
            "tip_backup": "和家人统一育儿语言与回应方式。",
            "tip_advanced": "制定未来两周的家庭作息与陪伴时段。",
            "observation": "观察家庭成员是否能稳定执行同一套养育口令。",
            "review_question": "今天完成了哪项环境准备？明天优先补齐哪一项？",
            "tip": "今日建议：先完成阅读角和游戏角的安全布置，并与家人统一育儿语言风格。",
        }

    years, months, days = _age_ymd(birth_date, date_obj)
    total_months = years * 12 + months
    fine_phase, fine_focus = _get_karl_fine_stage(total_months)
    phase, principle, stage_task, phase_key = _karl_phase_profile(total_months)
    age_text = f"{years}岁{months}个月{days}天"
    duration_text = _karl_duration_text(total_months)

    history_data = _read_karl_tip_history()
    cached_record = _find_karl_cached_record(history_data, birth_date_str, date_str)
    if cached_record and all(
        _karl_text_usable(cached_record.get(key, ""), 6)
        for key in ("tip_main", "tip_backup", "tip_advanced", "observation")
    ):
        tip_main = _normalize_text_compact(cached_record.get("tip_main", ""))
        tip_backup = _normalize_text_compact(cached_record.get("tip_backup", ""))
        tip_advanced = _normalize_text_compact(cached_record.get("tip_advanced", ""))
        observation = _normalize_text_compact(cached_record.get("observation", ""))
        review_question = _normalize_text_compact(
            cached_record.get("review_question", "")
        ) or "今天最有效的一步是什么？明天如何复用？"
        daily_theme = _normalize_text_compact(cached_record.get("theme", "")) or "日常养成"
        tip = _normalize_text_compact(cached_record.get("tip", ""))
        if not _karl_text_usable(tip, 20):
            tip = _compose_karl_tip(
                fine_focus,
                stage_task,
                daily_theme,
                {
                    "tip_main": tip_main,
                    "tip_backup": tip_backup,
                    "tip_advanced": tip_advanced,
                    "observation": observation,
                    "review_question": review_question,
                },
            )
        return {
            "birth_date": birth_date_str,
            "age": age_text,
            "phase": phase,
            "phase_fine": fine_phase,
            "fine_focus": fine_focus,
            "principle": principle,
            "daily_theme": daily_theme,
            "tip_main": tip_main,
            "tip_backup": tip_backup,
            "tip_advanced": tip_advanced,
            "observation": observation,
            "review_question": review_question,
            "tip": tip,
        }

    recent_records = _collect_karl_recent_records(
        history_data, birth_date_str, phase_key, date_str, limit=7
    )
    recent_main_texts = [
        _normalize_text_compact(x.get("tip_main", "")) for x in recent_records
    ]
    daily_theme = _choose_karl_theme(phase_key, birth_date_str, date_obj, recent_records)
    local_plan = _build_local_karl_plan(
        date_obj=date_obj,
        birth_date_str=birth_date_str,
        phase_key=phase_key,
        theme=daily_theme,
        stage_task=stage_task,
        fine_focus=fine_focus,
        duration_text=duration_text,
    )

    generated_plan = {}
    try:
        generated_plan = _generate_karl_plan_from_api(
            date_obj=date_obj,
            age_text=phase,
            phase=phase,
            fine_phase=fine_phase,
            fine_focus=fine_focus,
            principle=principle,
            stage_task=stage_task,
            theme=daily_theme,
            duration_text=duration_text,
            local_plan=local_plan,
            recent_main_texts=recent_main_texts,
        )
    except Exception:
        generated_plan = {}

    plan = _merge_karl_plan(
        local_plan=local_plan,
        generated_plan=generated_plan,
        recent_main_texts=recent_main_texts,
        duration_text=duration_text,
    )
    tip_main = plan.get("tip_main", local_plan["tip_main"])
    tip_backup = plan.get("tip_backup", local_plan["tip_backup"])
    tip_advanced = plan.get("tip_advanced", local_plan["tip_advanced"])
    observation = plan.get("observation", local_plan["observation"])
    review_question = plan.get("review_question", local_plan["review_question"])
    tip = plan.get("tip", "")
    if not _karl_text_usable(tip, 20):
        tip = _compose_karl_tip(fine_focus, stage_task, daily_theme, plan)

    response = {
        "birth_date": birth_date_str,
        "age": age_text,
        "phase": phase,
        "phase_fine": fine_phase,
        "fine_focus": fine_focus,
        "principle": principle,
        "daily_theme": daily_theme,
        "tip_main": tip_main,
        "tip_backup": tip_backup,
        "tip_advanced": tip_advanced,
        "observation": observation,
        "review_question": review_question,
        "tip": tip,
    }
    _save_karl_tip_record(
        history_data,
        {
            "date": date_str,
            "birth_date": birth_date_str,
            "phase_key": phase_key,
            "theme": daily_theme,
            "tip_main": tip_main,
            "tip_backup": tip_backup,
            "tip_advanced": tip_advanced,
            "observation": observation,
            "review_question": review_question,
            "tip": tip,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        },
    )

    return response


def apply_local_calendar(data, date_str, date_obj):
    if isinstance(data, dict):
        lunar = data.setdefault("lunar", {})
        lunar.update(get_lunar_info(date_obj))
        jieqi = data.setdefault("jieqi", {})
        jieqi.update(get_jieqi_info(date_str, date_obj))
        if date_str in TRADITIONAL_FESTIVALS:
            data["festivals"] = [
                {"name": name, "type": "\u4f20\u7edf\u8282\u65e5"}
                for name in TRADITIONAL_FESTIVALS[date_str]
            ]
        if date_str in JIEQI_BY_DATE:
            data["jieqi"]["name"] = JIEQI_BY_DATE[date_str]
            data["jieqi"]["desc"] = JIEQI_DESC.get(
                JIEQI_BY_DATE[date_str], "\u6682\u65e0"
            )

    return data

def _sanitize_json_snippet(snippet):
    cleaned = snippet.strip()
    cleaned = (
        cleaned.replace("\u201c", "\"")
        .replace("\u201d", "\"")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    cleaned = re.sub(r'(?<=\{|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', r'"\1":', cleaned)
    cleaned = re.sub(r"'([^'\\\\]*(?:\\\\.[^'\\\\]*)*)'", r'"\1"', cleaned)
    return cleaned


def _escape_newlines_in_strings(text):
    out = []
    in_str = False
    escape = False
    for ch in text:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == "\"":
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch in ("\r", "\n"):
            out.append("\\n")
            continue
        if in_str and ch == "\t":
            out.append("\\t")
            continue
        out.append(ch)
    return "".join(out)


def _fix_missing_colons(text):
    out = []
    stack = []
    in_str = False
    escape = False
    last_sig = None
    just_closed_key = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "\"":
                in_str = False
                if stack and stack[-1] == "obj" and (last_sig in ("{", ",")):
                    just_closed_key = True
                last_sig = "string"
            i += 1
            continue

        if just_closed_key:
            if ch.isspace():
                out.append(ch)
                i += 1
                continue
            if ch != ":":
                out.append(":")
            just_closed_key = False

        if ch == "\"":
            in_str = True
            out.append(ch)
        elif ch == "{":
            stack.append("obj")
            out.append(ch)
            last_sig = "{"
        elif ch == "[":
            stack.append("arr")
            out.append(ch)
            last_sig = "["
        elif ch == "}":
            if stack:
                stack.pop()
            out.append(ch)
            last_sig = "}"
        elif ch == "]":
            if stack:
                stack.pop()
            out.append(ch)
            last_sig = "]"
        else:
            out.append(ch)
            if not ch.isspace():
                last_sig = ch
        i += 1
    return "".join(out)


def _extract_json_block(text):
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == "\"":
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return text[start:]


def extract_json(text):
    text = text.strip()
    snippet = _extract_json_block(text)
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        pass

    try:
        data = ast.literal_eval(snippet)
        if isinstance(data, (dict, list)):
            return data
    except (ValueError, SyntaxError):
        pass

    py_snippet = re.sub(r"\btrue\b", "True", snippet, flags=re.IGNORECASE)
    py_snippet = re.sub(r"\bfalse\b", "False", py_snippet, flags=re.IGNORECASE)
    py_snippet = re.sub(r"\bnull\b", "None", py_snippet, flags=re.IGNORECASE)
    try:
        data = ast.literal_eval(py_snippet)
        if isinstance(data, (dict, list)):
            return data
    except (ValueError, SyntaxError):
        pass

    fixed = _sanitize_json_snippet(snippet)
    fixed = _escape_newlines_in_strings(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    fixed = _fix_missing_colons(fixed)
    return json.loads(fixed)


def _deepseek_request(
    messages,
    model_id,
    timeout=None,
    retry_count=None,
    max_tokens=None,
):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": DEEPSEEK_CONFIG["temperature"],
        "max_tokens": (
            int(max_tokens)
            if max_tokens is not None
            else DEEPSEEK_CONFIG["max_tokens"]
        ),
        "top_p": DEEPSEEK_CONFIG["top_p"],
        "frequency_penalty": DEEPSEEK_CONFIG["frequency_penalty"],
        "presence_penalty": DEEPSEEK_CONFIG["presence_penalty"],
        "stream": DEEPSEEK_CONFIG["stream"],
    }
    # deepseek-flash 是推理模型：reasoning_content 与正文共用 max_tokens 预算，
    # 长 JSON 任务会被推理吃光额度导致 content 为空。本项目的任务是结构化提取，
    # 不需要推理，默认关闭（恢复原 deepseek-chat 的行为）。
    if DEEPSEEK_CONFIG.get("disable_thinking", True):
        payload["thinking"] = {"type": "disabled"}
    retryable_status = {408, 409, 429, 500, 502, 503, 504, 524}
    effective_retry_count = (
        int(retry_count)
        if retry_count is not None
        else int(DEEPSEEK_CONFIG.get("retry_count", 2))
    )
    max_attempts = max(1, effective_retry_count + 1)
    base_backoff = float(DEEPSEEK_CONFIG.get("retry_backoff", 2.0))
    max_backoff = float(DEEPSEEK_CONFIG.get("retry_backoff_max", 12.0))
    effective_timeout = (
        float(timeout) if timeout is not None else DEEPSEEK_CONFIG["timeout"]
    )
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                DEEPSEEK_CONFIG["api_url"],
                headers=headers,
                json=payload,
                timeout=effective_timeout,
            )
            if resp.status_code != 200:
                if resp.status_code in retryable_status and attempt < max_attempts:
                    last_error = RuntimeError(
                        f"DeepSeek error: {resp.status_code} {resp.text}"
                    )
                    raise last_error
                raise RuntimeError(f"DeepSeek error: {resp.status_code} {resp.text}")

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise RuntimeError("DeepSeek returned empty content")
            return content
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
        except json.JSONDecodeError as exc:
            last_error = exc
        except RuntimeError as exc:
            last_error = exc

        if attempt < max_attempts:
            delay = min(base_backoff * (2 ** (attempt - 1)), max_backoff)
            time.sleep(delay)

    raise RuntimeError(f"DeepSeek request failed after {max_attempts} attempts: {last_error}")


def repair_json_with_deepseek(raw_text):
    repair_model = get_model_id("推理模型")
    messages = [
        {
            "role": "system",
            "content": "你是JSON修复器。只输出严格 JSON，不要任何解释。",
        },
        {
            "role": "user",
            "content": "将下列内容修复为严格JSON，仅输出JSON：\n" + raw_text,
        },
    ]
    return _deepseek_request(messages, repair_model)


def normalize_schema(data, date_str, date_obj):
    weekday_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_map[date_obj.weekday()]
    week_of_year = date_obj.isocalendar()[1]
    quarter = f"Q{(date_obj.month - 1) // 3 + 1}"
    out = {
        "solar": {
            "date": date_str,
            "weekday": weekday,
            "week_of_year": week_of_year,
            "quarter": quarter,
            "moon_phase": "",
        },
        "lunar": {
            "year": "",
            "month": "",
            "day": "",
            "is_leap_month": False,
            "ganzhi_year": "",
            "ganzhi_month": "",
            "ganzhi_day": "",
            "zodiac": "",
        },
        "jieqi": {"name": "", "desc": ""},
        "huangli": {
            "yi": [],
            "ji": [],
            "chong_sha": "",
            "ji_shen": [],
            "xiong_shen": [],
            "ji_shi": [],
        },
        "festivals": [],
        "memorial_days": [],
        "history": {"china": [], "world": []},
        "people": {"births": [], "deaths": []},
        "culture": {"quote_cn": "", "quote_en": "", "work": [], "greeting": ""},
        "lifestyle": {"food": [], "tips": [], "clothing": ""},
        "daily_wellness": {"tip": "", "breakfast": "", "lunch": "", "dinner": ""},
        "wellness_tip": "",
        "ai_notice": "以上信息由AI生成，仅供参考",
    }
    if isinstance(data, dict):
        for key, value in data.items():
            if key in out and isinstance(out[key], dict) and isinstance(value, dict):
                out[key].update(value)
            elif key in out:
                out[key] = value
    out["huangli"]["yi"] = ensure_list(out["huangli"].get("yi"))
    out["huangli"]["ji"] = ensure_list(out["huangli"].get("ji"))
    out["huangli"]["ji_shen"] = ensure_list(out["huangli"].get("ji_shen"))
    out["huangli"]["xiong_shen"] = ensure_list(out["huangli"].get("xiong_shen"))
    out["huangli"]["ji_shi"] = ensure_list(out["huangli"].get("ji_shi"))
    out["festivals"] = ensure_list(out.get("festivals"))
    out["memorial_days"] = ensure_list(out.get("memorial_days"))
    out["history"]["china"] = ensure_list(out["history"].get("china"))
    out["history"]["world"] = ensure_list(out["history"].get("world"))
    out["people"]["births"] = ensure_list(out["people"].get("births"))
    out["people"]["deaths"] = ensure_list(out["people"].get("deaths"))
    out["culture"]["work"] = ensure_list(out["culture"].get("work"))
    out["lifestyle"]["food"] = ensure_list(out["lifestyle"].get("food"))
    out["lifestyle"]["tips"] = ensure_list(out["lifestyle"].get("tips"))
    out["lifestyle"]["clothing"] = _normalize_clothing_advice(
        out["lifestyle"].get("clothing")
    )
    out["daily_wellness"] = _normalize_daily_wellness(out.get("daily_wellness"))
    if not isinstance(out.get("wellness_tip"), str):
        out["wellness_tip"] = ""
    else:
        out["wellness_tip"] = out["wellness_tip"].strip()
    return out


def is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def is_placeholder_text(value):
    if not isinstance(value, str):
        return False
    return value.strip() in {"暂无", "不详", "未知"}


def list_only_placeholders(values):
    if not isinstance(values, list) or not values:
        return False
    for item in values:
        if not is_placeholder_text(item):
            return False
    return True


def named_items_only_placeholders(values):
    if not isinstance(values, list) or not values:
        return False
    for item in values:
        if not isinstance(item, dict):
            return False
        name = str(item.get("name", "")).strip()
        if name not in {"", "暂无"}:
            return False
    return True


def list_items_missing(items, keys):
    if not isinstance(items, list) or len(items) == 0:
        return True
    for item in items:
        if not isinstance(item, dict):
            return True
        for key in keys:
            if is_blank(item.get(key)):
                return True
    return False


def _parse_month_day_text(value):
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""

    m = re.fullmatch(r"(?:\d{4}\s*[-/.年]\s*)?(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:\s*日)?", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}-{day:02d}"

    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}-{day:02d}"

    m = re.search(r"(?:\d{4}\s*[-/.年]\s*)?(\d{1,2})\s*[-/.]\s*(\d{1,2})", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month:02d}-{day:02d}"

    return ""


def _extract_item_month_day(item, text_fields):
    if not isinstance(item, dict):
        return ""
    for key in ("month_day", "monthDay", "md", "date"):
        month_day = _parse_month_day_text(item.get(key))
        if month_day:
            return month_day
    for key in text_fields:
        month_day = _parse_month_day_text(item.get(key))
        if month_day:
            return month_day
    return ""


def _filter_date_matched_items(items, target_month_day, text_fields):
    parsed = []
    has_month_day = False

    for raw in ensure_list(items):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        month_day = _extract_item_month_day(item, text_fields)
        if month_day:
            has_month_day = True
        parsed.append((item, month_day))

    if not has_month_day:
        return [item for item, _ in parsed], False

    matched = []
    for item, month_day in parsed:
        if month_day == target_month_day:
            item["month_day"] = month_day
            matched.append(item)
    return matched, True


def ensure_history_people_date_alignment(data, date_obj):
    target_month_day = date_obj.strftime("%m-%d")
    history = data.setdefault("history", {})
    people = data.setdefault("people", {})

    china, china_checked = _filter_date_matched_items(
        history.get("china"), target_month_day, ("event",)
    )
    world, world_checked = _filter_date_matched_items(
        history.get("world"), target_month_day, ("event",)
    )
    births, births_checked = _filter_date_matched_items(
        people.get("births"), target_month_day, ("desc", "quote")
    )
    deaths, deaths_checked = _filter_date_matched_items(
        people.get("deaths"), target_month_day, ("desc", "quote")
    )

    if china_checked and not china:
        china = [{"year": "不详", "month_day": target_month_day, "event": "暂无"}]
    if world_checked and not world:
        world = [{"year": "不详", "month_day": target_month_day, "event": "暂无"}]
    if births_checked and not births:
        births = [
            {
                "year": "不详",
                "month_day": target_month_day,
                "name": "暂无",
                "desc": "暂无",
                "quote": "暂无",
            }
        ]
    if deaths_checked and not deaths:
        deaths = [
            {
                "year": "不详",
                "month_day": target_month_day,
                "name": "暂无",
                "desc": "暂无",
                "quote": "暂无",
            }
        ]

    history["china"] = china
    history["world"] = world
    people["births"] = births
    people["deaths"] = deaths
    return data


def collect_missing(data):
    missing = []
    solar = data.get("solar", {})
    lunar = data.get("lunar", {})
    jieqi = data.get("jieqi", {})
    huangli = data.get("huangli", {})
    history = data.get("history", {})
    people = data.get("people", {})
    culture = data.get("culture", {})
    lifestyle = data.get("lifestyle", {})

    if is_blank(solar.get("weekday")):
        missing.append("solar.weekday")
    if is_blank(solar.get("week_of_year")):
        missing.append("solar.week_of_year")
    if is_blank(solar.get("quarter")):
        missing.append("solar.quarter")
    if is_blank(solar.get("moon_phase")):
        missing.append("solar.moon_phase")

    if is_blank(lunar.get("year")):
        missing.append("lunar.year")
    if is_blank(lunar.get("month")):
        missing.append("lunar.month")
    if is_blank(lunar.get("day")):
        missing.append("lunar.day")
    if is_blank(lunar.get("ganzhi_year")):
        missing.append("lunar.ganzhi_year")
    if is_blank(lunar.get("ganzhi_month")):
        missing.append("lunar.ganzhi_month")
    if is_blank(lunar.get("ganzhi_day")):
        missing.append("lunar.ganzhi_day")
    if is_blank(lunar.get("zodiac")):
        missing.append("lunar.zodiac")

    if is_blank(jieqi.get("name")) or is_blank(jieqi.get("desc")):
        missing.append("jieqi")

    if is_blank(huangli.get("yi")) or list_only_placeholders(huangli.get("yi")):
        missing.append("huangli.yi")
    if is_blank(huangli.get("ji")) or list_only_placeholders(huangli.get("ji")):
        missing.append("huangli.ji")
    if is_blank(huangli.get("chong_sha")) or is_placeholder_text(
        huangli.get("chong_sha")
    ):
        missing.append("huangli.chong_sha")
    if is_blank(huangli.get("ji_shen")) or list_only_placeholders(
        huangli.get("ji_shen")
    ):
        missing.append("huangli.ji_shen")
    if is_blank(huangli.get("xiong_shen")) or list_only_placeholders(
        huangli.get("xiong_shen")
    ):
        missing.append("huangli.xiong_shen")
    if is_blank(huangli.get("ji_shi")) or list_only_placeholders(huangli.get("ji_shi")):
        missing.append("huangli.ji_shi")

    if is_blank(data.get("festivals")) or named_items_only_placeholders(
        data.get("festivals")
    ):
        missing.append("festivals")
    if is_blank(data.get("memorial_days")) or named_items_only_placeholders(
        data.get("memorial_days")
    ):
        missing.append("memorial_days")

    if list_items_missing(history.get("china"), ["year", "event"]):
        missing.append("history.china")
    if list_items_missing(history.get("world"), ["year", "event"]):
        missing.append("history.world")

    if list_items_missing(people.get("births"), ["year", "name", "desc", "quote"]):
        missing.append("people.births")
    if list_items_missing(people.get("deaths"), ["year", "name", "desc", "quote"]):
        missing.append("people.deaths")

    if is_blank(culture.get("quote_cn")):
        missing.append("culture.quote_cn")
    if is_blank(culture.get("quote_en")):
        missing.append("culture.quote_en")
    if is_blank(culture.get("work")):
        missing.append("culture.work")
    if is_blank(culture.get("greeting")):
        missing.append("culture.greeting")

    if is_blank(lifestyle.get("food")):
        missing.append("lifestyle.food")
    if is_blank(lifestyle.get("tips")):
        missing.append("lifestyle.tips")
    if is_blank(lifestyle.get("clothing")):
        missing.append("lifestyle.clothing")

    daily_wellness = _normalize_daily_wellness(data.get("daily_wellness"))
    for key in ("tip", "breakfast", "lunch", "dinner"):
        if not daily_wellness.get(key):
            missing.append(f"daily_wellness.{key}")
    if is_blank(data.get("wellness_tip")):
        missing.append("wellness_tip")

    if is_blank(data.get("ai_notice")):
        missing.append("ai_notice")

    return missing


def fill_missing_with_deepseek(date_str, data, missing):
    model_id = get_model_id("推理模型")
    month_day = date_str[5:]
    prompt = (
        "以下 JSON 有缺失字段，请补全并输出完整严格 JSON（双引号、无尾逗号）。"
        f"缺失字段：{', '.join(missing)}。"
        f"history 与 people 必须匹配月日 {month_day}，不得出现其他月日。"
        f"原始JSON：{json.dumps(data, ensure_ascii=False)}"
    )
    messages = [
        {"role": "system", "content": "你是JSON补全器，只输出严格 JSON。"},
        {"role": "user", "content": prompt},
    ]
    content = _deepseek_request(messages, model_id)
    return extract_json(content)


def fill_placeholders(data):
    solar = data.setdefault("solar", {})
    lunar = data.setdefault("lunar", {})
    jieqi = data.setdefault("jieqi", {})
    huangli = data.setdefault("huangli", {})
    history = data.setdefault("history", {})
    people = data.setdefault("people", {})
    culture = data.setdefault("culture", {})
    lifestyle = data.setdefault("lifestyle", {})

    for key in ("weekday", "week_of_year", "quarter", "moon_phase"):
        if is_blank(solar.get(key)):
            solar[key] = "暂无"

    for key in (
        "year",
        "month",
        "day",
        "ganzhi_year",
        "ganzhi_month",
        "ganzhi_day",
        "zodiac",
    ):
        if is_blank(lunar.get(key)):
            lunar[key] = "暂无"

    if is_blank(jieqi.get("name")):
        jieqi["name"] = "暂无"
    if is_blank(jieqi.get("desc")):
        jieqi["desc"] = "暂无"

    if is_blank(huangli.get("yi")) or list_only_placeholders(huangli.get("yi")):
        huangli["yi"] = ["祭祀", "祈福", "学习"]
    if is_blank(huangli.get("ji")) or list_only_placeholders(huangli.get("ji")):
        huangli["ji"] = ["动土", "争执", "冲动决策"]
    if is_blank(huangli.get("chong_sha")) or is_placeholder_text(huangli.get("chong_sha")):
        huangli["chong_sha"] = "冲煞信息请结合权威黄历核验"
    if is_blank(huangli.get("ji_shen")) or list_only_placeholders(huangli.get("ji_shen")):
        huangli["ji_shen"] = ["天德", "月德"]
    if is_blank(huangli.get("xiong_shen")) or list_only_placeholders(huangli.get("xiong_shen")):
        huangli["xiong_shen"] = ["天刑"]
    if is_blank(huangli.get("ji_shi")) or list_only_placeholders(huangli.get("ji_shi")):
        huangli["ji_shi"] = ["07:00-09:00", "13:00-15:00"]

    if is_blank(data.get("festivals")) or named_items_only_placeholders(data.get("festivals")):
        data["festivals"] = [{"name": "无全国性固定节日", "type": "说明"}]
    if is_blank(data.get("memorial_days")) or named_items_only_placeholders(
        data.get("memorial_days")
    ):
        data["memorial_days"] = [{"name": "无通用纪念日", "type": "说明"}]

    if list_items_missing(history.get("china"), ["year", "event"]):
        history["china"] = [{"year": "不详", "event": "暂无"}]
    if list_items_missing(history.get("world"), ["year", "event"]):
        history["world"] = [{"year": "不详", "event": "暂无"}]

    if list_items_missing(people.get("births"), ["year", "name", "desc", "quote"]):
        people["births"] = [{"year": "不详", "name": "暂无", "desc": "暂无", "quote": "暂无"}]
    if list_items_missing(people.get("deaths"), ["year", "name", "desc", "quote"]):
        people["deaths"] = [{"year": "不详", "name": "暂无", "desc": "暂无", "quote": "暂无"}]

    if is_blank(culture.get("quote_cn")):
        culture["quote_cn"] = "暂无"
    if is_blank(culture.get("quote_en")):
        culture["quote_en"] = "暂无"
    if is_blank(culture.get("work")):
        culture["work"] = ["暂无"]
    if is_blank(culture.get("greeting")):
        culture["greeting"] = "暂无"

    if is_blank(lifestyle.get("food")):
        lifestyle["food"] = ["暂无"]
    if is_blank(lifestyle.get("tips")):
        lifestyle["tips"] = ["暂无"]
    if is_blank(lifestyle.get("clothing")):
        lifestyle["clothing"] = "暂无"

    daily_wellness = _normalize_daily_wellness(data.get("daily_wellness"))
    for key in ("tip", "breakfast", "lunch", "dinner"):
        if not daily_wellness.get(key):
            daily_wellness[key] = "暂无"
    data["daily_wellness"] = daily_wellness

    if is_blank(data.get("wellness_tip")):
        data["wellness_tip"] = daily_wellness.get("tip", "暂无")

    if is_blank(data.get("ai_notice")):
        data["ai_notice"] = "以上信息由AI生成，仅供参考"

    return data


def ensure_complete(data, date_str, date_obj, allow_llm=True):
    data = ensure_history_people_date_alignment(data, date_obj)
    missing = collect_missing(data)
    if missing and allow_llm:
        try:
            filled = fill_missing_with_deepseek(date_str, data, missing)
            data = normalize_schema(filled, date_str, date_obj)
        except Exception:
            pass

    if collect_missing(data):
        data = fill_placeholders(data)
    data = ensure_history_people_date_alignment(data, date_obj)
    return data


def call_deepseek(date_str):
    month_day = date_str[5:]
    prompt = (
        PROMPT_TEMPLATE.replace("{{DATE}}", date_str).replace("{{MONTH_DAY}}", month_day)
    )

    messages = [
        {
            "role": "system",
            "content": "你是严谨的日历信息生成器，只输出严格 JSON。",
        },
        {"role": "user", "content": prompt},
    ]

    content = _deepseek_request(messages, DEEPSEEK_CONFIG["model"])
    try:
        return extract_json(content)
    except Exception:
        repaired = repair_json_with_deepseek(content)
        try:
            return extract_json(repaired)
        except Exception:
            regen_model = get_model_id("推理模型")
            regen_content = _deepseek_request(messages, regen_model)
            return extract_json(regen_content)


@app.route("/")
def index():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cities = list(WEATHER_CITIES.keys())
    default_city = WEATHER_CONFIG.get("default_city", "")
    return render_template(
        "index.html",
        today=today_str,
        cities=cities,
        default_city=default_city,
    )


@app.route("/api/weather")
def api_weather():
    try:
        city = request.args.get("city", "").strip()
        data = get_today_weather(city)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history")
def api_history():
    history = read_history()
    items = history.get("items", [])
    last_date = history.get("last_date", "")

    if items and not last_date:
        last_date = items[0].get("date", "")

    if not items:
        items = build_history_from_cache()
        if items:
            last_date = items[0].get("date", "")
            history = {"items": items, "last_date": last_date}
            write_history(history)

    if not last_date:
        last_date = find_latest_cache_date()
        if not items and last_date:
            items = [
                {
                    "date": last_date,
                    "model": CURRENT_MODEL,
                    "created_at": "",
                    "last_query_at": "",
                }
            ]

    return jsonify({"items": items, "last_date": last_date})


@app.route("/api/full")
def api_full():
    date_str = request.args.get("date", "").strip()
    refresh = request.args.get("refresh", "0") == "1"
    model_name = CURRENT_MODEL

    child_birth_str = request.args.get("child_birth", "").strip()
    child_birth_date = parse_child_birth_date(child_birth_str)
    if child_birth_str and not child_birth_date:
        return jsonify({"error": "\u513f\u7ae5\u751f\u65e5\u683c\u5f0f\u65e0\u6548\uff0c\u8bf7\u4f7f\u7528 YYYY-MM-DD\u3002"}), 400

    date_obj = parse_date(date_str)
    if not date_obj:
        return jsonify({"error": "\u65e5\u671f\u683c\u5f0f\u65e0\u6548\uff0c\u8bf7\u4f7f\u7528 YYYY-MM-DD\u3002"}), 400

    date_str = date_obj.strftime("%Y-%m-%d")

    cached = None
    if not refresh:
        cached = read_cache(date_str)

    if cached and "data" in cached:
        data = cached["data"]
        meta = {
            "cached": True,
            "model": cached.get("model", model_name),
            "created_at": cached.get("created_at", ""),
        }
        data = normalize_schema(data, date_str, date_obj)
        original_snapshot = json.dumps(data, ensure_ascii=False, sort_keys=True)
        data = ensure_complete(data, date_str, date_obj, allow_llm=False)
        data = apply_local_calendar(data, date_str, date_obj)
        data = ensure_lifestyle_clothing(data, date_obj, allow_llm=False)
        data = ensure_daily_wellness_data(data, date_obj, allow_llm=False)
        should_persist = (
            json.dumps(data, ensure_ascii=False, sort_keys=True) != original_snapshot
        )

        if should_persist:
            persisted_created_at = meta["created_at"] or datetime.datetime.now().isoformat(
                timespec="seconds"
            )
            write_cache(date_str, data, meta["model"], persisted_created_at)
            meta["created_at"] = persisted_created_at
        data["karl_witte_tip"] = get_karl_witte_tip(date_obj, child_birth_date)
        data["_meta"] = meta
        if meta["created_at"]:
            update_history(date_str, meta["model"], meta["created_at"])
        return jsonify(data)

    try:
        raw = call_deepseek(date_str)
        data = normalize_schema(raw, date_str, date_obj)
        data = ensure_complete(data, date_str, date_obj, allow_llm=False)
        data = apply_local_calendar(data, date_str, date_obj)
        data = ensure_lifestyle_clothing(data, date_obj, allow_llm=False)
        data = ensure_daily_wellness_data(data, date_obj, allow_llm=False)
        created_at = datetime.datetime.now().isoformat(timespec="seconds")
        write_cache(date_str, data, model_name, created_at)
        update_history(date_str, model_name, created_at)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    data["karl_witte_tip"] = get_karl_witte_tip(date_obj, child_birth_date)
    data["_meta"] = {
        "cached": False,
        "model": model_name,
        "created_at": created_at,
    }
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5091, debug=False)






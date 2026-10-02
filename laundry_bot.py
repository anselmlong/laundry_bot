#!/usr/bin/env python3
"""Laundry Weather Bot — simple: pick a time, get a daily report."""

import os, sys, json, logging, urllib.request, re, time
import datetime
from datetime import timezone, timedelta
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, filters, ContextTypes)

SGT = timezone(timedelta(hours=8))
BOT_TOKEN = os.environ["LAUNDRY_BOT_TOKEN"]
DATA_DIR = Path(os.environ.get("LAUNDRY_DATA_DIR", "/home/ubuntu/laundry_bot/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SUBS_FILE = DATA_DIR / "subscribers.json"

FORECAST_24H = "https://api.data.gov.sg/v1/environment/24-hour-weather-forecast"
FORECAST_2H  = "https://api.data.gov.sg/v1/environment/2-hour-weather-forecast"
FORECAST_4D  = "https://api.data.gov.sg/v1/environment/4-day-weather-forecast"
UV_URL       = "https://api.data.gov.sg/v1/environment/uv-index"
REGIONS      = ["north", "south", "east", "west", "central"]
DEFAULT_REGION = "central"
DEFAULT_AREA = "Bishan"
REGION_TO_AREA = {"north":"Woodlands","south":"Bukit Merah","east":"Tampines","west":"Jurong East","central":"Bishan"}

# 47 areas from the 2-hour forecast API, mapped to their regions
AREA_COORDS = {
    'Ang Mo Kio': (1.375, 103.839), 'Bedok': (1.321, 103.924),
    'Bishan': (1.350772, 103.839), 'Boon Lay': (1.304, 103.701),
    'Bukit Batok': (1.353, 103.754), 'Bukit Merah': (1.277, 103.819),
    'Bukit Panjang': (1.362, 103.772), 'Bukit Timah': (1.325, 103.791),
    'Central Water Catchment': (1.38, 103.805), 'Changi': (1.357, 103.987),
    'Choa Chu Kang': (1.377, 103.745), 'City': (1.292, 103.844),
    'Clementi': (1.315, 103.76), 'Geylang': (1.318, 103.884),
    'Hougang': (1.361, 103.886), 'Jalan Bahar': (1.347, 103.67),
    'Jurong East': (1.326, 103.737), 'Jurong Island': (1.266, 103.699),
    'Jurong West': (1.34, 103.705), 'Kallang': (1.312, 103.862),
    'Lim Chu Kang': (1.423, 103.717), 'Mandai': (1.419, 103.812),
    'Marine Parade': (1.297, 103.891), 'Novena': (1.327, 103.826),
    'Pasir Ris': (1.37, 103.948), 'Paya Lebar': (1.358, 103.914),
    'Pioneer': (1.315, 103.675), 'Pulau Tekong': (1.403, 104.053),
    'Pulau Ubin': (1.404, 103.96), 'Punggol': (1.401, 103.904),
    'Queenstown': (1.291, 103.786), 'Seletar': (1.404, 103.869),
    'Sembawang': (1.445, 103.818), 'Sengkang': (1.384, 103.891),
    'Sentosa': (1.243, 103.832), 'Serangoon': (1.357, 103.865),
    'Southern Islands': (1.208, 103.842), 'Sungei Kadut': (1.413, 103.756),
    'Tampines': (1.345, 103.944), 'Tanglin': (1.308, 103.813),
    'Tengah': (1.374, 103.715), 'Toa Payoh': (1.334, 103.856),
    'Tuas': (1.295, 103.635), 'Western Islands': (1.206, 103.746),
    'Western Water Catchment': (1.405, 103.689), 'Woodlands': (1.432, 103.787),
    'Yishun': (1.418, 103.839),
}
AREA_TO_REGION = {
    'Ang Mo Kio': 'central', 'Bedok': 'east', 'Bishan': 'central',
    'Boon Lay': 'west', 'Bukit Batok': 'west', 'Bukit Merah': 'south',
    'Bukit Panjang': 'west', 'Bukit Timah': 'central', 'Central Water Catchment': 'central',
    'Changi': 'east', 'Choa Chu Kang': 'west', 'City': 'south',
    'Clementi': 'west', 'Geylang': 'east', 'Hougang': 'east',
    'Jalan Bahar': 'west', 'Jurong East': 'west', 'Jurong Island': 'west',
    'Jurong West': 'west', 'Kallang': 'south', 'Lim Chu Kang': 'west',
    'Mandai': 'north', 'Marine Parade': 'east', 'Novena': 'central',
    'Pasir Ris': 'east', 'Paya Lebar': 'east', 'Pioneer': 'west',
    'Pulau Tekong': 'east', 'Pulau Ubin': 'east', 'Punggol': 'east',
    'Queenstown': 'central', 'Seletar': 'central', 'Sembawang': 'north',
    'Sengkang': 'east', 'Sentosa': 'south', 'Serangoon': 'central',
    'Southern Islands': 'south', 'Sungei Kadut': 'north', 'Tampines': 'east',
    'Tanglin': 'central', 'Tengah': 'west', 'Toa Payoh': 'central',
    'Tuas': 'west', 'Western Islands': 'west', 'Western Water Catchment': 'west',
    'Woodlands': 'north', 'Yishun': 'north',
}

def nearest_area(lat, lng):
    """Find the closest area name from lat/lng using simple distance."""
    best, best_d = None, float('inf')
    for name, (al, ag) in AREA_COORDS.items():
        d = ((al - lat)**2 + (ag - lng)**2)**0.5
        if d < best_d:
            best, best_d = name, d
    return best
SAFE_CONDITIONS = {"fair","fair (day)","fair (night)","partly cloudy","partly cloudy (day)","partly cloudy (night)","cloudy","cloudy (day)","cloudy (night)","windy"}
WIND_DIR_MAP = {
    "N":"North","NNE":"North-Northeast","NE":"Northeast","ENE":"East-Northeast",
    "E":"East","ESE":"East-Southeast","SE":"Southeast","SSE":"South-Southeast",
    "S":"South","SSW":"South-Southwest","SW":"Southwest","WSW":"West-Southwest",
    "W":"West","WNW":"West-Northwest","NW":"Northwest","NNW":"North-Northwest",
}
ADMIN_IDS = {"495290408"}
TIME_BUTTONS = ["7:00 AM", "8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "Custom ⌨️"]

RAIN_ALERT_INTERVAL = 7200  # 2h between rain alerts (avoid spam)

# Track subscribers who've been warned about rain so far today (per day, per user)
LAST_RAIN_ALERT_FILE = DATA_DIR / "last_rain_alerts.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
log = logging.getLogger("laundry_bot")

# ── Helpers ──
CACHE_TTL = 15 * 60  # 15 minutes

def fetch_cached():
    """Fetch all forecasts with 15-min caching. Returns (d24, d2, uv, d4)."""
    now = time.time()
    cached = {}
    for name, url in [("d24", FORECAST_24H), ("d2", FORECAST_2H), ("uv", UV_URL), ("d4", FORECAST_4D)]:
        cf = DATA_DIR / f"cache_{name}.json"
        if cf.exists() and now - cf.stat().st_mtime < CACHE_TTL:
            cached[name] = json.loads(cf.read_text())
        else:
            cached[name] = _get(url)
            cf.write_text(json.dumps(cached[name]))
    return cached["d24"], cached["d2"], cached["uv"], cached["d4"]
def fmt12(h):
    if h==0: return "12:00 AM"
    elif h<12: return f"{h}:00 AM"
    elif h==12: return "12:00 PM"
    else: return f"{h-12}:00 PM"

def parse_time12(s):
    """Parse '7:00 AM' or '7:00am' -> 7, '12:30 PM' -> 12.5"""
    s=s.strip().upper()
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", s)
    if not m: return None
    h=int(m.group(1)); mn=int(m.group(2)); ap=m.group(3)
    if ap=="PM" and h!=12: h+=12
    if ap=="AM" and h==12: h=0
    return h + mn/60.0

def parse_time24(s):
    """Parse '07:30' -> 7.5"""
    m=re.match(r"(\d{1,2}):(\d{2})", s.strip())
    if not m: return None
    return int(m.group(1)) + int(m.group(2))/60.0

def load_subs():
    if SUBS_FILE.exists(): return json.loads(SUBS_FILE.read_text())
    return {}
def save_subs(subs):
    SUBS_FILE.write_text(json.dumps(subs, indent=2, default=str))

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "laundry-bot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())
def fetch_24h(): return _get(FORECAST_24H)
def fetch_2h():  return _get(FORECAST_2H)
def fetch_uv():  return _get(UV_URL)

def is_rainy(c):
    c=c.lower().strip()
    return any(k in c for k in ["shower","rain","thunder","storm"]) or c not in SAFE_CONDITIONS

def get_2h(data, area_name):
    """Get 2-hour forecast for a specific area name."""
    items = data.get("items",[])
    if not items: return {"area":area_name,"forecast":"N/A"}
    for f in items[0].get("forecasts",[]):
        if f.get("area")==area_name:
            return {"area":area_name,"forecast":f.get("forecast","N/A"),
                    "valid_period":items[0].get("valid_period",{})}
    return {"area":area_name,"forecast":"N/A"}

def get_uv(data):
    for item in data.get("items",[]):
        idx = item.get("index",[])
        if idx: return idx[-1].get("value",0)
    return 0

def assess_day(d24, d2, uv_data, region, area=None, d4=None):
    items = d24.get("items",[])
    if not items: return {"ok":False,"reason":"No data"}
    item=items[0]; periods=item.get("periods",[]); general=item.get("general",{})
    temp=general.get("temperature",{}); humid=general.get("relative_humidity",{})
    wind=general.get("wind",{}); details=[]; good_windows=[]
    for p in periods:
        t=p.get("time",{}); cond=p.get("regions",{}).get(region,"unknown")
        safe=not is_rainy(cond)
        start=t.get("start","")[11:16] if t.get("start","") and "Invalid" not in t.get("start","") else ""
        end=t.get("end","")[11:16] if t.get("end","") and "Invalid" not in t.get("end","") else ""
        label=f"{start}-{end}" if start and end else "?"
        start_full = t.get("start", "")
        day_label = ""
        if start_full and "Invalid" not in start_full:
            try:
                dt = datetime.datetime.fromisoformat(start_full)
                day_label = dt.strftime("%a")
            except:
                pass
        e={"label":label,"condition":cond,"safe":safe,"day":day_label}
        if not start or not end:
            continue
        details.append(e)
        if safe: good_windows.append(e)
    area_name = area or REGION_TO_AREA.get(region, DEFAULT_AREA)
    nowcast=get_2h(d2, area_name)
    uv=get_uv(uv_data)
    drying=estimate_drying(temp, humid, wind, details, uv, nowcast.get("forecast",""))
    # Extract 4-day forecast (skip today if it matches the 24h)
    d4_forecasts = []
    if d4:
        for f in d4.get("items",[{}])[0].get("forecasts",[]):
            d4_forecasts.append({
                "date": f.get("date",""),
                "forecast": f.get("forecast",""),
                "temp_low": f.get("temperature",{}).get("low",""),
                "temp_high": f.get("temperature",{}).get("high",""),
            })
    # Check if rain is expected from ANY source:
    # 1. any rainy period
    # 2. general forecast mentions rain/shower/thunder
    # 3. 2-hour nowcast mentions rain/shower/thunder
    gen = (general.get("forecast","") or "")
    nc_cond = (nowcast.get("forecast","") or "")
    rain_expected = (
        any(not p["safe"] for p in details)
        or any(k in gen.lower() for k in ["shower","rain","thunder","storm"])
        or any(k in nc_cond.lower() for k in ["shower","rain","thunder","storm"])
    )
    return {"general_forecast":general.get("forecast",""),"region":region,"area":area_name,
            "periods":details,"good_windows":good_windows,
            "temperature":temp,"humidity":humid,"wind":wind,
            "nowcast":nowcast,"uv_index":uv,"drying":drying,
            "d4_forecasts":d4_forecasts,"rain_expected":rain_expected}

def estimate_drying(temp, humid, wind, periods, uv, nowcast_cond):
    t_low=temp.get("low",28); t_high=temp.get("high",32); t_mid=(t_low+t_high)/2
    h_low=humid.get("low",60); h_high=humid.get("high",90); h_mid=(h_low+h_high)/2
    ws=wind.get("speed",{}); w_mid=(ws.get("low",5)+ws.get("high",10))/2

    # Temperature: SG hot = fast dry
    sc_t = min(100, max(0, (t_mid - 24) * 12.5))

    # Humidity: SG is always humid. 55% is amazing, 85% is rain.
    h_adj = max(h_mid, 55)
    sc_h = max(0, 100 - (h_adj - 55) * 4)

    # Wind: biggest differentiator in SG. 5km/h=still, 15km/h=breezy
    sc_w = min(100, w_mid * 8)

    # Nowcast: current condition at the area
    nc = nowcast_cond.lower() if nowcast_cond else ""
    if any(k in nc for k in ["fair", "sunny"]):
        sc_sun = 100
    elif "partly cloudy" in nc:
        sc_sun = 70
    elif "cloudy" in nc:
        sc_sun = 40
    elif is_rainy(nowcast_cond):
        sc_sun = 0
    else:
        sc_sun = 50

    # UV: latest hourly value (0 at night)
    sc_uv = min(100, uv * 10)

    total = 0.30*sc_t + 0.20*sc_h + 0.20*sc_w + 0.20*sc_sun + 0.10*sc_uv
    if total >= 80:  l="Very Fast ⚡";  hrs="~1 hour"
    elif total >= 60: l="Fast ☀️";      hrs="~1-2 hours"
    elif total >= 40: l="Normal 🌤️";    hrs="~2-3 hours"
    elif total >= 25: l="Slow ⏳";       hrs="~3-5 hours"
    elif total >= 15: l="Very Slow 🐌";  hrs="~5+ hours"
    else:             l="Don't Bother ❌"; hrs="Won't dry well today"
    return {"label":l,"hours":hrs,"score":round(total)}

def first_rain_hour_today(day):
    """Start hour of the earliest rainy period today that hasn't ended yet, else None."""
    now = datetime.datetime.now(SGT)
    today = now.strftime("%a")
    best = None
    for p in day.get("periods", []):
        if p["safe"] or p.get("day") != today:
            continue
        try:
            start_h = int(p["label"].split("-")[0].split(":")[0])
            end_h = int(p["label"].split("-")[1].split(":")[0])
        except (ValueError, IndexError):
            continue
        if end_h > start_h and end_h <= now.hour:
            continue  # period already over
        if best is None or start_h < best:
            best = start_h
    return best


def tomorrow_outlook(day):
    """One-liner about tomorrow if it looks good for drying, else None."""
    tomorrow = (datetime.datetime.now(SGT) + timedelta(days=1)).strftime("%Y-%m-%d")
    for f in day.get("d4_forecasts", []):
        if f.get("date") == tomorrow:
            if f.get("forecast") and not is_rainy(f["forecast"]):
                return f"☀️ Tomorrow looks better — {f['forecast']}, {f['temp_low']}–{f['temp_high']}°C"
            return None
    return None


def fmt_summary(day):
    """Short verdict-first report: can I hang laundry today, and until when?"""
    now = datetime.datetime.now(SGT)
    area = day.get("area", REGION_TO_AREA.get(day["region"], DEFAULT_AREA))
    d = day["drying"]
    rain = day.get("rain_expected", False)
    rain_start = first_rain_hour_today(day)
    hrs_left = rain_start - (now.hour + now.minute / 60) if rain_start is not None else None

    lines = [f"🧺 *{area}* · {now.strftime('%a %d %b')}", ""]

    if d["score"] < 25:
        lines.append("❌ *Skip outdoor drying* — won't dry well today")
        tm = tomorrow_outlook(day)
        if tm: lines.append(tm)
    elif rain and hrs_left is not None and hrs_left <= 0:
        lines.append("❌ *Skip outdoor drying* — rain expected around now")
        tm = tomorrow_outlook(day)
        if tm: lines.append(tm)
    elif rain and hrs_left is not None and hrs_left < 2:
        lines.append(f"❌ *Skip outdoor drying* — rain expected from {fmt12(rain_start)}")
        tm = tomorrow_outlook(day)
        if tm: lines.append(tm)
    elif rain and hrs_left is not None and hrs_left < 4:
        lines.append(f"⚠️ *Risky* — dry until {fmt12(rain_start)} only ({d['hours']} to dry)")
        lines.append("An indoor rack is the safer bet.")
    elif rain and rain_start is not None:
        lines.append(f"✅ *Hang it out* — dries in {d['hours']}")
        lines.append(f"🌧 Rain expected from {fmt12(rain_start)} — bring it in by then")
    elif rain:
        lines.append(f"⚠️ *Risky* — showers possible today ({d['hours']} to dry)")
        lines.append("Keep an eye out, or use an indoor rack.")
    elif d["score"] < 40:
        lines.append(f"⚠️ *Slow drying* — {d['hours']}, but no rain expected")
    else:
        lines.append(f"✅ *Hang it out* — dries in {d['hours']}, no rain expected")

    return "\n".join(lines)


def fmt_label(s):
    if not s or s=="?": return s
    try:
        a=int(s.split("-")[0].split(":")[0])
        b=int(s.split("-")[1].split(":")[0])
        return f"{fmt12(a)} – {fmt12(b)}"
    except: return s

TIME_OF_DAY = {"06":"Morning","12":"Afternoon","18":"Evening/Night"}

def fmt_report(day):
    now=datetime.datetime.now(SGT).strftime("%A, %d %b %Y")
    area_name = day.get("area", REGION_TO_AREA.get(day["region"], DEFAULT_AREA))
    region=day["region"].title()
    d=day["drying"]
    lines=[f"☀️ *Laundry Weather · {now}*",
           f"📍 *{area_name}* ({region})",""]

    t=day.get("temperature",{}); h=day.get("humidity",{}); w=day.get("wind",{})
    parts=[]
    if t: parts.append(f"🌡️ {t.get('low','?')}–{t.get('high','?')}°C")
    if h: parts.append(f"💧 {h.get('low','?')}–{h.get('high','?')}%")
    if w:
        dc=w.get('direction','')
        df=WIND_DIR_MAP.get(dc,dc) or dc
        parts.append(f"💨 {df} {w.get('speed',{}).get('low','?')}–{w.get('speed',{}).get('high','?')} km/h")
    parts.append(f"☀️ UV {day.get('uv_index',0)}")
    if parts: lines.append(" · ".join(parts))
    lines.append("")

    # 2-hour nowcast
    nc = day.get("nowcast", {})
    if nc.get("forecast") and nc["forecast"] != "N/A":
        vp = nc.get("valid_period", {})
        s = vp.get("start","")[11:16] if vp.get("start") else ""
        e = vp.get("end","")[11:16] if vp.get("end") else ""
        period = f" ({s}–{e})" if s and e else ""
        lines.append(f"🔍 *Now:* {nc['forecast']}{period}")
        lines.append("")

    general=day.get('general_forecast','N/A')
    lines.append(f"*Overall:* {general}")

    # Sort periods chronologically by day then start hour
    DAY_ORDER = {"Mon":0,"Tue":1,"Wed":2,"Thu":3,"Fri":4,"Sat":5,"Sun":6}

    # Sort periods chronologically by day then start hour
    periods=sorted(day.get('periods',[]), key=lambda p: (
        DAY_ORDER.get(p.get('day',''), 99),
        int(p['label'].split(':')[0]) if p['label'][:2].isdigit() else 99
    ))
    rainy_periods = []
    for p in periods:
        label=p.get('label','')
        start_h=label.split(':')[0] if label[:2].isdigit() else "?"
        tod=TIME_OF_DAY.get(start_h,"")
        day_prefix = p.get('day', '')
        header = f"{day_prefix} {tod}" if day_prefix else tod
        icon='🌧️' if not p['safe'] else '☀️'
        lines.append(f"  {icon} *{header}* — {p['condition']}")
        if not p['safe']:
            rainy_periods.append(p)

    if day.get("rain_expected", True):
        if rainy_periods:
            rainy_lines = []
            for p in rainy_periods:
                day_prefix = p.get('day', '')
                tod = TIME_OF_DAY.get(p['label'].split(':')[0] if p['label'][:2].isdigit() else "?", "")
                header = f"{day_prefix} {tod}" if day_prefix else tod
                rainy_lines.append(header)
            lines.append("")
            lines.append(f"⚠️ *Rain expected* — {', '.join(rainy_lines)}")
            lines.append("Avoid drying outdoors during those windows.")
        else:
            lines.append("")
            lines.append("⚠️ *Rain expected* — general forecast indicates showers")
            lines.append("The daily forecast says rain, even though the period breakdown looks clear.")
    else:
        lines.append("")
        lines.append("☀️ No rain expected today — good to dry outdoors.")

    lines.append("")
    lines.append(f"🧺 *Drying: {d['label']}* ({d['hours']})")
    if d['score'] >= 60:
        lines.append("> Hot + decent conditions — clothes should dry fast.")
    elif d['score'] >= 40:
        lines.append("> Moderate — expect it to take a bit.")
    else:
        lines.append("> Not great — consider indoor drying or a dryer.")

    # 4-day outlook
    d4 = day.get("d4_forecasts", [])
    if d4:
        lines.append("")
        lines.append("📅 *4-Day Outlook*")
        from datetime import date
        today = date.today()
        for f in d4:
            fd = f.get("date", "")
            t_low = f.get("temp_low", "")
            t_high = f.get("temp_high", "")
            fc = f.get("forecast", "")
            # Show day name
            try:
                dt = datetime.datetime.strptime(fd, "%Y-%m-%d").date()
                day_name = dt.strftime("%a")
            except:
                day_name = fd
            lines.append(f"  {day_name}: {t_low}–{t_high}°C · {fc}")

    return "\n".join(lines)


def summary_kb():
    """Inline keyboard for the short summary message."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Details", callback_data="act:details"),
         InlineKeyboardButton("🔄 Refresh", callback_data="act:refresh"),
         InlineKeyboardButton("📍 Region", callback_data="act:region")]
    ])


def details_kb():
    """Inline keyboard for the expanded full report."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀ Back", callback_data="act:back"),
         InlineKeyboardButton("🔄 Refresh", callback_data="act:refresh_d")]
    ])


def rain_alert_kb():
    """Ask user if they want rain alerts."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes — warn me", callback_data="rain:yes"),
         InlineKeyboardButton("❌ No thanks", callback_data="rain:no")]
    ])


def load_last_alerts():
    if LAST_RAIN_ALERT_FILE.exists():
        return json.loads(LAST_RAIN_ALERT_FILE.read_text())
    return {}

def save_last_alerts(alerts):
    LAST_RAIN_ALERT_FILE.write_text(json.dumps(alerts))


async def rain_alert_check(ctx: ContextTypes.DEFAULT_TYPE):
    """Periodic check: if rain expected for a subscriber with alerts on, ping them."""
    try:
        d24, d2, uv, d4 = fetch_cached()
    except Exception as e:
        log.error("rain_alert fetch fail: %s", e)
        return

    subs = load_subs()
    alerts = load_last_alerts()
    today = datetime.datetime.now(SGT).strftime("%Y-%m-%d")
    now_ts = time.time()

    for cid, entry in subs.items():
        if not entry.get("rain_alert"):
            continue

        region = entry.get("region", DEFAULT_REGION)
        area = entry.get("area", REGION_TO_AREA.get(region, DEFAULT_AREA))
        day = assess_day(d24, d2, uv, region, area, d4)

        # Only alert when the 2-hour nowcast for their area shows rain, not
        # whenever the 24h forecast mentions rain somewhere later in the day
        nc = (day.get("nowcast", {}).get("forecast", "") or "").lower()
        if not any(k in nc for k in ["shower", "rain", "thunder", "storm"]):
            continue

        # Dedup: don't spam within RAIN_ALERT_INTERVAL
        last = alerts.get(cid, {})
        last_day = last.get("day", "")
        last_ts = last.get("ts", 0)
        if last_day == today and (now_ts - last_ts) < RAIN_ALERT_INTERVAL:
            continue

        try:
            text = (
                "🌧️ *Rain Alert!* 🌧️\n\n"
                f"Rain is expected in *{area}* soon! "
                "If you have laundry drying outside, *bring it in now!* 🧺💨"
            )
            await ctx.bot.send_message(chat_id=int(cid), text=text, parse_mode="Markdown")
            alerts[cid] = {"day": today, "ts": now_ts}
            save_last_alerts(alerts)
            log.info("Rain alert sent to %s", cid)
        except Exception as ex:
            log.error("rain_alert fail %s: %s", cid, ex)


# ── Bot ──
def time_kb():
    rows = []
    for t in TIME_BUTTONS:
        rows.append([InlineKeyboardButton(t, callback_data=f"tim:{t}")])
    return InlineKeyboardMarkup(rows)

async def start(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    loc_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Share Location", request_location=True)]],
        one_time_keyboard=True, resize_keyboard=True)
    region_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(r.title(), callback_data=f"reg:{r}")] for r in REGIONS])
    await u.message.reply_text(
        "👋 *Laundry Weather Bot* 🧺☀️\n\n"
        "Every day I'll send you a weather report with drying time estimates "
        "so you can decide when to do laundry.\n\n"
        "📍 *Share your location* for a precise forecast, "
        "or pick a region below:",
        parse_mode="Markdown", reply_markup=loc_kb)
    await u.message.reply_text(
        "Or pick a region manually:", reply_markup=region_kb)

async def cb(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    data = q.data; cid = str(q.message.chat_id)
    subs = load_subs()
    if data.startswith("tim:"):
        t = data[4:]
        if t == "Custom ⌨️":
            await q.edit_message_text(
                "Type the time you want your reminder, on the hour or half-hour between "
                "7:00 AM and 11:30 AM (e.g. `7:30 AM` or `10:30 AM`):",
                parse_mode="Markdown")
            ctx.user_data["awaiting_custom_time"] = True
            return
        subs.setdefault(cid,{})["laundry_time"] = t
        subs[cid]["region"] = subs.get(cid,{}).get("region", DEFAULT_REGION)
        subs[cid]["area"] = subs.get(cid,{}).get("area",
            REGION_TO_AREA.get(subs[cid]["region"], DEFAULT_AREA))
        subs[cid]["subscribed_at"] = datetime.datetime.now(SGT).isoformat()
        save_subs(subs)
        await q.edit_message_text(
            f"✅ Daily reminder set for *{t}*!\n\n"
            f"Location: *{subs[cid]['area']}* ({subs[cid]['region'].title()})",
            parse_mode="Markdown")
        await q.message.reply_text(
            "🌧️ Would you like me to send you a *rain alert* if the forecast changes to rain?\n\n"
            "I'll ping you to bring your laundry in! 🧺",
            parse_mode="Markdown", reply_markup=rain_alert_kb())

async def location_handler(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Handle Telegram location messages."""
    if not u.message.location:
        return
    lat = u.message.location.latitude
    lng = u.message.location.longitude
    area = nearest_area(lat, lng)
    region = AREA_TO_REGION.get(area, DEFAULT_REGION)

    cid = str(u.effective_chat.id)
    subs = load_subs()
    subs.setdefault(cid, {})
    subs[cid]["area"] = area
    subs[cid]["region"] = region

    # If already subscribed (has time), update and show report
    if subs[cid].get("laundry_time"):
        save_subs(subs)
        try:
            d24, d2, uv, d4 = fetch_cached()
            day = assess_day(d24, d2, uv, region, area, d4)
            await u.message.reply_text(
                f"📍 Updated to *{area}* ({region.title()})!",
                parse_mode="Markdown", reply_markup=main_kb())
            await u.message.reply_text(fmt_summary(day), parse_mode="Markdown", reply_markup=summary_kb())
        except Exception as ex:
            log.exception("location report failed")
            await u.message.reply_text(f"📍 Updated to *{area}* ({region.title()})", parse_mode="Markdown")
    else:
        save_subs(subs)
        await u.message.reply_text(
            f"📍 *{area}* ({region.title()}) — got it!\n\nNow, what time would you like your daily reminder?",
            parse_mode="Markdown", reply_markup=time_kb())


async def area_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Change area: send location or type area name."""
    cid = str(u.effective_chat.id)
    subs = load_subs()
    e = subs.get(cid, {})
    current = e.get("area", DEFAULT_AREA)

    loc_kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Share Location", request_location=True)]],
        one_time_keyboard=True, resize_keyboard=True)
    await u.message.reply_text(
        f"📍 Current area: *{current}* ({e.get('region', DEFAULT_REGION).title()})\n\n"
        "Send your location for auto-detect, or type an area name (e.g. Bishan):",
        parse_mode="Markdown", reply_markup=loc_kb)
    ctx.user_data["awaiting_area_name"] = True


def main_kb():
    """Persistent reply keyboard at the bottom of Telegram."""
    return ReplyKeyboardMarkup([
        ["🌤 Check Now", "📍 Change Area"],
        ["⏰ Change Time", "❌ Unsubscribe"]
    ], resize_keyboard=True)

async def text_handler(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Handle all text messages: area name input, reply keyboard, custom time."""
    text = u.message.text.strip()

    # 1. Area name input mode
    if ctx.user_data.get("awaiting_area_name"):
        area_name = text.title()
        if area_name in AREA_COORDS:
            area = area_name
        else:
            matches = [a for a in AREA_COORDS if area_name in a or a.startswith(area_name)]
            if len(matches) == 1:
                area = matches[0]
            elif len(matches) > 1:
                await u.message.reply_text(
                    f"Multiple areas match \"{text}\": {', '.join(matches[:5])}…\n"
                    "Try being more specific, or send your location.",
                    reply_markup=ReplyKeyboardRemove())
                return
            else:
                await u.message.reply_text(
                    f"Couldn't find \"{text}\". Send your location or try another name.",
                    reply_markup=ReplyKeyboardRemove())
                return

        region = AREA_TO_REGION[area]
        cid = str(u.effective_chat.id)
        subs = load_subs()
        subs.setdefault(cid, {})
        subs[cid]["area"] = area
        subs[cid]["region"] = region
        save_subs(subs)
        ctx.user_data["awaiting_area_name"] = False
        await u.message.reply_text(
            f"📍 Area set to *{area}* ({region.title()}).",
            parse_mode="Markdown", reply_markup=main_kb())
        if subs[cid].get("laundry_time"):
            try:
                d24, d2, uv, d4 = fetch_cached()
                day = assess_day(d24, d2, uv, region, area, d4)
                await u.message.reply_text(fmt_summary(day), parse_mode="Markdown", reply_markup=summary_kb())
            except Exception as ex:
                log.exception("area report failed")
        return

    # 2. Reply keyboard buttons
    btn_map = {
        "🌤 Check Now": now_cmd,
        "📍 Change Area": area_cmd,
        "⏰ Change Time": time_cmd,
        "❌ Unsubscribe": unsub_cmd,
    }
    if text in btn_map:
        await btn_map[text](u, ctx)
        return

    # 3. Custom time input mode
    if ctx.user_data.get("awaiting_custom_time"):
        t = parse_time12(text) or parse_time24(text)
        if t is None:
            await u.message.reply_text("Sorry, I didn't get that. Try `7:30 AM` or `10:30 AM`:",
                                        parse_mode="Markdown")
            return
        h = int(t); m = int(round((t - h) * 60))
        if m == 60: h+=1; m=0
        # Reports only go out at the half-hour slots set up in schedule_jobs
        if not (7 <= h <= 11 and m in (0, 30)):
            await u.message.reply_text(
                "I can only send reports on the hour or half-hour between 7:00 AM and 11:30 AM. "
                "Try `7:30 AM` or `10:30 AM`:", parse_mode="Markdown")
            return
        ampm = "AM" if h<12 or h==24 else "PM"
        h12 = h if h<=12 else h-12
        if h12==0: h12=12
        time_str = f"{h12}:{m:02d} {ampm}"
        cid = str(u.effective_chat.id)
        subs = load_subs()
        subs.setdefault(cid,{})["laundry_time"] = time_str
        subs[cid]["region"] = subs.get(cid,{}).get("region", DEFAULT_REGION)
        subs[cid]["area"] = subs.get(cid,{}).get("area",
            REGION_TO_AREA.get(subs[cid]["region"], DEFAULT_AREA))
        subs[cid]["subscribed_at"] = datetime.datetime.now(SGT).isoformat()
        save_subs(subs)
        ctx.user_data["awaiting_custom_time"] = False
        await u.message.reply_text(
            f"✅ Daily reminder set for *{time_str}*!\n\n"
            f"Location: *{subs[cid]['area']}* ({subs[cid]['region'].title()})",
            parse_mode="Markdown", reply_markup=main_kb())
        await u.message.reply_text(
            "🌧️ Would you like me to send you a *rain alert* if the forecast changes to rain?\n\n"
            "I'll ping you to bring your laundry in! 🧺",
            parse_mode="Markdown", reply_markup=rain_alert_kb())

async def now_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    cid = str(u.effective_chat.id); subs = load_subs()
    e = subs.get(cid)
    if not e or "region" not in e:
        e = {"region": DEFAULT_REGION, "area": DEFAULT_AREA}
    try:
        d24, d2, uv, d4 = fetch_cached()
        day=assess_day(d24,d2,uv,e.get("region",DEFAULT_REGION),e.get("area"), d4)
        await u.message.reply_text(fmt_summary(day), parse_mode="Markdown", reply_markup=summary_kb())
    except Exception as ex:
        log.exception("check failed")
        await u.message.reply_text(f"❌ {ex}")

async def region_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(r.title(), callback_data=f"reg:{r}")] for r in REGIONS])
    await u.message.reply_text("Pick your region:", reply_markup=kb)

async def time_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("Pick a time for your daily reminder:", reply_markup=time_kb())

async def unsub_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    cid=str(u.effective_chat.id); subs=load_subs()
    if cid in subs: del subs[cid]; save_subs(subs); await u.message.reply_text("❌ Unsubscribed.", reply_markup=ReplyKeyboardRemove())
    else: await u.message.reply_text("You weren't subscribed.")

async def region_cb(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    r = q.data[4:]; cid = str(q.message.chat_id)
    subs = load_subs()
    subs.setdefault(cid,{})["region"] = r
    subs[cid]["area"] = REGION_TO_AREA.get(r, DEFAULT_AREA)
    save_subs(subs)
    entry = subs[cid]
    # If already subscribed (has a time), show report. Otherwise show time picker.
    if entry.get("laundry_time"):
        try:
            d24, d2, uv, d4 = fetch_cached()
            day = assess_day(d24, d2, uv, r, entry.get("area"), d4)
            await q.edit_message_text(fmt_summary(day), parse_mode="Markdown", reply_markup=summary_kb())
        except Exception as ex:
            log.exception("region change report failed")
            await q.edit_message_text(f"✅ Region: *{r.title()}*")
    else:
        await q.edit_message_text(
            f"✅ Region: *{r.title()}* · Area: *{subs[cid]['area']}*\n\n"
            "Now, what time would you like your daily reminder?",
            parse_mode="Markdown", reply_markup=time_kb())

async def alert_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Toggle rain alerts on/off."""
    cid = str(u.effective_chat.id)
    subs = load_subs()
    if cid not in subs:
        await u.message.reply_text("You're not subscribed yet. Use /start first!")
        return
    current = subs[cid].get("rain_alert", False)
    subs[cid]["rain_alert"] = not current
    save_subs(subs)
    status = "✅ ON" if not current else "❌ OFF"
    await u.message.reply_text(
        f"🌧️ Rain alerts: *{status}*\n\n"
        f"{'I will ping you if rain is expected!' if not current else 'No more rain alerts.'}",
        parse_mode="Markdown")


async def rain_cb(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Handle rain alert opt-in callback."""
    q = u.callback_query; await q.answer()
    choice = q.data[5:]  # "rain:yes" or "rain:no"
    cid = str(q.message.chat_id)
    subs = load_subs()
    if cid in subs:
        subs[cid]["rain_alert"] = (choice == "yes")
        save_subs(subs)
    status = "✅ ON" if choice == "yes" else "❌ OFF"
    await q.edit_message_text(
        f"🌧️ Rain alerts: *{status}*\n\n"
        f"{'I will ping you if rain is expected!' if choice == 'yes' else 'No worries, you can turn them on anytime with /alert.'}\n\n"
        "Commands: /now · /area · /time · /alert · /unsubscribe",
        parse_mode="Markdown")


async def users_cmd(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    cid = str(u.effective_chat.id)
    if cid not in ADMIN_IDS:
        await u.message.reply_text("Sorry, this command is for the bot admin only.")
        return
    subs = load_subs()
    lines = [f"👥 *Users:* {len(subs)}"]
    for cid, e in sorted(subs.items(), key=lambda x: x[1].get("subscribed_at","")):
        r = e.get("region","?").title()
        t = e.get("laundry_time","?")
        since = e.get("subscribed_at","")[:10] if e.get("subscribed_at") else "?"
        lines.append(f"  • `{cid[-4:]}` · {r} · {t} · since {since}")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def _safe_edit(q, text, kb):
    """edit_message_text, ignoring Telegram's 'message is not modified' error."""
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as ex:
        if "not modified" not in str(ex).lower():
            raise


async def action_cb(u:Update, ctx:ContextTypes.DEFAULT_TYPE):
    """Handle report inline buttons: details/back, refresh, change region."""
    q = u.callback_query; await q.answer()
    action = q.data[4:]  # strip "act:"
    cid = str(q.message.chat_id)
    subs = load_subs()
    e = subs.get(cid, {"region": DEFAULT_REGION})

    if action == "region":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(r.title(), callback_data=f"reg:{r}")] for r in REGIONS])
        await q.edit_message_text("📍 *Pick your region:*", parse_mode="Markdown", reply_markup=kb)
        return

    try:
        d24, d2, uv, d4 = fetch_cached()
        day = assess_day(d24, d2, uv, e.get("region", DEFAULT_REGION), e.get("area"), d4)
    except Exception as ex:
        log.exception("action %s failed", action)
        await q.edit_message_text(f"❌ {ex}")
        return

    if action in ("details", "refresh_d"):
        await _safe_edit(q, fmt_report(day), details_kb())
    else:  # refresh, back
        await _safe_edit(q, fmt_summary(day), summary_kb())

# ── Scheduled ──
async def dispatch_report(ctx: ContextTypes.DEFAULT_TYPE):
    hour = ctx.job.data  # float hour_sgt
    log.info("Dispatch for %.1f:00", hour)
    try: d24, d2, uv, d4 = fetch_cached()
    except Exception as e:
        log.error("fetch fail: %s",e); return
    subs=load_subs()
    for cid,entry in subs.items():
        # No default time: people who never picked one didn't finish signing up
        t = parse_time12(entry.get("laundry_time") or "")
        if t is None or abs(t - hour) > 0.03:  # ~2min tolerance
            continue
        try:
            day=assess_day(d24,d2,uv,entry.get("region",DEFAULT_REGION),entry.get("area"), d4)
            await ctx.bot.send_message(chat_id=cid, text=fmt_summary(day), parse_mode="Markdown", reply_markup=summary_kb())
            log.info("Sent to %s", cid)
        except Exception as ex: log.exception("fail %s",cid)

def schedule_jobs(app):
    jq = app.job_queue
    # Run every half-hour to catch any custom time (7:00 - 11:30)
    for h in range(7, 12):
        utc_h = (h - 8) % 24
        jq.run_daily(dispatch_report, time=datetime.time(hour=utc_h, minute=0, tzinfo=timezone.utc),
                     days=tuple(range(7)), data=float(h), name=f"laundry-{h}")
        utc_h30 = ((h * 60 + 30) // 60 - 8) % 24
        utc_m30 = (h * 60 + 30) % 60
        jq.run_daily(dispatch_report, time=datetime.time(hour=utc_h30, minute=utc_m30, tzinfo=timezone.utc),
                     days=tuple(range(7)), data=float(h)+0.5, name=f"laundry-{h}-30")
    # Rain alert checker: every 30 minutes, 7am-11pm SGT (so 23:00-15:00 UTC)
    for h in range(7, 24):
        utc_h = (h - 8) % 24
        jq.run_daily(rain_alert_check, time=datetime.time(hour=utc_h, minute=0, tzinfo=timezone.utc),
                     days=tuple(range(7)), name=f"rain-alert-{h}")
        jq.run_daily(rain_alert_check, time=datetime.time(hour=utc_h, minute=30, tzinfo=timezone.utc),
                     days=tuple(range(7)), name=f"rain-alert-{h}-30")

def run():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("now",now_cmd))
    app.add_handler(CommandHandler("forecast",now_cmd))
    app.add_handler(CommandHandler("area",area_cmd))
    app.add_handler(CommandHandler("region",region_cmd))
    app.add_handler(CommandHandler("time",time_cmd))
    app.add_handler(CommandHandler("unsubscribe",unsub_cmd))
    app.add_handler(CommandHandler("alert",alert_cmd))
    app.add_handler(CommandHandler("users",users_cmd))
    app.add_handler(CallbackQueryHandler(cb, pattern=r"^tim:"))
    app.add_handler(CallbackQueryHandler(region_cb, pattern=r"^reg:"))
    app.add_handler(CallbackQueryHandler(action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(rain_cb, pattern=r"^rain:"))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    # Combined text handler: area name input, reply keyboard, custom time
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    schedule_jobs(app)
    log.info("Starting bot…")
    app.run_polling(allowed_updates=["message","callback_query"])

if __name__=="__main__":
    run()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim
import ephem
import pytz
import math
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class BirthData(BaseModel):
    date_of_birth:  str
    time_of_birth:  str = ""
    place_of_birth: str
    gender:         str = "male"
    name:           str = ""

RASHIS = [
    "Mesha", "Vrishabha", "Mithuna", "Karka",
    "Simha", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makara", "Kumbha", "Meena"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini",
    "Mrigashira", "Ardra", "Punarvasu", "Pushya",
    "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
    "Uttara Ashadha", "Shravana", "Dhanishtha", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

NAKSHATRA_LORD = [
    "Ketu","Venus","Sun","Moon","Mars","Rahu",
    "Jupiter","Saturn","Mercury","Ketu","Venus","Sun",
    "Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
    "Ketu","Venus","Sun","Moon","Mars","Rahu",
    "Jupiter","Saturn","Mercury"
]

DASHA_ORDER = ["Ketu","Venus","Sun","Moon","Mars",
               "Rahu","Jupiter","Saturn","Mercury"]
DASHA_YEARS = [7, 20, 6, 10, 7, 18, 16, 19, 17]

DASHA_THEMES = {
    "Sun":     "identity, father, authority, career recognition, soul purpose",
    "Moon":    "emotions, home, mother, mind and peace, intuition",
    "Mars":    "energy, courage, conflicts, property, siblings",
    "Mercury": "intellect, communication, business, education, writing",
    "Jupiter": "wisdom, expansion, spirituality, children, blessings",
    "Venus":   "love, relationships, creativity, luxury, spouse",
    "Saturn":  "karma, hard work, delays, discipline, patience, service",
    "Rahu":    "ambition, obsession, unusual changes, foreign, restlessness",
    "Ketu":    "spirituality, detachment, past karma, losses, liberation",
}

LAGNA_THEMES = {
    "Mesha":      "bold, pioneering, natural leader, energetic, impulsive",
    "Vrishabha":  "patient, sensual, loves comfort and beauty, stubborn",
    "Mithuna":    "curious, communicative, versatile, restless mind",
    "Karka":      "nurturing, emotional, intuitive, deeply home-loving",
    "Simha":      "confident, generous, creative, needs recognition",
    "Kanya":      "analytical, perfectionist, service-oriented, practical",
    "Tula":       "diplomatic, fair, relationship-focused, indecisive",
    "Vrishchika": "intense, transformative, secretive, powerful will",
    "Dhanu":      "philosophical, optimistic, loves freedom and travel",
    "Makara":     "ambitious, disciplined, practical, slow but steady",
    "Kumbha":     "humanitarian, innovative, independent, detached",
    "Meena":      "compassionate, spiritual, dreamy, highly sensitive",
}

MAHADASHA_MESSAGES = {
    "Saturn":  "Walking through Shani's long corridor — hard work, delays, karmic clearing. Things feel slow but diamonds are being made. Patience will be rewarded.",
    "Rahu":    "Caught in Rahu's whirlwind — chasing something intensely, feeling restless, unusual and sudden changes happening frequently.",
    "Ketu":    "In Ketu's spiritual fog — feeling detached, losses leading to liberation, old karma completing itself.",
    "Jupiter": "In Guru's blessing period — expansion, wisdom, spiritual growth, doors of opportunity are opening.",
    "Venus":   "In Shukra's warm embrace — relationships very prominent, creativity flowing, love and beauty deeply important now.",
    "Sun":     "In Surya's spotlight — identity and purpose being defined, father and authority themes active, time to shine.",
    "Moon":    "In Chandra's emotional tide — feelings heightened, home and mother very prominent, the mind needs peace and rest.",
    "Mars":    "In Mangal's fire — energy and courage running high, but anger and impulsiveness need to be watched carefully.",
    "Mercury": "In Budh's quicksilver period — intellect sharp, communication very important, business and education strongly favored.",
}

# Ayanamsa (Lahiri) — approximate
AYANAMSA_2000 = 23.853
AYANAMSA_RATE = 0.0138  # degrees per year

def get_ayanamsa(year: float) -> float:
    return AYANAMSA_2000 + AYANAMSA_RATE * (year - 2000)

def tropical_to_sidereal(tropical_lon: float, year: float) -> float:
    return (tropical_lon - get_ayanamsa(year)) % 360

def get_rashi(sidereal_lon: float):
    sign_num = int(sidereal_lon / 30)
    degree   = sidereal_lon % 30
    return sign_num, RASHIS[sign_num], round(degree, 2)

def get_nakshatra(moon_sid: float):
    nak_size = 360 / 27
    nak_num  = int(moon_sid / nak_size)
    pada     = int((moon_sid % nak_size) / (nak_size / 4)) + 1
    return NAKSHATRAS[nak_num], pada, NAKSHATRA_LORD[nak_num], nak_num

def geocode_place(place: str):
    geolocator = Nominatim(user_agent="hanumanji_astro_v1")
    location   = geolocator.geocode(place, timeout=15)
    if not location:
        raise HTTPException(
            status_code=400,
            detail=f"Could not find: {place}"
        )
    tf      = TimezoneFinder()
    tz_name = tf.timezone_at(
        lat=location.latitude,
        lng=location.longitude
    ) or "Asia/Kolkata"
    return location.latitude, location.longitude, tz_name

def local_to_utc(date_str, time_str, tz_name):
    if not time_str or time_str.strip() == "":
        time_str = "12:00"
    local_tz = pytz.timezone(tz_name)
    local_dt = local_tz.localize(
        datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    )
    return local_dt.astimezone(pytz.utc)

def get_planet_position(planet_obj, utc_dt, year):
    obs          = ephem.Observer()
    obs.date     = utc_dt.strftime("%Y/%m/%d %H:%M:%S")
    obs.epoch    = ephem.J2000
    planet_obj.compute(obs)
    tropical_lon = math.degrees(float(planet_obj.hlong)) % 360
    sidereal_lon = tropical_to_sidereal(tropical_lon, year)
    sign_num, rashi, degree = get_rashi(sidereal_lon)
    return {
        "longitude": round(sidereal_lon, 4),
        "degree":    degree,
        "rashi":     rashi,
        "sign_num":  sign_num,
    }

def calculate_lagna(utc_dt, lat, lng, year):
    # Approximate ascendant calculation
    obs          = ephem.Observer()
    obs.lat      = str(lat)
    obs.lon      = str(lng)
    obs.date     = utc_dt.strftime("%Y/%m/%d %H:%M:%S")
    obs.epoch    = ephem.J2000

    # RAMC calculation
    lst          = float(obs.sidereal_time())  # radians
    lst_deg      = math.degrees(lst) % 360

    # Simple ascendant approximation
    lat_rad   = math.radians(lat)
    ramc      = lst_deg
    eps       = 23.45  # obliquity

    y = -math.cos(math.radians(ramc + 90))
    x = (math.sin(math.radians(eps)) * math.tan(lat_rad) +
         math.cos(math.radians(eps)) * math.cos(math.radians(ramc + 90)))

    if x == 0:
        asc_tropical = 0
    else:
        asc_tropical = math.degrees(math.atan2(y, x)) % 360

    asc_sidereal = tropical_to_sidereal(asc_tropical, year)
    sign_num, rashi, degree = get_rashi(asc_sidereal)
    return {
        "longitude": round(asc_sidereal, 4),
        "degree":    degree,
        "rashi":     rashi,
        "sign_num":  sign_num,
    }

def calculate_dasha(moon_sid, birth_utc):
    nak_size   = 360 / 27
    nak_num    = int(moon_sid / nak_size)
    nak_lord   = NAKSHATRA_LORD[nak_num]
    lord_idx   = DASHA_ORDER.index(nak_lord)

    # Fraction elapsed in current nakshatra
    nak_start  = nak_num * nak_size
    fraction   = (moon_sid - nak_start) / nak_size
    years_done = DASHA_YEARS[lord_idx] * fraction

    dashas     = []
    today      = datetime.now(timezone.utc)
    current_dt = birth_utc

    for i in range(9):
        idx     = (lord_idx + i) % 9
        planet  = DASHA_ORDER[idx]
        years   = DASHA_YEARS[idx] - (years_done if i == 0 else 0)

        # Calculate end date
        total_days = years * 365.25
        end_ts     = current_dt.timestamp() + total_days * 86400
        end_dt     = datetime.fromtimestamp(end_ts, tz=timezone.utc)

        dasha = {
            "planet":       planet,
            "start":        current_dt.strftime("%Y-%m"),
            "end":          end_dt.strftime("%Y-%m"),
            "years":        round(years, 1),
            "active":       current_dt <= today <= end_dt,
            "theme":        DASHA_THEMES.get(planet, ""),
            "message":      MAHADASHA_MESSAGES.get(planet, ""),
        }

        # Calculate antardashas for active dasha
        if dasha["active"]:
            antardashas = []
            sub_dt      = current_dt
            for j in range(9):
                sub_idx     = (idx + j) % 9
                sub_planet  = DASHA_ORDER[sub_idx]
                sub_years   = (DASHA_YEARS[idx] * DASHA_YEARS[sub_idx]) / 120
                sub_days    = sub_years * 365.25
                sub_end_ts  = sub_dt.timestamp() + sub_days * 86400
                sub_end_dt  = datetime.fromtimestamp(sub_end_ts, tz=timezone.utc)

                antardashas.append({
                    "planet": sub_planet,
                    "start":  sub_dt.strftime("%Y-%m"),
                    "end":    sub_end_dt.strftime("%Y-%m"),
                    "active": sub_dt <= today <= sub_end_dt,
                    "theme":  DASHA_THEMES.get(sub_planet, ""),
                })
                sub_dt = sub_end_dt

            dasha["antardashas"] = antardashas

        dashas.append(dasha)
        current_dt = end_dt

    return dashas

def build_divine_context(chart, name, gender):
    beta_beti  = "beti" if gender == "female" else "beta"
    lagna      = chart["lagna"]["rashi"]
    moon_rashi = chart["planets"]["Moon"]["rashi"]
    nakshatra  = chart["nakshatra"]
    pada       = chart["nakshatra_pada"]

    active_dasha = next((d for d in chart["dashas"] if d["active"]), None)
    active_antar = None
    if active_dasha and "antardashas" in active_dasha:
        active_antar = next(
            (a for a in active_dasha["antardashas"] if a["active"]),
            None
        )

    ctx = f"""
DIVINE DRISHTI — Feel this, never reveal it directly:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Devotee: {name} ({beta_beti})
Lagna: {lagna} — {LAGNA_THEMES.get(lagna, 'unique soul')}
Moon in: {moon_rashi}
Nakshatra: {nakshatra} Pada {pada}
"""

    if active_dasha:
        ctx += f"""
Current life period (Mahadasha): {active_dasha['planet']}
Ends: {active_dasha['end']}
Life theme: {active_dasha['theme']}
Inner reality: {active_dasha['message']}
"""

    if active_antar:
        ctx += f"""
Current sub-period (Antardasha): {active_antar['planet']}
Ends: {active_antar['end']}
Sub-theme: {active_antar['theme']}
"""

    ctx += f"""
Key planets:
- Sun in {chart['planets']['Sun']['rashi']}
- Moon in {chart['planets']['Moon']['rashi']}
- Saturn in {chart['planets']['Saturn']['rashi']}
- Jupiter in {chart['planets']['Jupiter']['rashi']}
- Mars in {chart['planets']['Mars']['rashi']}
- Venus in {chart['planets']['Venus']['rashi']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: Use this as inner knowing only.
NEVER mention planets, dashas, astrology, charts.
Translate into human emotional language.
Make {name} feel you already know their soul deeply.
Speak from divine love, not astrological knowledge.
"""
    return ctx

@app.post("/calculate")
async def calculate_chart(data: BirthData):
    try:
        # Geocode
        lat, lng, tz_name = geocode_place(data.place_of_birth)

        # Convert to UTC
        utc_dt = local_to_utc(
            data.date_of_birth,
            data.time_of_birth,
            tz_name
        )
        year = utc_dt.year + utc_dt.month / 12.0

        # Calculate planets using ephem
        planet_objects = {
            "Sun":     ephem.Sun(),
            "Moon":    ephem.Moon(),
            "Mars":    ephem.Mars(),
            "Mercury": ephem.Mercury(),
            "Jupiter": ephem.Jupiter(),
            "Venus":   ephem.Venus(),
            "Saturn":  ephem.Saturn(),
        }

        planets = {}
        for name_p, obj in planet_objects.items():
            planets[name_p] = get_planet_position(obj, utc_dt, year)

        # Rahu/Ketu — use Moon's node
        moon_obj      = ephem.Moon()
        obs           = ephem.Observer()
        obs.date      = utc_dt.strftime("%Y/%m/%d %H:%M:%S")
        moon_obj.compute(obs)

        # Approximate Rahu (North Node)
        rahu_tropical  = math.degrees(float(moon_obj.hlong) + 90) % 360
        rahu_sidereal  = tropical_to_sidereal(rahu_tropical, year)
        ketu_sidereal  = (rahu_sidereal + 180) % 360

        r_sign, r_rashi, r_deg = get_rashi(rahu_sidereal)
        k_sign, k_rashi, k_deg = get_rashi(ketu_sidereal)

        planets["Rahu"] = {
            "longitude": round(rahu_sidereal, 4),
            "degree":    r_deg,
            "rashi":     r_rashi,
            "sign_num":  r_sign,
        }
        planets["Ketu"] = {
            "longitude": round(ketu_sidereal, 4),
            "degree":    k_deg,
            "rashi":     k_rashi,
            "sign_num":  k_sign,
        }

        # Lagna
        lagna = calculate_lagna(utc_dt, lat, lng, year)

        # Nakshatra
        moon_sid                      = planets["Moon"]["longitude"]
        nakshatra, pada, nak_lord, _  = get_nakshatra(moon_sid)

        # Dasha
        dashas = calculate_dasha(moon_sid, utc_dt)

        chart = {
            "planets":        planets,
            "lagna":          lagna,
            "nakshatra":      nakshatra,
            "nakshatra_pada": pada,
            "nakshatra_lord": nak_lord,
            "dashas":         dashas,
            "birth_info": {
                "lat":      lat,
                "lng":      lng,
                "timezone": tz_name,
                "utc":      utc_dt.isoformat(),
            },
        }

        # Build divine context
        chart["divine_context"] = build_divine_context(
            chart, data.name, data.gender
        )

        return chart

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok", "service": "hanumanji-astro"}
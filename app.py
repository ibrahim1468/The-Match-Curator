import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import requests 
import urllib3
import ssl
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

if "screen_width" not in st.session_state:
    st.session_state["screen_width"] = 1200

urllib3.disable_warnings()

# ====================== SESSION ======================
class TLSAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        # OP_LEGACY_SERVER_CONNECT only exists in Python 3.12+
        legacy = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        ctx.options |= legacy
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

def get_session():
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, */*",
    })
    session.mount("https://", TLSAdapter())
    return session


# ====================== LIVE SCORES ======================
LIVE_STATUSES = {"live", "inprogress", "in progress", "1h", "2h", "ht", "et", "p"}

TEAM_SHORT = {
    "Democratic Republic of the Congo": "DR Congo",
    "United States": "USA",
    "Korea Republic": "South Korea",
    "Trinidad and Tobago": "T&T",
    "Bosnia and Herzegovina": "Bosnia",
    "North Macedonia": "N. Macedonia",
}

def short_name(name):
    return TEAM_SHORT.get(name, name)

MINUTE_LABELS = {
    "live": "Live", "inprogress": "Live", "in progress": "Live",
    "1h": "1st Half", "2h": "2nd Half", "ht": "HT", "et": "ET", "p": "Pens",
}

def parse_scorers(raw):
    if not raw or raw == "null":
        return []
    try:
        import re
        names = re.findall(r'"([^"]+)"', str(raw))
        return names
    except:
        return []

@st.cache_data(ttl=45)
def get_live_scores():
    for attempt in range(2):
        try:
            session = get_session()
            r = session.get(
                "https://worldcup26.ir/get/games",
                timeout=30
            )
            print(f"Games API status: {r.status_code}")

            if r.status_code != 200:
                print(f"Failed: {r.text[:150]}")
                return {}

            live = {}
            for match in r.json().get("games", []):
                status = str(match.get("time_elapsed", "")).lower().strip()
                if status not in LIVE_STATUSES:
                    continue
                home = str(match.get("home_team_name_en", "")).strip()
                away = str(match.get("away_team_name_en", "")).strip()
                if not (home and away):
                    continue

                live[f"{home} vs {away}"] = {
                    "home": home,
                    "away": away,
                    "home_score": int(match.get("home_score") or 0),
                    "away_score": int(match.get("away_score") or 0),
                    "minute": str(match.get("time_elapsed", "")),
                    "status": status,
                    "group": str(match.get("group", "") or ""),
                    "home_scorers": parse_scorers(match.get("home_scorers")),
                    "away_scorers": parse_scorers(match.get("away_scorers")),
                }

            print(f"✅ Found {len(live)} live matches")
            return live

        except Exception as e:
            print(f"Live scores error (attempt {attempt + 1}): {e}")
    return {} 
        
st.set_page_config(
    page_title="The Match Curator",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st_autorefresh(interval=30_000, limit=None, key="live_score_refresh")

PKT = timezone(timedelta(hours=5))
TOURNAMENT_START = datetime(2026, 6, 12, 0, 0, tzinfo=PKT)
NOW = datetime.now(PKT)
PRE_TOURNAMENT = NOW < TOURNAMENT_START
SHOW_RANKINGS = NOW >= (TOURNAMENT_START - timedelta(hours=23, minutes=59))
TOURNAMENT_END = datetime(2026, 8, 20, 0, 0, tzinfo=PKT)  # Day after Final
POST_TOURNAMENT = NOW >= TOURNAMENT_END

# ── Today's Matches Section ────────────────────────────────────────────────────
now_pkt = NOW
today = NOW.date()
next_24h = now_pkt + timedelta(hours=24)

def resolve_team(slot, df):
    slot = str(slot).strip()
    if not slot or slot in ["TBD", "nan"] or slot.startswith(" "):
        return slot
    
    # Already a real team name — not a slot code
    if not (slot.startswith("W") or slot.startswith("L") or 
            (len(slot) == 2 and slot[0].isdigit())):
        return slot
    
    if slot.startswith("W"):
        try:
            match_id = int(slot[1:])
        except ValueError:
            return slot
        match_row = df[df["match_id"] == match_id]
        if len(match_row) > 0:
            winner = str(match_row.iloc[0]["winner"]).strip()
            if winner and winner not in ["", "nan", "0", "TBD"]:
                return winner

    if slot.startswith("L"):
        try:
            match_id = int(slot[1:])
        except ValueError:
            return slot
        match_row = df[df["match_id"] == match_id]
        if len(match_row) > 0:
            row = match_row.iloc[0]
            winner = str(row["winner"]).strip()
            if winner and winner not in ["", "nan", "0", "TBD", "Draw"]:
                return row["team1"] if winner == str(row["team2"]) else row["team2"]

    return slot  # unresolved — keep slot code for now

@st.cache_data(ttl=45)   # change to:
@st.cache_data(ttl=10)
def load_data():
    df = pd.read_csv("data/final/FIFA_WC_2026_data.csv", encoding="cp850")
    return df

df = load_data()

df["date"] = pd.to_datetime(df["date"], day = "First")

def get_match_datetime(row):
    try:
        parts = str(row["time"]).split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return datetime(
            row["date"].year, row["date"].month, row["date"].day,
            hour, minute, tzinfo=PKT
        )
    except:
        return datetime(row["date"].year, row["date"].month,
                       row["date"].day, 0, 0, tzinfo=PKT)

df["match_datetime"] = df.apply(get_match_datetime, axis=1)
def resolve_all(df):
    changed = True
    while changed:
        changed = False
        for col in ["team1", "team2"]:
            new = df[col].apply(lambda x: resolve_team(x, df))
            if not new.equals(df[col]):
                changed = True
                df[col] = new
    return df

df = resolve_all(df)

try:
    screen_width = int(st.query_params.get("sw", 1200))
except (ValueError, TypeError):
    screen_width = 1200

IS_MOBILE = screen_width < 768
IS_TABLET = 768 <= screen_width < 1024
    
TIMEZONE_OPTIONS = {
    'Africa/Abidjan': 0.0,
    'Africa/Accra': 0.0,
    'Africa/Addis_Ababa': 3.0,
    'Africa/Algiers': 1.0,
    'Africa/Asmara': 3.0,
    'Africa/Asmera': 3.0,
    'Africa/Bamako': 0.0,
    'Africa/Bangui': 1.0,
    'Africa/Banjul': 0.0,
    'Africa/Bissau': 0.0,
    'Africa/Blantyre': 2.0,
    'Africa/Brazzaville': 1.0,
    'Africa/Bujumbura': 2.0,
    'Africa/Cairo': 3.0,
    'Africa/Casablanca': 1.0,
    'Africa/Ceuta': 2.0,
    'Africa/Conakry': 0.0,
    'Africa/Dakar': 0.0,
    'Africa/Dar_es_Salaam': 3.0,
    'Africa/Djibouti': 3.0,
    'Africa/Douala': 1.0,
    'Africa/El_Aaiun': 1.0,
    'Africa/Freetown': 0.0,
    'Africa/Gaborone': 2.0,
    'Africa/Harare': 2.0,
    'Africa/Johannesburg': 2.0,
    'Africa/Juba': 2.0,
    'Africa/Kampala': 3.0,
    'Africa/Khartoum': 2.0,
    'Africa/Kigali': 2.0,
    'Africa/Kinshasa': 1.0,
    'Africa/Lagos': 1.0,
    'Africa/Libreville': 1.0,
    'Africa/Lome': 0.0,
    'Africa/Luanda': 1.0,
    'Africa/Lubumbashi': 2.0,
    'Africa/Lusaka': 2.0,
    'Africa/Malabo': 1.0,
    'Africa/Maputo': 2.0,
    'Africa/Maseru': 2.0,
    'Africa/Mbabane': 2.0,
    'Africa/Mogadishu': 3.0,
    'Africa/Monrovia': 0.0,
    'Africa/Nairobi': 3.0,
    'Africa/Ndjamena': 1.0,
    'Africa/Niamey': 1.0,
    'Africa/Nouakchott': 0.0,
    'Africa/Ouagadougou': 0.0,
    'Africa/Porto-Novo': 1.0,
    'Africa/Sao_Tome': 0.0,
    'Africa/Timbuktu': 0.0,
    'Africa/Tripoli': 2.0,
    'Africa/Tunis': 1.0,
    'Africa/Windhoek': 2.0,
    'America/Adak': -9.0,
    'America/Anchorage': -8.0,
    'America/Anguilla': -4.0,
    'America/Antigua': -4.0,
    'America/Araguaina': -3.0,
    'America/Argentina/Buenos_Aires': -3.0,
    'America/Argentina/Catamarca': -3.0,
    'America/Argentina/ComodRivadavia': -3.0,
    'America/Argentina/Cordoba': -3.0,
    'America/Argentina/Jujuy': -3.0,
    'America/Argentina/La_Rioja': -3.0,
    'America/Argentina/Mendoza': -3.0,
    'America/Argentina/Rio_Gallegos': -3.0,
    'America/Argentina/Salta': -3.0,
    'America/Argentina/San_Juan': -3.0,
    'America/Argentina/San_Luis': -3.0,
    'America/Argentina/Tucuman': -3.0,
    'America/Argentina/Ushuaia': -3.0,
    'America/Aruba': -4.0,
    'America/Asuncion': -3.0,
    'America/Atikokan': -5.0,
    'America/Atka': -9.0,
    'America/Bahia': -3.0,
    'America/Bahia_Banderas': -6.0,
    'America/Barbados': -4.0,
    'America/Belem': -3.0,
    'America/Belize': -6.0,
    'America/Blanc-Sablon': -4.0,
    'America/Boa_Vista': -4.0,
    'America/Bogota': -5.0,
    'America/Boise': -6.0,
    'America/Buenos_Aires': -3.0,
    'America/Cambridge_Bay': -6.0,
    'America/Campo_Grande': -4.0,
    'America/Cancun': -5.0,
    'America/Caracas': -4.0,
    'America/Catamarca': -3.0,
    'America/Cayenne': -3.0,
    'America/Cayman': -5.0,
    'America/Chicago': -5.0,
    'America/Chihuahua': -6.0,
    'America/Ciudad_Juarez': -6.0,
    'America/Coral_Harbour': -5.0,
    'America/Cordoba': -3.0,
    'America/Costa_Rica': -6.0,
    'America/Coyhaique': -3.0,
    'America/Creston': -7.0,
    'America/Cuiaba': -4.0,
    'America/Curacao': -4.0,
    'America/Danmarkshavn': 0.0,
    'America/Dawson': -7.0,
    'America/Dawson_Creek': -7.0,
    'America/Denver': -6.0,
    'America/Detroit': -4.0,
    'America/Dominica': -4.0,
    'America/Edmonton': -6.0,
    'America/Eirunepe': -5.0,
    'America/El_Salvador': -6.0,
    'America/Ensenada': -7.0,
    'America/Fort_Nelson': -7.0,
    'America/Fort_Wayne': -4.0,
    'America/Fortaleza': -3.0,
    'America/Glace_Bay': -3.0,
    'America/Godthab': -1.0,
    'America/Goose_Bay': -3.0,
    'America/Grand_Turk': -4.0,
    'America/Grenada': -4.0,
    'America/Guadeloupe': -4.0,
    'America/Guatemala': -6.0,
    'America/Guayaquil': -5.0,
    'America/Guyana': -4.0,
    'America/Halifax': -3.0,
    'America/Havana': -4.0,
    'America/Hermosillo': -7.0,
    'America/Indiana/Indianapolis': -4.0,
    'America/Indiana/Knox': -5.0,
    'America/Indiana/Marengo': -4.0,
    'America/Indiana/Petersburg': -4.0,
    'America/Indiana/Tell_City': -5.0,
    'America/Indiana/Vevay': -4.0,
    'America/Indiana/Vincennes': -4.0,
    'America/Indiana/Winamac': -4.0,
    'America/Indianapolis': -4.0,
    'America/Inuvik': -6.0,
    'America/Iqaluit': -4.0,
    'America/Jamaica': -5.0,
    'America/Jujuy': -3.0,
    'America/Juneau': -8.0,
    'America/Kentucky/Louisville': -4.0,
    'America/Kentucky/Monticello': -4.0,
    'America/Knox_IN': -5.0,
    'America/Kralendijk': -4.0,
    'America/La_Paz': -4.0,
    'America/Lima': -5.0,
    'America/Los_Angeles': -7.0,
    'America/Louisville': -4.0,
    'America/Lower_Princes': -4.0,
    'America/Maceio': -3.0,
    'America/Managua': -6.0,
    'America/Manaus': -4.0,
    'America/Marigot': -4.0,
    'America/Martinique': -4.0,
    'America/Matamoros': -5.0,
    'America/Mazatlan': -7.0,
    'America/Mendoza': -3.0,
    'America/Menominee': -5.0,
    'America/Merida': -6.0,
    'America/Metlakatla': -8.0,
    'America/Mexico_City': -6.0,
    'America/Miquelon': -2.0,
    'America/Moncton': -3.0,
    'America/Monterrey': -6.0,
    'America/Montevideo': -3.0,
    'America/Montreal': -4.0,
    'America/Montserrat': -4.0,
    'America/Nassau': -4.0,
    'America/New_York': -4.0,
    'America/Nipigon': -4.0,
    'America/Nome': -8.0,
    'America/Noronha': -2.0,
    'America/North_Dakota/Beulah': -5.0,
    'America/North_Dakota/Center': -5.0,
    'America/North_Dakota/New_Salem': -5.0,
    'America/Nuuk': -1.0,
    'America/Ojinaga': -5.0,
    'America/Panama': -5.0,
    'America/Pangnirtung': -4.0,
    'America/Paramaribo': -3.0,
    'America/Phoenix': -7.0,
    'America/Port-au-Prince': -4.0,
    'America/Port_of_Spain': -4.0,
    'America/Porto_Acre': -5.0,
    'America/Porto_Velho': -4.0,
    'America/Puerto_Rico': -4.0,
    'America/Punta_Arenas': -3.0,
    'America/Rainy_River': -5.0,
    'America/Rankin_Inlet': -5.0,
    'America/Recife': -3.0,
    'America/Regina': -6.0,
    'America/Resolute': -5.0,
    'America/Rio_Branco': -5.0,
    'America/Rosario': -3.0,
    'America/Santa_Isabel': -7.0,
    'America/Santarem': -3.0,
    'America/Santiago': -4.0,
    'America/Santo_Domingo': -4.0,
    'America/Sao_Paulo': -3.0,
    'America/Scoresbysund': -1.0,
    'America/Shiprock': -6.0,
    'America/Sitka': -8.0,
    'America/St_Barthelemy': -4.0,
    'America/St_Johns': -2.5,
    'America/St_Kitts': -4.0,
    'America/St_Lucia': -4.0,
    'America/St_Thomas': -4.0,
    'America/St_Vincent': -4.0,
    'America/Swift_Current': -6.0,
    'America/Tegucigalpa': -6.0,
    'America/Thule': -3.0,
    'America/Thunder_Bay': -4.0,
    'America/Tijuana': -7.0,
    'America/Toronto': -4.0,
    'America/Tortola': -4.0,
    'America/Vancouver': -7.0,
    'America/Virgin': -4.0,
    'America/Whitehorse': -7.0,
    'America/Winnipeg': -5.0,
    'America/Yakutat': -8.0,
    'America/Yellowknife': -6.0,
    'Antarctica/Casey': 8.0,
    'Antarctica/Davis': 7.0,
    'Antarctica/DumontDUrville': 10.0,
    'Antarctica/Macquarie': 10.0,
    'Antarctica/Mawson': 5.0,
    'Antarctica/McMurdo': 12.0,
    'Antarctica/Palmer': -3.0,
    'Antarctica/Rothera': -3.0,
    'Antarctica/South_Pole': 12.0,
    'Antarctica/Syowa': 3.0,
    'Antarctica/Troll': 2.0,
    'Antarctica/Vostok': 5.0,
    'Arctic/Longyearbyen': 2.0,
    'Asia/Aden': 3.0,
    'Asia/Almaty': 5.0,
    'Asia/Amman': 3.0,
    'Asia/Anadyr': 12.0,
    'Asia/Aqtau': 5.0,
    'Asia/Aqtobe': 5.0,
    'Asia/Ashgabat': 5.0,
    'Asia/Ashkhabad': 5.0,
    'Asia/Atyrau': 5.0,
    'Asia/Baghdad': 3.0,
    'Asia/Bahrain': 3.0,
    'Asia/Baku': 4.0,
    'Asia/Bangkok': 7.0,
    'Asia/Barnaul': 7.0,
    'Asia/Beirut': 3.0,
    'Asia/Bishkek': 6.0,
    'Asia/Brunei': 8.0,
    'Asia/Calcutta': 5.5,
    'Asia/Chita': 9.0,
    'Asia/Choibalsan': 8.0,
    'Asia/Chongqing': 8.0,
    'Asia/Chungking': 8.0,
    'Asia/Colombo': 5.5,
    'Asia/Dacca': 6.0,
    'Asia/Damascus': 3.0,
    'Asia/Dhaka': 6.0,
    'Asia/Dili': 9.0,
    'Asia/Dubai': 4.0,
    'Asia/Dushanbe': 5.0,
    'Asia/Famagusta': 3.0,
    'Asia/Gaza': 3.0,
    'Asia/Harbin': 8.0,
    'Asia/Hebron': 3.0,
    'Asia/Ho_Chi_Minh': 7.0,
    'Asia/Hong_Kong': 8.0,
    'Asia/Hovd': 7.0,
    'Asia/Irkutsk': 8.0,
    'Asia/Istanbul': 3.0,
    'Asia/Jakarta': 7.0,
    'Asia/Jayapura': 9.0,
    'Asia/Jerusalem': 3.0,
    'Asia/Kabul': 4.5,
    'Asia/Kamchatka': 12.0,
    'Asia/Karachi': 5.0,
    'Asia/Kashgar': 6.0,
    'Asia/Kathmandu': 5.75,
    'Asia/Katmandu': 5.75,
    'Asia/Khandyga': 9.0,
    'Asia/Kolkata': 5.5,
    'Asia/Krasnoyarsk': 7.0,
    'Asia/Kuala_Lumpur': 8.0,
    'Asia/Kuching': 8.0,
    'Asia/Kuwait': 3.0,
    'Asia/Macao': 8.0,
    'Asia/Macau': 8.0,
    'Asia/Magadan': 11.0,
    'Asia/Makassar': 8.0,
    'Asia/Manila': 8.0,
    'Asia/Muscat': 4.0,
    'Asia/Nicosia': 3.0,
    'Asia/Novokuznetsk': 7.0,
    'Asia/Novosibirsk': 7.0,
    'Asia/Omsk': 6.0,
    'Asia/Oral': 5.0,
    'Asia/Phnom_Penh': 7.0,
    'Asia/Pontianak': 7.0,
    'Asia/Pyongyang': 9.0,
    'Asia/Qatar': 3.0,
    'Asia/Qostanay': 5.0,
    'Asia/Qyzylorda': 5.0,
    'Asia/Rangoon': 6.5,
    'Asia/Riyadh': 3.0,
    'Asia/Saigon': 7.0,
    'Asia/Sakhalin': 11.0,
    'Asia/Samarkand': 5.0,
    'Asia/Seoul': 9.0,
    'Asia/Shanghai': 8.0,
    'Asia/Singapore': 8.0,
    'Asia/Srednekolymsk': 11.0,
    'Asia/Taipei': 8.0,
    'Asia/Tashkent': 5.0,
    'Asia/Tbilisi': 4.0,
    'Asia/Tehran': 3.5,
    'Asia/Tel_Aviv': 3.0,
    'Asia/Thimbu': 6.0,
    'Asia/Thimphu': 6.0,
    'Asia/Tokyo': 9.0,
    'Asia/Tomsk': 7.0,
    'Asia/Ujung_Pandang': 8.0,
    'Asia/Ulaanbaatar': 8.0,
    'Asia/Ulan_Bator': 8.0,
    'Asia/Urumqi': 6.0,
    'Asia/Ust-Nera': 10.0,
    'Asia/Vientiane': 7.0,
    'Asia/Vladivostok': 10.0,
    'Asia/Yakutsk': 9.0,
    'Asia/Yangon': 6.5,
    'Asia/Yekaterinburg': 5.0,
    'Asia/Yerevan': 4.0,
    'Atlantic/Azores': 0.0,
    'Atlantic/Bermuda': -3.0,
    'Atlantic/Canary': 1.0,
    'Atlantic/Cape_Verde': -1.0,
    'Atlantic/Faeroe': 1.0,
    'Atlantic/Faroe': 1.0,
    'Atlantic/Jan_Mayen': 2.0,
    'Atlantic/Madeira': 1.0,
    'Atlantic/Reykjavik': 0.0,
    'Atlantic/South_Georgia': -2.0,
    'Atlantic/St_Helena': 0.0,
    'Atlantic/Stanley': -3.0,
    'Australia/ACT': 10.0,
    'Australia/Adelaide': 9.5,
    'Australia/Brisbane': 10.0,
    'Australia/Broken_Hill': 9.5,
    'Australia/Canberra': 10.0,
    'Australia/Currie': 10.0,
    'Australia/Darwin': 9.5,
    'Australia/Eucla': 8.75,
    'Australia/Hobart': 10.0,
    'Australia/LHI': 10.5,
    'Australia/Lindeman': 10.0,
    'Australia/Lord_Howe': 10.5,
    'Australia/Melbourne': 10.0,
    'Australia/NSW': 10.0,
    'Australia/North': 9.5,
    'Australia/Perth': 8.0,
    'Australia/Queensland': 10.0,
    'Australia/South': 9.5,
    'Australia/Sydney': 10.0,
    'Australia/Tasmania': 10.0,
    'Australia/Victoria': 10.0,
    'Australia/West': 8.0,
    'Australia/Yancowinna': 9.5,
    'Brazil/Acre': -5.0,
    'Brazil/DeNoronha': -2.0,
    'Brazil/East': -3.0,
    'Brazil/West': -4.0,
    'CET': 2.0,
    'CST6CDT': -5.0,
    'Canada/Atlantic': -3.0,
    'Canada/Central': -5.0,
    'Canada/Eastern': -4.0,
    'Canada/Mountain': -6.0,
    'Canada/Newfoundland': -2.5,
    'Canada/Pacific': -7.0,
    'Canada/Saskatchewan': -6.0,
    'Canada/Yukon': -7.0,
    'Chile/Continental': -4.0,
    'Chile/EasterIsland': -6.0,
    'Cuba': -4.0,
    'EET': 3.0,
    'EST': -5.0,
    'EST5EDT': -4.0,
    'Egypt': 3.0,
    'Eire': 1.0,
    'Etc/GMT': 0.0,
    'Etc/GMT+0': 0.0,
    'Etc/GMT+1': -1.0,
    'Etc/GMT+10': -10.0,
    'Etc/GMT+11': -11.0,
    'Etc/GMT+12': -12.0,
    'Etc/GMT+2': -2.0,
    'Etc/GMT+3': -3.0,
    'Etc/GMT+4': -4.0,
    'Etc/GMT+5': -5.0,
    'Etc/GMT+6': -6.0,
    'Etc/GMT+7': -7.0,
    'Etc/GMT+8': -8.0,
    'Etc/GMT+9': -9.0,
    'Etc/GMT-0': 0.0,
    'Etc/GMT-1': 1.0,
    'Etc/GMT-10': 10.0,
    'Etc/GMT-11': 11.0,
    'Etc/GMT-12': 12.0,
    'Etc/GMT-13': 13.0,
    'Etc/GMT-14': 14.0,
    'Etc/GMT-2': 2.0,
    'Etc/GMT-3': 3.0,
    'Etc/GMT-4': 4.0,
    'Etc/GMT-5': 5.0,
    'Etc/GMT-6': 6.0,
    'Etc/GMT-7': 7.0,
    'Etc/GMT-8': 8.0,
    'Etc/GMT-9': 9.0,
    'Etc/GMT0': 0.0,
    'Etc/Greenwich': 0.0,
    'Etc/UCT': 0.0,
    'Etc/UTC': 0.0,
    'Etc/Universal': 0.0,
    'Etc/Zulu': 0.0,
    'Europe/Amsterdam': 2.0,
    'Europe/Andorra': 2.0,
    'Europe/Astrakhan': 4.0,
    'Europe/Athens': 3.0,
    'Europe/Belfast': 1.0,
    'Europe/Belgrade': 2.0,
    'Europe/Berlin': 2.0,
    'Europe/Bratislava': 2.0,
    'Europe/Brussels': 2.0,
    'Europe/Bucharest': 3.0,
    'Europe/Budapest': 2.0,
    'Europe/Busingen': 2.0,
    'Europe/Chisinau': 3.0,
    'Europe/Copenhagen': 2.0,
    'Europe/Dublin': 1.0,
    'Europe/Gibraltar': 2.0,
    'Europe/Guernsey': 1.0,
    'Europe/Helsinki': 3.0,
    'Europe/Isle_of_Man': 1.0,
    'Europe/Istanbul': 3.0,
    'Europe/Jersey': 1.0,
    'Europe/Kaliningrad': 2.0,
    'Europe/Kiev': 3.0,
    'Europe/Kirov': 3.0,
    'Europe/Kyiv': 3.0,
    'Europe/Lisbon': 1.0,
    'Europe/Ljubljana': 2.0,
    'Europe/London': 1.0,
    'Europe/Luxembourg': 2.0,
    'Europe/Madrid': 2.0,
    'Europe/Malta': 2.0,
    'Europe/Mariehamn': 3.0,
    'Europe/Minsk': 3.0,
    'Europe/Monaco': 2.0,
    'Europe/Moscow': 3.0,
    'Europe/Nicosia': 3.0,
    'Europe/Oslo': 2.0,
    'Europe/Paris': 2.0,
    'Europe/Podgorica': 2.0,
    'Europe/Prague': 2.0,
    'Europe/Riga': 3.0,
    'Europe/Rome': 2.0,
    'Europe/Samara': 4.0,
    'Europe/San_Marino': 2.0,
    'Europe/Sarajevo': 2.0,
    'Europe/Saratov': 4.0,
    'Europe/Simferopol': 3.0,
    'Europe/Skopje': 2.0,
    'Europe/Sofia': 3.0,
    'Europe/Stockholm': 2.0,
    'Europe/Tallinn': 3.0,
    'Europe/Tirane': 2.0,
    'Europe/Tiraspol': 3.0,
    'Europe/Ulyanovsk': 4.0,
    'Europe/Uzhgorod': 3.0,
    'Europe/Vaduz': 2.0,
    'Europe/Vatican': 2.0,
    'Europe/Vienna': 2.0,
    'Europe/Vilnius': 3.0,
    'Europe/Volgograd': 3.0,
    'Europe/Warsaw': 2.0,
    'Europe/Zagreb': 2.0,
    'Europe/Zaporozhye': 3.0,
    'Europe/Zurich': 2.0,
    'Factory': 0.0,
    'GB': 1.0,
    'GB-Eire': 1.0,
    'GMT': 0.0,
    'GMT+0': 0.0,
    'GMT-0': 0.0,
    'GMT0': 0.0,
    'Greenwich': 0.0,
    'HST': -10.0,
    'Hongkong': 8.0,
    'Iceland': 0.0,
    'Indian/Antananarivo': 3.0,
    'Indian/Chagos': 6.0,
    'Indian/Christmas': 7.0,
    'Indian/Cocos': 6.5,
    'Indian/Comoro': 3.0,
    'Indian/Kerguelen': 5.0,
    'Indian/Mahe': 4.0,
    'Indian/Maldives': 5.0,
    'Indian/Mauritius': 4.0,
    'Indian/Mayotte': 3.0,
    'Indian/Reunion': 4.0,
    'Iran': 3.5,
    'Israel': 3.0,
    'Jamaica': -5.0,
    'Japan': 9.0,
    'Kwajalein': 12.0,
    'Libya': 2.0,
    'MET': 2.0,
    'MST': -7.0,
    'MST7MDT': -6.0,
    'Mexico/BajaNorte': -7.0,
    'Mexico/BajaSur': -7.0,
    'Mexico/General': -6.0,
    'NZ': 12.0,
    'NZ-CHAT': 12.75,
    'Navajo': -6.0,
    'PRC': 8.0,
    'PST8PDT': -7.0,
    'Pacific/Apia': 13.0,
    'Pacific/Auckland': 12.0,
    'Pacific/Bougainville': 11.0,
    'Pacific/Chatham': 12.75,
    'Pacific/Chuuk': 10.0,
    'Pacific/Easter': -6.0,
    'Pacific/Efate': 11.0,
    'Pacific/Enderbury': 13.0,
    'Pacific/Fakaofo': 13.0,
    'Pacific/Fiji': 12.0,
    'Pacific/Funafuti': 12.0,
    'Pacific/Galapagos': -6.0,
    'Pacific/Gambier': -9.0,
    'Pacific/Guadalcanal': 11.0,
    'Pacific/Guam': 10.0,
    'Pacific/Honolulu': -10.0,
    'Pacific/Johnston': -10.0,
    'Pacific/Kanton': 13.0,
    'Pacific/Kiritimati': 14.0,
    'Pacific/Kosrae': 11.0,
    'Pacific/Kwajalein': 12.0,
    'Pacific/Majuro': 12.0,
    'Pacific/Marquesas': -9.5,
    'Pacific/Midway': -11.0,
    'Pacific/Nauru': 12.0,
    'Pacific/Niue': -11.0,
    'Pacific/Norfolk': 11.0,
    'Pacific/Noumea': 11.0,
    'Pacific/Pago_Pago': -11.0,
    'Pacific/Palau': 9.0,
    'Pacific/Pitcairn': -8.0,
    'Pacific/Pohnpei': 11.0,
    'Pacific/Ponape': 11.0,
    'Pacific/Port_Moresby': 10.0,
    'Pacific/Rarotonga': -10.0,
    'Pacific/Saipan': 10.0,
    'Pacific/Samoa': -11.0,
    'Pacific/Tahiti': -10.0,
    'Pacific/Tarawa': 12.0,
    'Pacific/Tongatapu': 13.0,
    'Pacific/Truk': 10.0,
    'Pacific/Wake': 12.0,
    'Pacific/Wallis': 12.0,
    'Pacific/Yap': 10.0,
    'Poland': 2.0,
    'Portugal': 1.0,
    'ROC': 8.0,
    'ROK': 9.0,
    'Singapore': 8.0,
    'Turkey': 3.0,
    'UCT': 0.0,
    'US/Alaska': -8.0,
    'US/Aleutian': -9.0,
    'US/Arizona': -7.0,
    'US/Central': -5.0,
    'US/East-Indiana': -4.0,
    'US/Eastern': -4.0,
    'US/Hawaii': -10.0,
    'US/Indiana-Starke': -5.0,
    'US/Michigan': -4.0,
    'US/Mountain': -6.0,
    'US/Pacific': -7.0,
    'US/Samoa': -11.0,
    'UTC': 0.0,
    'Universal': 0.0,
    'W-SU': 3.0,
    'WET': 1.0,
    'Zulu': 0.0,
    'localtime': 0.0
    }

def pkt_to_user(time_str, offset=5):
    try:
        parts = str(time_str).split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        
        # Convert PKT time to total minutes, then shift by offset difference
        pkt_total_minutes = hour * 60 + minute
        offset_diff_minutes = int((offset - 5) * 60)  # int handles half-hour zones
        local_total_minutes = pkt_total_minutes + offset_diff_minutes
        
        # Determine day shift BEFORE taking modulo
        if local_total_minutes < 0:
            day_shift = -1
        elif local_total_minutes >= 24 * 60:
            day_shift = 1
        else:
            day_shift = 0
        
        # Wrap to valid time
        local_total_minutes = local_total_minutes % (24 * 60)
        local_hour = local_total_minutes // 60
        local_min = local_total_minutes % 60
        
        return f"{local_hour:02d}:{local_min:02d}", day_shift
    except:
        return str(time_str), 0
    
from pathlib import Path
import base64

BASE_DIR = Path(__file__).resolve().parent
FLAG_DIR = BASE_DIR / "Assets" / "Flags"

def get_flag_b64(team_name, height=28):
    if not team_name or pd.isna(team_name):
        return ""
    team_name = str(team_name).strip()
    flag_path = FLAG_DIR / f"{team_name}.png"
    if not flag_path.exists():
        alt_name = team_name.replace(" ", "").replace(" and ", "&")
        flag_path = FLAG_DIR / f"{alt_name}.png"
    try:
        with open(flag_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return (
            f"<img src='data:image/png;base64,{data}' "
            f"style='height:{height}px; width:{int(height*1.5)}px; "
            f"object-fit:cover; border-radius:2px; vertical-align:middle;'>"
        )
    except Exception:
        return f"<span style='color:#666; font-size:0.9rem;'>[{team_name}]</span>"

KNOCKOUT_STAGES = ["round of 32", "round of 16", "quarter-final",
                   "semi-final", "play-off for third place", "final"]

CATEGORY_COLORS = {
    "Must Watch":     {"bg": "#d4f5d4", "border": "#2d8a2d", "badge_bg": "#2d8a2d", "badge_text": "#ffffff"},
    "Worth Watching": {"bg": "#d0f0f8", "border": "#0099bb", "badge_bg": "#0099bb", "badge_text": "#ffffff"},
    "Optional":       {"bg": "#feffd4", "border": "#cccc00", "badge_bg": "#cccc00", "badge_text": "#000000"},
    "Skip":           {"bg": "#fdd4d4", "border": "#cc0000", "badge_bg": "#cc0000", "badge_text": "#ffffff"},
    "TBD":            {"bg": "#f0f0f0", "border": "#999999", "badge_bg": "#999999", "badge_text": "#ffffff"},
}



# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow:wght@400;500;600&display=swap');

* { box-sizing: border-box; }

.stMarkdown { display: block; }
.stMarkdown p { display: block; }
            
.main { background-color: #0a0a0a; }
.block-container { padding: 2rem 3rem; max-width: 1200px; margin: auto; }

/* Header */
.curator-header {
    padding: 2.5rem 0 1.5rem 0;
    margin-top: 1rem;
}
            
.curator-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 4rem;
    color: #ffffff;
    letter-spacing: 0.15em;
    margin: 0;
    line-height: 1;
}
.curator-subtitle {
    font-family: 'Barlow', sans-serif;
    font-size: 1rem;
    color: #888888;
    margin-top: 0.4rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.countdown-box {
    display: inline-block;
    margin-top: 1.2rem;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 0.6rem 1.5rem;
    font-family: 'Barlow', sans-serif;
    font-size: 0.95rem;
    color: #cccccc;
    letter-spacing: 0.05em;
}
.countdown-highlight {
    color: #ffffff;
    font-weight: 600;
}

/* Match card */
.match-card {
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.2rem;
    border: 2px solid;
    position: relative;
    font-family: 'Barlow', sans-serif;
}
.badge {
    display: inline-block;
    padding: 0.25rem 0.9rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.8rem;
}
.match-teams {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2rem;
    letter-spacing: 0.08em;
    color: #111111;
    margin: 0.3rem 0;
    line-height: 1.1;
}
.match-meta {
    font-size: 0.85rem;
    color: #444444;
    margin-top: 0.4rem;
    font-weight: 500;
}
.match-reason {
    font-size: 0.9rem;
    color: #333333;
    margin-top: 0.8rem;
    line-height: 1.5;
    border-top: 1px solid rgba(0,0,0,0.1);
    padding-top: 0.8rem;
}
.favorite-star {
    position: absolute;
    top: 1rem;
    right: 1rem;
    font-size: 1.2rem;
}
.starts-in {
    display: inline-block;
    margin-top: 0.5rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: #1a7a1a;
    background: rgba(0,150,0,0.08);
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
}

/* Schedule table */
.schedule-header {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.8rem;
    color: #ffffff;
    letter-spacing: 0.1em;
    margin: 2rem 0 1rem 0;
    border-left: 4px solid #ffffff;
    padding-left: 0.8rem;
}
.filter-row {
    background: #1a1a1a;
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid #2a2a2a;
}

/* Divider */
.section-divider {
    border: none;
    border-top: 1px solid #222;
    margin: 2.5rem 0;
}
/* ── Scoreboard ── */
.sb-outer {
    margin-top: 1.2rem;
    font-family: 'Barlow', sans-serif;
}
.sb-card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 10px;
    display: inline-block;
    width: 100%;
}
.sb-live-bar {
    background: #c0392b;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    padding: 4px 14px;
}
.sb-live-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #fff;
    animation: sbpulse 1.2s infinite;
    flex-shrink: 0;
}
@keyframes sbpulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
.sb-live-text {
    font-size: 0.72rem;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}
.sb-minute {
    font-size: 0.72rem;
    color: rgba(255,255,255,0.75);
}
.sb-body {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    gap: 12px;
}
.sb-team {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    flex: 1;
}
.sb-team-name {
    font-size: 2rem;
    font-weight: 700;
    font-family: 'Bebas Neue', sans-serif;
}
.sb-score {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.2rem;
    color: #ffffff;
    letter-spacing: 0.05em;
    line-height: 1;
    text-align: center;
}
.sb-score-meta {
    font-size: 0.72rem;
    color: #666;
    text-align: center;
    margin-top: 2px;
}
.sb-scorers {
    display: flex;
    justify-content: space-between;
    padding: 0 20px 10px;
    border-top: 1px solid #222;
    padding-top: 8px;
    margin-top: 0;
    gap: 8px;
}
.sb-scorer-col {
    font-size: 0.72rem;
    color: #888;
    line-height: 1.6;
}
.sb-scorer-col.right { text-align: right; }
.sb-multi-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}
.sb-multi-grid .sb-body { padding: 10px 14px; }
.sb-multi-grid .sb-score { font-size: 1.7rem; }
.sb-multi-grid .sb-team-name { font-size: 0.75rem; }
.sb-next-bar {
    background: #111;
    border-bottom: 1px solid #222;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 5px 14px;
}
.sb-next-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: #888;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.sb-kickoff {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    flex: 1;
}
.sb-kickoff-time {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.8rem;
    color: #ffffff;
    line-height: 1;
}
.sb-kickoff-sub {
    font-size: 0.72rem;
    color: #666;
}
            

@media (max-width: 767px) {
    .block-container { padding: 1rem 1rem; }
    .curator-title   { font-size: 2.5rem; }
    .match-teams     { font-size: 1.4rem; }
    .sb-team-name    { font-size: 1.4rem; }
    .sb-score        { font-size: 1.6rem; }
    .sb-multi-grid   { grid-template-columns: 1fr; }
}
@media (max-width: 1023px) and (min-width: 768px) {
    .block-container { padding: 1.5rem 2rem; }
    .curator-title   { font-size: 3rem; }
}
            
</style>
""", unsafe_allow_html=True)

components.html("""
<script>
    (function() {
        const w = window.innerWidth;
        const url = new URL(window.parent.location.href);
        
        // Only update if not already set or stale
        if (url.searchParams.get('sw') != w) {
            url.searchParams.set('sw', w);
            window.parent.history.replaceState({}, '', url);
            // Trigger Streamlit rerun by dispatching storage event
            window.parent.dispatchEvent(new Event('popstate'));
        }
    })();
</script>
""", height=0)

# ── Timezone selector on main page ────────────────────────────────────────────
tz_col1, tz_col2, tz_col3 = st.columns([1, 2, 1])
with tz_col2:
    st.markdown("""
    <p style='font-family:Barlow,sans-serif; font-size:0.85rem; 
    color:#888; text-align:center; margin-bottom:0.3rem;'>
    🕐 Select your timezone to see match times correctly</p>
    """, unsafe_allow_html=True)
    selected_tz_label = st.selectbox(
        "Your Timezone",
        list(TIMEZONE_OPTIONS.keys()),
        index=list(TIMEZONE_OPTIONS.keys()).index("Asia/Karachi"),
        key="tz_selector",
        label_visibility="collapsed"
    )

user_tz_offset = TIMEZONE_OPTIONS[selected_tz_label]
USER_TZ_LABEL = selected_tz_label

def make_user_tz(offset):
    h = int(offset)
    m = int(round((offset - h) * 60))
    return timezone(timedelta(hours=h, minutes=m))

user_tz = make_user_tz(user_tz_offset)

def get_match_category(home, away):
    row = df[
        ((df["team1"] == home) & (df["team2"] == away)) |
        ((df["team1"] == away) & (df["team2"] == home))
    ]
    if len(row) > 0:
        return str(row.iloc[0]["category"])
    return "TBD"

def render_scoreboard_html():
    if PRE_TOURNAMENT:
        delta = TOURNAMENT_START - NOW
        total_seconds = int(delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return (
            f"<div class='countdown-box'>"
            f"Tournament begins in <span class='countdown-highlight'>"
            f"{days} days, {hours} hours</span></div>"
        )

    live_scores = get_live_scores()
    flex_dir = "column" if IS_MOBILE else "row"

    # ── LIVE matches ───────────────────────────────────────────────
    if live_scores:
        live_matches = list(live_scores.values())

        def single_card(m, compact=False):

            grid_class = "sb-multi-grid " if compact else ""
            scorers_html = ""
            if not compact:
                h_scorers = "<br>".join(m["home_scorers"]) if m["home_scorers"] else ""
                a_scorers = "<br>".join(m["away_scorers"]) if m["away_scorers"] else ""
                if h_scorers or a_scorers:
                    scorers_html = (
                        f"<div class='sb-scorers'>"
                        f"<div class='sb-scorer-col'>{h_scorers}</div>"
                        f"<div class='sb-scorer-col right'>{a_scorers}</div>"
                        f"</div>"
                    )
                    
            return (
                f"<div class='sb-card'>"
                f"<div class='sb-live-bar'>"
                f"<div class='sb-live-dot'></div>"
                f"<span class='sb-live-text'>{MINUTE_LABELS.get(m['status'], 'Live')}</span>"
                f"</div>"
                f"<div class='sb-body' style='flex-direction:{flex_dir};'>"
                f"<div class='sb-team'>"
                f"<span class='sb-team-name'>{short_name(m['home'])}</span>"
                f"</div>"
                f"<div class='sb-kickoff'>"
                f"<span class='sb-score'>{m['home_score']} – {m['away_score']}</span>"
                f"</div>"
                f"<div class='sb-team'>"
                f"<span class='sb-team-name'>{short_name(m['away'])}</span>"
                f"</div>"
                f"</div>"
                f"{scorers_html}"
                f"</div>"
            )

        if len(live_matches) == 1:
            return f"<div class='sb-outer'>{single_card(live_matches[0])}</div>"
        else:
            cards = "".join(single_card(m, compact=True) for m in live_matches)
            return f"<div class='sb-outer'><div class='sb-multi-grid'>{cards}</div></div>"


    # ── No live match — show next upcoming ─────────────────────────
    upcoming = df[
        (df["match_datetime"] > NOW) &
        (df["winner"].fillna("") == "") &
        (df["category"] != "TBD")
    ].sort_values("match_datetime")

    if len(upcoming) == 0:
        return "<div class='countdown-box'>🏆 <span class='countdown-highlight'>Tournament Complete</span></div>"

    next_match = upcoming.iloc[0]
    st.session_state["scoreboard_match_id"] = int(next_match["match_id"])
    cat = str(next_match.get("category", "TBD"))
    colors = CATEGORY_COLORS.get(cat, CATEGORY_COLORS["TBD"])
    category_banner = (
        f"<div style='background:{colors['badge_bg']}; color:{colors['badge_text']}; "
        f"text-align:center; padding:0.4rem; border-radius:0 0 10px 10px; "
        f"font-size:0.72rem; font-weight:700; letter-spacing:0.12em; "
        f"text-transform:uppercase;'>{cat}</div>"
    )
    delta = next_match["match_datetime"] - NOW
    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    if hours == 0:
        time_str = f"{minutes}m"
    elif hours < 24:
        time_str = f"{hours}h {minutes}m"
    else:
        days = hours // 24
        time_str = f"{days}d"

    local_dt = next_match["match_datetime"].astimezone(user_tz)
    kickoff_time = local_dt.strftime("%H:%M")
    t1 = short_name(str(next_match["team1"]))
    t2 = short_name(str(next_match["team2"]))

    return (
        f"<div class='sb-outer'>"
        f"<div class='sb-card'>"
        f"<div class='sb-next-bar'>"
        f"⏱ <span class='sb-next-label'>Next match · in {time_str}</span>"
        f"</div>"
        f"<div class='sb-body'>"
        f"<div class='sb-team'><span class='sb-team-name'>{t1}</span></div>"
        f"<div class='sb-kickoff'>"
        f"<span class='sb-kickoff-time'>{kickoff_time}</span>"
        f"<span class='sb-kickoff-sub'>{USER_TZ_LABEL}</span>"
        f"</div>"
        f"<div class='sb-team'><span class='sb-team-name'>{t2}</span></div>"
        f"</div>"
        f"{category_banner}"
        f"</div>"
        f"</div>"
    )

# ── Header ────────────────────────────────────────────────────────
st.markdown(f"""
<div class='curator-header'>
    <p class='curator-title'>The Match Curator</p>
    <p class='curator-subtitle'>Your FIFA World Cup 2026 Watching Guide</p>
    {render_scoreboard_html()}
</div>
""", unsafe_allow_html=True)

_all_team_names = set(df["team1"].unique()) | set(df["team2"].unique())
_slot_prefixes = ("W", "L", "1A","1B","1C","1D","1E","1F","1G","1H",
                  "1I","1J","1K","1L","2A","2B","2C","2D","2E",
                  "2F","2G","2H","2I","2J","2K","2L","3","TBD")
all_teams = sorted([t for t in _all_team_names 
                    if not str(t).startswith(_slot_prefixes) 
                    and str(t) not in ["TBD", "nan", ""]])

# Default values
favorite_team = None
selected_categories = ["Must Watch", "Worth Watching", "Optional"]

# ── Sidebar ────────────────────────────────────────────────────────────────────
# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <p style='font-family:Bebas Neue,sans-serif; font-size:1.8rem; 
    color:#ffffff; letter-spacing:0.1em; margin-bottom:0;'>
    The Match Curator</p>
    <p style='font-family:Barlow,sans-serif; font-size:0.8rem; 
    color:#888; margin-top:0;'>FIFA World Cup 2026</p>
    <hr style='border-color:#333; margin:0.8rem 0;'>
    """, unsafe_allow_html=True)

    # Favorite Team
    favorite_team_select = st.selectbox(
        "⭐ My Team",
        ["None"] + all_teams,
        index=0
    )
    favorite_team = None if favorite_team_select == "None" else favorite_team_select

    st.markdown("<hr style='border-color:#333; margin:1.2rem 0;'>", unsafe_allow_html=True)

    # ── All Filters in Sidebar ─────────────────────────────────────
    st.markdown("<p style='font-family:Barlow,sans-serif; font-size:0.9rem; color:#aaa; margin-bottom:0.5rem;'>Filters</p>", unsafe_allow_html=True)

    # Category Filter
    st.markdown("**Category**")
    show_must = st.checkbox("🟢 Must Watch", value=True, key="cb_must")
    show_worth = st.checkbox("🔵 Worth Watching", value=True, key="cb_worth")
    show_optional = st.checkbox("🟡 Optional", value=True, key="cb_optional")
    show_skip = st.checkbox("🔴 Skip", value=False, key="cb_skip")

    selected_categories = []
    if show_must: selected_categories.append("Must Watch")
    if show_worth: selected_categories.append("Worth Watching")
    if show_optional: selected_categories.append("Optional")
    if show_skip: selected_categories.append("Skip")

    # Team Filter
    st.markdown("**Team**")
    schedule_team = st.selectbox(
        "Filter by Team",
        ["All Teams"] + all_teams,
        key="sidebar_team_filter"
    )

    # Stage Filter
    st.markdown("**Stage**")
    all_stages = ["All Stages"] + sorted(df["stage"].dropna().unique().tolist())
    schedule_stage = st.selectbox(
        "Filter by Stage",
        all_stages,
        key="sidebar_stage_filter"
    )

    st.markdown("<hr style='border-color:#333; margin:1.5rem 0;'>", unsafe_allow_html=True)

    # Share
    st.link_button("🔗 Share This App", "https://thematchcurator.streamlit.app", use_container_width=True)
# ── Helper functions ───────────────────────────────────────────────────────────
def parse_reason(reason):
    if pd.isna(reason) or reason == "":
        return "No preview available.", ""
    parts = str(reason).split("|")
    short = parts[0].strip()
    extended = parts[1].strip() if len(parts) > 1 else ""
    return short, extended

def get_surprise_match():
    pool = df[
        (df["category"].isin(["Must Watch", "Worth Watching"])) &
        (df["category"] != "TBD") &
        (df["match_datetime"] >= NOW) &          # only future/ongoing
        (df["winner"].fillna("") == "")          # not yet played
    ]
    if len(pool) == 0:
        return None
    return pool.sample(1).iloc[0]

def safe_int(val):
    try:
        v = float(val)
        return 0 if pd.isna(v) else int(v)
    except:
        return 0

def build_group_standings(df):
    group_df = df[df["stage"] == "group stage"].copy()
    groups = sorted(group_df["group"].dropna().unique())
    standings = {}

    for group in groups:
        g_matches = group_df[group_df["group"] == group]
        teams = {}

        for _, row in g_matches.iterrows():
            for team, pts_col, gf_col, ga_col, gd_col, rank_col in [
                (row["team1"], "points_team1", "GF_team1", "GA_team1", "GD_team1", "group_rank_team1"),
                (row["team2"], "points_team2", "GF_team2", "GA_team2", "GD_team2", "group_rank_team2"),
            ]:
                if team not in teams:
                    teams[team] = {
                        "points": safe_int(row[pts_col]),
                        "gf":     safe_int(row[gf_col]),
                        "ga":     safe_int(row[ga_col]),
                        "gd":     safe_int(row[gd_col]),
                        "rank":   safe_int(row[rank_col]),
                        "played": 0,
                        "w": 0, "d": 0, "l": 0
                    }

        # Count W/D/L/played directly from match results — read only, no formula
        for _, row in g_matches.iterrows():
            winner = str(row["winner"]).strip()
            if winner in ["", "nan", "0", "TBD"]:
                continue
            t1, t2 = str(row["team1"]), str(row["team2"])
            if t1 in teams: teams[t1]["played"] += 1
            if t2 in teams: teams[t2]["played"] += 1
            if winner == "Draw":
                if t1 in teams: teams[t1]["d"] += 1
                if t2 in teams: teams[t2]["d"] += 1
            elif winner == t1:
                if t1 in teams: teams[t1]["w"] += 1
                if t2 in teams: teams[t2]["l"] += 1
            elif winner == t2:
                if t2 in teams: teams[t2]["w"] += 1
                if t1 in teams: teams[t1]["l"] += 1

        # Sort purely by rank from CSV — no recalculation
        sorted_teams = sorted(
            teams.items(),
            key=lambda x: (x[1]["rank"] if x[1]["rank"] > 0 else 999,
                          -x[1]["points"], -x[1]["gd"], -x[1]["gf"])
        )
        standings[group] = sorted_teams

    return standings

def get_starts_in(match_date, match_time):
    try:
        time_parts = str(match_time).split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        match_dt = datetime(
            match_date.year, match_date.month, match_date.day,
            hour, minute, tzinfo=PKT
        )
        delta = match_dt - NOW
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "", False
        elif total_seconds < 3600:
            mins = total_seconds // 60
            return f"Starts in {mins} minutes", True
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"Starts in {hours} hours", True
        else:
            return "", False
    except:
        return "", False

def display_team_name(name):
    """Show slot codes in a styled way if not yet resolved."""
    name = str(name).strip()
    if name.startswith("W"):
        return f"<span style='color:#888; font-style:italic;'>Winner M{name[1:]}</span>"
    if name.startswith("L"):
        return f"<span style='color:#888; font-style:italic;'>Runner-up M{name[1:]}</span>"
    return name

def render_card(row, favorite_team=None, rank=None):
    category = str(row["category"])
    if category == "TBD" and str(row.get("stage", "")).strip().lower() in KNOCKOUT_STAGES:
        category = str(row["stage"]).strip().title()
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["TBD"])
    short_reason, extended_reason = parse_reason(row["reason"])
    title_size = "1.4rem" if IS_MOBILE else "2rem"
    meta_size  = "0.75rem" if IS_MOBILE else "0.85rem"
    is_favorite = favorite_team and (
        str(row["team1"]) == favorite_team or
        str(row["team2"]) == favorite_team
    )
    starts_in_text, is_soon = get_starts_in(row["date"], row["time"])

    # Build winner display
    winner = str(row["winner"]) if pd.notna(row["winner"]) and str(row["winner"]) != "" else ""
    result_text = ""
    if winner:
        s1 = str(row["score_team1"]) if pd.notna(row["score_team1"]) else ""
        s2 = str(row["score_team2"]) if pd.notna(row["score_team2"]) else ""
        if s1 and s2:
            result_text = f"{s1}–{s2} · {'Draw' if winner == 'Draw' else winner + ' win'}"

    rank_span = f"<span style='float:right; font-family:Barlow,sans-serif; font-size:0.85rem; color:#666;'>#{rank}</span>" if rank else ""
    flag1 = get_flag_b64(row["team1"]) if not str(row["team1"]).startswith(("W","L")) else ""
    flag2 = get_flag_b64(row["team2"]) if not str(row["team2"]).startswith(("W","L")) else ""
    team1 = str(row["team1"])
    team2 = str(row["team2"])
    local_dt = row["match_datetime"].astimezone(user_tz)
    time_str = local_dt.strftime("%H:%M")
    date_str = local_dt.strftime("%b %d, %Y")
    venue = str(row["venue"])
    bg = colors["bg"]
    border = colors["border"]
    badge_bg = colors["badge_bg"]
    badge_text = colors["badge_text"]

    card_style = f"background-color:{bg}; border-color:{border}; border-left:6px solid {border}; border-radius:12px; padding:1.5rem; margin-bottom:1.2rem; border-width:2px; border-style:solid; position:relative; font-family:Barlow,sans-serif;"

    html = "<div style='" + card_style + "'>"

    # Top-right corner: either ⭐ favorite, or ⏳ next match badge, or rank
    if is_favorite:
        html += "<div style='position:absolute; top:1rem; right:1rem; font-size:1.2rem;'>⭐</div>"
    html += "<span style='display:inline-block; padding:0.25rem 0.9rem; border-radius:20px; font-size:0.75rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; background-color:" + badge_bg + "; color:" + badge_text + ";'>" + category + "</span>"
    html += rank_span
    t1_display = display_team_name(team1)
    t2_display = display_team_name(team2)
    html += f"<div style='font-family:Bebas Neue,sans-serif; font-size:{title_size}; letter-spacing:0.08em; color:#111111; margin:0.3rem 0; line-height:1.1;'>" + flag1 + " " + t1_display + " vs " + t2_display + " " + flag2 + "</div>"
    html += f"<div style='font-size:{meta_size}; color:#444444; margin-top:0.4rem; font-weight:500;'>📅 " + date_str + " &nbsp;·&nbsp; 🕐 " + time_str + " " + USER_TZ_LABEL + " &nbsp;·&nbsp; 📍 " + venue + "</div>"

    if starts_in_text:
        html += "<div style='display:inline-block; margin-top:0.5rem; font-size:0.8rem; font-weight:600; color:#1a7a1a; background:rgba(0,150,0,0.08); padding:0.2rem 0.6rem; border-radius:4px;'>⏱ " + starts_in_text + "</div>"
    if result_text:
        html += "<div style='margin-top:0.5rem; font-size:0.85rem; font-weight:600; color:#333;'>🏆 " + result_text + "</div>"
    html += "<div style='font-size:0.9rem; color:#333333; margin-top:0.8rem; line-height:1.5; border-top:1px solid rgba(0,0,0,0.1); padding-top:0.8rem;'>" + short_reason + "</div>"
    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)

    if extended_reason:
        with st.expander("+ More"):
            st.markdown(f"<p style='font-family:Barlow,sans-serif; font-size:0.9rem; line-height:1.6; color:#cccccc;'>{extended_reason}</p>",
                       unsafe_allow_html=True)
if POST_TOURNAMENT:
    st.markdown("""
    <div style='text-align:center; padding:4rem 2rem;'>
        <p style='font-family:Bebas Neue,sans-serif; font-size:3rem; 
        color:#ffffff; letter-spacing:0.15em; margin:0;'>
        FIFA World Cup 2026 — Final Whistle</p>
        <p style='font-family:Barlow,sans-serif; font-size:1.1rem; 
        color:#888; margin-top:1rem; max-width:600px; margin-left:auto; margin-right:auto;'>
        The tournament is over. The Match Curator has been archived.<br>
        Thank you for watching with us.</p>
        <p style='font-family:Bebas Neue,sans-serif; font-size:1.5rem; 
        color:#2d8a2d; margin-top:2rem; letter-spacing:0.1em;'>
        See you at the next World Cup. 🏆</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

KNOCKOUT_STAGES = ["round of 32", "round of 16", "quarter-final", 
                   "semi-final", "play-off for third place", "final"]

is_knockout = df["stage"].str.lower().isin(KNOCKOUT_STAGES)

today_matches = df[
    (df["match_datetime"] > NOW) &
    (df["match_datetime"] <= next_24h) &
    (df["winner"].fillna("") == "") &
    (
        is_knockout |
        (
            ~is_knockout &
            (df["category"] != "TBD") &
            df["category"].isin(selected_categories)
        )
    )
].copy()

# Also exclude any currently live matches
live_scores = get_live_scores()
if live_scores:
    live_keys = set(live_scores.keys())
    def is_live_match(row):
        k1 = f"{row['team1']} vs {row['team2']}"
        k2 = f"{row['team2']} vs {row['team1']}"
        return k1 in live_keys or k2 in live_keys
    today_matches = today_matches[~today_matches.apply(is_live_match, axis=1)]

# Exclude next-match scoreboard card
excluded_id = st.session_state.get("scoreboard_match_id", None)
if excluded_id:
    today_matches = today_matches[today_matches["match_id"] != excluded_id]

# Exclude any currently live matches from the 24h cards
live_scores = get_live_scores()
if live_scores:
    live_keys = set(live_scores.keys())
    def is_live_match(row):
        k1 = f"{row['team1']} vs {row['team2']}"
        k2 = f"{row['team2']} vs {row['team1']}"
        return k1 in live_keys or k2 in live_keys
    today_matches = today_matches[~today_matches.apply(is_live_match, axis=1)]

# Sort by entertainment value
cat_order = {"Must Watch": 0, "Worth Watching": 1, "Optional": 2, "Skip": 3}
today_matches["sort_order"] = today_matches["category"].map(cat_order)
today_matches = today_matches.sort_values("sort_order")

# Favorite team match always shown first
if favorite_team:
    fav_matches = today_matches[
        (today_matches["team1"] == favorite_team) |
        (today_matches["team2"] == favorite_team)
    ]
    other_matches = today_matches[
        (today_matches["team1"] != favorite_team) &
        (today_matches["team2"] != favorite_team)
    ]
    today_matches = pd.concat([fav_matches, other_matches])

if PRE_TOURNAMENT and not SHOW_RANKINGS:
    st.markdown("""
    <div style='text-align:center; padding:3rem 1rem;'>
        <p style='font-family:Bebas Neue,sans-serif; font-size:2.5rem; 
        color:#ffffff; letter-spacing:0.1em; margin:0;'>
        Tournament Hasn't Started Yet</p>
        <p style='font-family:Barlow,sans-serif; font-size:1rem; 
        color:#888; margin-top:0.5rem;'>
        Browse the full schedule below to plan your viewing.</p>
    </div>
    """, unsafe_allow_html=True)

elif len(today_matches) == 0:
    st.markdown("""
    <div style='text-align:center; padding:2rem 1rem;'>
        <p style='font-family:Bebas Neue,sans-serif; font-size:1.8rem; 
        color:#ffffff; letter-spacing:0.1em;'>No Matches in Next 24 Hours</p>
        <p style='font-family:Barlow,sans-serif; font-size:0.95rem; 
        color:#888;'>Check the full schedule for upcoming fixtures.</p>
    </div>
    """, unsafe_allow_html=True)

else:
    match_count = len(today_matches)
    st.markdown(f"""
    <div style='margin-bottom:1.5rem;'>
        <p style='font-family:Bebas Neue,sans-serif; font-size:2rem; 
        color:#ffffff; letter-spacing:0.1em; margin:0;'>
        Matches Worth Watching in the next 24h</p>
        <p style='font-family:Barlow,sans-serif; font-size:0.9rem; 
        color:#888; margin-top:0.2rem;'>
        {match_count} match{'es' if match_count > 1 else ''} · 
        {today.strftime("%B %d, %Y")} · Ranked by entertainment value</p>
    </div>
    """, unsafe_allow_html=True)

    for rank, (_, row) in enumerate(today_matches.iterrows(), 1):
        render_card(row, favorite_team=favorite_team, rank=rank)

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

if PRE_TOURNAMENT:
    tabs = st.tabs(["📅 Full Schedule"])
    tab_schedule = tabs[0]
    tab_bracket = None
    active_tabs = ["schedule"]
else:
    tab_standings, tab_bracket, tab_schedule = st.tabs([
        "📊 Group Standings",
        "🏆 Knockout Bracket",
        "📅 Fixtures & Results",
    ])
    active_tabs = ["standings", "bracket", "schedule"]


# ── Knockout Bracket Tab ──────────────────────────────────────────────────────
if "bracket" in active_tabs and tab_bracket is not None:
    with tab_bracket:

        # ── Data prep ────────────────────────────────────────────────────────
        BRACKET_STAGES = [
            "round of 32", "round of 16",
            "quarter-final", "semi-final", "final"
        ]
        bracket_df = df[df["stage"].str.lower().isin(BRACKET_STAGES)].copy()
        bracket_df["stage_lower"] = bracket_df["stage"].str.lower()

        def get_bracket_matches(stage):
            return bracket_df[bracket_df["stage_lower"] == stage].sort_values("match_id").reset_index(drop=True)

        r32  = get_bracket_matches("round of 32")
        r16  = get_bracket_matches("round of 16")
        qf   = get_bracket_matches("quarter-final")
        sf   = get_bracket_matches("semi-final")
        fin  = get_bracket_matches("final")

        # Category → color mapping (matches your existing scheme)
        CAT_COLORS = {
            "Must Watch":     "#2d8a2d",
            "Worth Watching": "#0099bb",
            "Optional":       "#cccc00",
            "Skip":           "#cc0000",
            "TBD":            "#555555",
        }
        CAT_BG = {
            "Must Watch":     "#d4f5d4",
            "Worth Watching": "#d0f0f8",
            "Optional":       "#feffd4",
            "Skip":           "#fdd4d4",
            "TBD":            "#2a2a2a",
        }
        # Text color on dark background
        CAT_TEXT = {
            "Must Watch":     "#90ee90",
            "Worth Watching": "#66ddff",
            "Optional":       "#eeee44",
            "Skip":           "#ff8888",
            "TBD":            "#aaaaaa",
        }

        def team_display_short(name):
            name = str(name).strip()
            if name.startswith("W"):
                return f"W{name[1:]}"
            if name.startswith("L"):
                return f"L{name[1:]}"
            return TEAM_SHORT.get(name, name)

        def card_color(cat):
            return CAT_TEXT.get(str(cat), CAT_TEXT["TBD"])

        def border_color(cat):
            return CAT_COLORS.get(str(cat), CAT_COLORS["TBD"])

        def score_str(row):
            try:
                s1 = str(row["score_team1"]).split(".")[0]
                s2 = str(row["score_team2"]).split(".")[0]
                if s1 not in ["", "nan"] and s2 not in ["", "nan"]:
                    return f"{s1}–{s2}"
            except:
                pass
            return ""

        def winner_of(row):
            w = str(row["winner"]).strip() if pd.notna(row["winner"]) else ""
            if w in ["", "nan", "0", "TBD"]:
                return ""
            return w

        STAGE_SIZES = {
            "round of 32":   {"team_h": 44, "card_w": 180, "col_gap": 70,  "v_gap": 28},
            "round of 16":   {"team_h": 48, "card_w": 195, "col_gap": 75,  "v_gap": 30},
            "quarter-final": {"team_h": 54, "card_w": 215, "col_gap": 80,  "v_gap": 34},
            "semi-final":    {"team_h": 62, "card_w": 230, "col_gap": 90,  "v_gap": 40},
            "final":         {"team_h": 70, "card_w": 245, "col_gap": 100, "v_gap": 48},
        }

        TEAM_H = 44
        CARD_H = TEAM_H * 2 + 6
        CARD_W = 180
        COL_GAP = 70
        V_GAP = 28

        # stage column order: R32 left, Final center
        # We draw left-half: R32(8) → R16(4) → QF(2) → SF(1)
        # and right-half:    SF(1) → QF(2) → R16(4) → R32(8) mirrored
        # Final sits in the absolute centre

        def make_team_slot(name, cat, is_winner, score_side="", team_h=44, winner="", opponent=""):
            name_str = str(name).strip()
            border = border_color(cat)

            has_result = winner != ""
            is_loser = has_result and not is_winner
            is_tbd_slot = name_str.startswith(("W", "L")) and name_str[1:].isdigit()

            if is_winner:
                bg = "#1a2e1a"
                name_color = CAT_TEXT.get(cat, CAT_TEXT['TBD'])
                flag_filter = ""
                score_color = "#f0c040"
            elif is_loser:
                bg = "#161616"
                name_color = "#888"
                flag_filter = "filter:grayscale(60%) brightness(0.8);"
                score_color = "#6b5a20"
            else:
                bg = "#252525" if is_tbd_slot else "#1e1e1e"
                name_color = "#777" if is_tbd_slot else CAT_TEXT.get(cat, CAT_TEXT['TBD'])
                flag_filter = ""
                score_color = "#f0c040"

            bold  = "700" if is_winner else "400"
            trophy = " 🏆" if is_winner else ""

            if name_str.startswith("W") and name_str[1:].isdigit():
                slot_html = (
                    f"<span style='font-family:Barlow,sans-serif; font-size:0.72rem; "
                    f"color:#666; font-style:italic;'>Winner of M{name_str[1:]}</span>"
                )
            elif name_str.startswith("L") and name_str[1:].isdigit():
                slot_html = (
                    f"<span style='font-family:Barlow,sans-serif; font-size:0.72rem; "
                    f"color:#666; font-style:italic;'>Runner-up M{name_str[1:]}</span>"
                )
            else:
                flag_b64 = get_flag_b64(name_str, height=16)
                short = TEAM_SHORT.get(name_str, name_str)
                if flag_filter:
                    flag_img = flag_b64.replace("style='", f"style='{flag_filter} ", 1)
                else:
                    flag_img = flag_b64
                slot_html = (
                    f"<span style='display:flex; align-items:center; gap:5px;'>"
                    f"{flag_img}"
                    f"<span style='font-family:Barlow,sans-serif; font-size:0.78rem; "
                    f"font-weight:{bold}; color:{name_color};'>{short}{trophy}</span>"
                    f"</span>"
                )

            score_html = (
                f"<span style='margin-left:auto; font-family:Bebas Neue,sans-serif; "
                f"font-size:0.95rem; color:{score_color};'>{score_side}</span>"
                if score_side and score_side not in ["0", ""] else ""
            )

            return (
                f"<div style='height:{team_h}px; display:flex; align-items:center; "
                f"padding:0 10px; gap:6px; background:{bg}; border-left:3px solid {border}; "
                f"overflow:hidden;'>"
                f"{slot_html}{score_html}"
                f"</div>"
            )

        def make_match_card(row, confirmed=True):
            stage = str(row.get("stage", "round of 32")).lower()
            sz = STAGE_SIZES.get(stage, STAGE_SIZES["round of 32"])
            t_h = sz["team_h"]
            c_w = sz["card_w"]

            cat  = str(row.get("category", "TBD"))
            t1   = str(row["team1"]) if pd.notna(row["team1"]) else "TBD"
            t2   = str(row["team2"]) if pd.notna(row["team2"]) else "TBD"
            w    = winner_of(row)
            sc   = score_str(row)
            s1, s2 = ("", "")
            if sc:
                parts = sc.split("–")
                s1 = parts[0] if len(parts) > 0 else ""
                s2 = parts[1] if len(parts) > 1 else ""

            is_tbd = (not confirmed) or t1.startswith(("W","L","1","2","3")) or t2.startswith(("W","L","1","2","3"))
            effective_cat = "TBD" if is_tbd else cat
            border = border_color(effective_cat)

            slot1 = make_team_slot(t1, effective_cat, w == t1 and w != "", s1, t_h, w, t2)
            slot2 = make_team_slot(t2, effective_cat, w == t2 and w != "", s2, t_h, w, t1)

            mid_line = (
                f"<div style='height:2px; background:linear-gradient(90deg, "
                f"{border}22, {border}88, {border}22);'></div>"
            )

            match_id = int(row.get("match_id", 0))
            is_live = False
            live_scores = get_live_scores()
            for lm in live_scores.values():
                if lm["home"] == t1 or lm["away"] == t1:
                    is_live = True
                    break

            live_pulse = ""
            if is_live:
                live_pulse = (
                    f"<div style='background:#c0392b; display:flex; align-items:center; "
                    f"justify-content:center; gap:5px; padding:3px 10px;'>"
                    f"<div style='width:6px; height:6px; border-radius:50%; background:#fff; "
                    f"animation:sbpulse 1.2s infinite;'></div>"
                    f"<span style='font-size:0.65rem; font-weight:700; color:#fff; "
                    f"letter-spacing:0.1em;'>LIVE</span>"
                    f"</div>"
                )

            card_id = f"match_{match_id}"
            return (
                f"<div id='{card_id}' class='bracket-card' data-match='{match_id}' "
                f"style='width:{c_w}px; border-radius:12px; overflow:hidden; "
                f"border:1.5px solid {border}; "
                f"box-shadow: 0 2px 8px rgba(0,0,0,0.4); "
                f"transition: box-shadow 0.2s ease;'>"
                f"{live_pulse}"
                f"{slot1}{mid_line}{slot2}"
                f"</div>"
            )

        def split_half(stage_df):
            n = len(stage_df)
            mid = n // 2
            left  = stage_df.iloc[:mid].reset_index(drop=True)
            right = stage_df.iloc[mid:].reset_index(drop=True)
            return left, right

        r32_left,  r32_right  = split_half(r32)
        r16_left,  r16_right  = split_half(r16)
        qf_left,   qf_right   = split_half(qf)
        sf_left_df, sf_right_df = split_half(sf)
        fin_row = fin.iloc[0] if len(fin) > 0 else None

        # ── Rewrite compute_positions_left to accept DataFrames ───────────────
        def compute_positions(r32_df, r16_df, qf_df, sf_df):
            stages = {}
            r32_list = list(r32_df.iterrows())
            r16_list = list(r16_df.iterrows())
            qf_list  = list(qf_df.iterrows())
            sf_list  = list(sf_df.iterrows())

            r32_y_step = CARD_H + V_GAP
            stages["r32"] = []
            for i, (_, row) in enumerate(r32_list):
                y = i * r32_y_step
                stages["r32"].append((0, y, row))

            r16_x = CARD_W + COL_GAP
            stages["r16"] = []
            for j, (_, row) in enumerate(r16_list):
                i1, i2 = j * 2, j * 2 + 1
                y1 = stages["r32"][i1][1] if i1 < len(stages["r32"]) else 0
                y2 = stages["r32"][i2][1] if i2 < len(stages["r32"]) else y1
                mid_y = (y1 + CARD_H + y2) / 2 - CARD_H / 2
                stages["r16"].append((r16_x, mid_y, row))

            qf_x = r16_x + CARD_W + COL_GAP
            stages["qf"] = []
            for j, (_, row) in enumerate(qf_list):
                i1, i2 = j * 2, j * 2 + 1
                y1 = stages["r16"][i1][1] if i1 < len(stages["r16"]) else 0
                y2 = stages["r16"][i2][1] if i2 < len(stages["r16"]) else y1
                mid_y = (y1 + CARD_H + y2) / 2 - CARD_H / 2
                stages["qf"].append((qf_x, mid_y, row))

            sf_x = qf_x + CARD_W + COL_GAP
            stages["sf"] = []
            for j, (_, row) in enumerate(sf_list):
                i1, i2 = j * 2, j * 2 + 1
                y1 = stages["qf"][i1][1] if i1 < len(stages["qf"]) else 0
                y2 = stages["qf"][i2][1] if i2 < len(stages["qf"]) else y1
                mid_y = (y1 + CARD_H + y2) / 2 - CARD_H / 2
                stages["sf"].append((sf_x, mid_y, row))

            return stages

        lp = compute_positions(r32_left, r16_left, qf_left, sf_left_df)
        rp = compute_positions(r32_right, r16_right, qf_right, sf_right_df)

        # ── Canvas sizing ─────────────────────────────────────────────────────
        # Left half width = 4 cols of cards + 3 gaps + padding
        HALF_W   = CARD_W * 4 + COL_GAP * 3
        FIN_W    = CARD_W + COL_GAP * 2   # final card + breathing room each side
        TOTAL_W  = HALF_W * 2 + FIN_W
        PADDING  = 40

        # Height = tallest half (should be same)
        n_r32 = max(len(r32_left), len(r32_right))
        TOTAL_H = n_r32 * (CARD_H + V_GAP) - V_GAP + PADDING * 2

        # Final card Y position = vertical centre
        FIN_Y = TOTAL_H / 2 - CARD_H / 2

        # ── Connector line helper ─────────────────────────────────────────────
        def h_connector(x1, y1_mid, x2, y2_mid, color="#444"):
            """
            Elbow connector: right-exit from card1 centre → left-entry of card2 centre.
            """
            mid_x = (x1 + x2) / 2
            return (
                f"<line x1='{x1}' y1='{y1_mid}' x2='{mid_x}' y2='{y1_mid}' "
                f"stroke='{color}' stroke-width='1.5' stroke-dasharray='4 3'/>"
                f"<line x1='{mid_x}' y1='{y1_mid}' x2='{mid_x}' y2='{y2_mid}' "
                f"stroke='{color}' stroke-width='1.5' stroke-dasharray='4 3'/>"
                f"<line x1='{mid_x}' y1='{y2_mid}' x2='{x2}' y2='{y2_mid}' "
                f"stroke='{color}' stroke-width='1.5' stroke-dasharray='4 3'/>"
            )

        # ── Stage label positions (above top card of each column) ─────────────
        STAGE_LABELS = {
            "R32":    "ROUND OF 32",
            "R16":    "ROUND OF 16",
            "QF":     "QUARTER-FINAL",
            "SF":     "SEMI-FINAL",
            "FINAL":  "FINAL",
        }

        # ── Build HTML ────────────────────────────────────────────────────────
        # Layout offsets:
        # Left half:  R32 at x=PADDING, R16, QF, SF going right
        # Right half: SF at x=HALF_W+FIN_W+PADDING, then QF, R16, R32 going further right (mirrored)
        # Final:      at x = HALF_W + COL_GAP + PADDING

        L_OFF = PADDING                          # left R32 x-start
        R_OFF = PADDING + HALF_W + FIN_W        # right R32 x-start (mirrored, card right-edge aligns)
        FIN_X = PADDING + HALF_W + (FIN_W - CARD_W) / 2

        # Right half: R32 is rightmost, so column order is reversed.
        # rp["r32"] x=0 → actual x = R_OFF + (HALF_W - CARD_W) - 0 = far right
        def rx(x):  # mirror x for right half
            return R_OFF + (HALF_W - CARD_W) - x

        cards_html = ""
        lines_svg  = ""

        LABEL_H = 32  # extra top padding for labels
        V_SHIFT  = PADDING + LABEL_H

        # ── Left half cards ───────────────────────────────────────────────────
        for stage_key, items in lp.items():
            for (x, y, row) in items:
                abs_x = L_OFF + x
                abs_y = V_SHIFT + y
                confirmed = not (
                    str(row["team1"]).startswith(("W","L","1","2","3")) or
                    str(row["team2"]).startswith(("W","L","1","2","3"))
                )
                card = make_match_card(row, confirmed=confirmed)
                cards_html += (
                    f"<div style='position:absolute; left:{abs_x}px; top:{abs_y}px; width:{CARD_W}px;'>"
                    f"{card}</div>"
                )

        # ── Right half cards (mirrored) ───────────────────────────────────────
        for stage_key, items in rp.items():
            for (x, y, row) in items:
                abs_x = rx(x)
                abs_y = V_SHIFT + y
                confirmed = not (
                    str(row["team1"]).startswith(("W","L","1","2","3")) or
                    str(row["team2"]).startswith(("W","L","1","2","3"))
                )
                card = make_match_card(row, confirmed=confirmed)
                cards_html += (
                    f"<div style='position:absolute; left:{abs_x}px; top:{abs_y}px; width:{CARD_W}px;'>"
                    f"{card}</div>"
                )

        # ── Final card ────────────────────────────────────────────────────────
        if fin_row is not None:
            confirmed_fin = not (
                str(fin_row["team1"]).startswith(("W","L","1","2","3")) or
                str(fin_row["team2"]).startswith(("W","L","1","2","3"))
            )
            fin_card = make_match_card(fin_row, confirmed=confirmed_fin)
            cards_html += (
                f"<div style='position:absolute; left:{FIN_X}px; top:{V_SHIFT + FIN_Y}px; "
                f"width:{CARD_W}px;'>{fin_card}</div>"
            )

        # ── Connector lines (SVG) ─────────────────────────────────────────────
        # Left half connectors: R32→R16, R16→QF, QF→SF, SF→Final
        stage_pairs_left = [
            ("r32", "r16"),
            ("r16", "qf"),
            ("qf", "sf"),
        ]
        for s1_key, s2_key in stage_pairs_left:
            s1_items = lp[s1_key]
            s2_items = lp[s2_key]
            for j, (x2, y2, _) in enumerate(s2_items):
                i1, i2 = j * 2, j * 2 + 1
                if i1 < len(s1_items) and i2 < len(s1_items):
                    x1a, y1a, _ = s1_items[i1]
                    x1b, y1b, _ = s1_items[i2]
                    # exit right edge of s1 cards → entry left edge of s2 card
                    xa_out  = L_OFF + x1a + CARD_W
                    ya_mid  = V_SHIFT + y1a + CARD_H / 2
                    xb_out  = L_OFF + x1b + CARD_W
                    yb_mid  = V_SHIFT + y1b + CARD_H / 2
                    x2_in   = L_OFF + x2
                    y2_mid  = V_SHIFT + y2 + CARD_H / 2
                    mid_x   = xa_out + (x2_in - xa_out) / 2
                    lines_svg += (
                        f"<line x1='{xa_out}' y1='{ya_mid}' x2='{mid_x}' y2='{ya_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{ya_mid}' x2='{mid_x}' y2='{yb_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{yb_mid}' x2='{xb_out}' y2='{yb_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{y2_mid}' x2='{x2_in}' y2='{y2_mid}' "
                        f"stroke='#666' stroke-width='1.5'/>"
                    )

        # SF → Final (left)
        # SF → Final (left) — horizontal run to fin_in_x, then vertical to final card centre
        if lp["sf"] and fin_row is not None:
            x_sf, y_sf, _ = lp["sf"][0]
            sf_out_x  = L_OFF + x_sf + CARD_W
            sf_mid_y  = V_SHIFT + y_sf + CARD_H / 2
            fin_in_x  = FIN_X
            fin_mid_y = V_SHIFT + FIN_Y + CARD_H / 2
            mid_x     = sf_out_x + (fin_in_x - sf_out_x) / 2
            lines_svg += (
                f"<line x1='{sf_out_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{sf_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{fin_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{fin_mid_y}' x2='{fin_in_x}' y2='{fin_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
            )

        # Right half connectors (mirrored — lines go right-to-left)
        stage_pairs_right = [
            ("r32", "r16"),
            ("r16", "qf"),
            ("qf", "sf"),
        ]
        for s1_key, s2_key in stage_pairs_right:
            s1_items = rp[s1_key]
            s2_items = rp[s2_key]
            for j, (x2, y2, _) in enumerate(s2_items):
                i1, i2 = j * 2, j * 2 + 1
                if i1 < len(s1_items) and i2 < len(s1_items):
                    x1a, y1a, _ = s1_items[i1]
                    x1b, y1b, _ = s1_items[i2]
                    xa_out  = rx(x1a)                     # left edge of mirrored card
                    ya_mid  = V_SHIFT + y1a + CARD_H / 2
                    xb_out  = rx(x1b)
                    yb_mid  = V_SHIFT + y1b + CARD_H / 2
                    x2_in   = rx(x2) + CARD_W            # right edge of next-round card
                    y2_mid  = V_SHIFT + y2 + CARD_H / 2
                    mid_x   = xa_out - (xa_out - x2_in) / 2
                    lines_svg += (
                        f"<line x1='{xa_out}' y1='{ya_mid}' x2='{mid_x}' y2='{ya_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{ya_mid}' x2='{mid_x}' y2='{yb_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{yb_mid}' x2='{xb_out}' y2='{yb_mid}' "
                        f"stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{y2_mid}' x2='{x2_in}' y2='{y2_mid}' "
                        f"stroke='#666' stroke-width='1.5'/>"
                    )

        # SF → Final (right)
        # SF → Final (right) — symmetric elbow
        if rp["sf"] and fin_row is not None:
            x_sf, y_sf, _ = rp["sf"][0]
            sf_in_x   = rx(x_sf)               # left edge of mirrored SF card
            sf_mid_y  = V_SHIFT + y_sf + CARD_H / 2
            fin_out_x = FIN_X + CARD_W
            fin_mid_y = V_SHIFT + FIN_Y + CARD_H / 2
            mid_x     = fin_out_x + (sf_in_x - fin_out_x) / 2
            lines_svg += (
                f"<line x1='{sf_in_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{sf_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{fin_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{fin_mid_y}' x2='{fin_out_x}' y2='{fin_mid_y}' "
                f"stroke='#888' stroke-width='2'/>"
            )

        # ── Hardcoded bracket tree (match_id based) ───────────────────────────
        # Order within each list = top-to-bottom visual order
        R32_LEFT_IDS  = [75, 78, 73, 76, 84, 83, 82, 81]
        R32_RIGHT_IDS = [74, 77, 79, 80, 87, 86, 85, 88]
        R16_LEFT_IDS  = [90, 89, 93, 94]
        R16_RIGHT_IDS = [91, 92, 95, 96]
        QF_LEFT_IDS  = [97, 99]
        QF_RIGHT_IDS = [98, 100]
        SF_LEFT_IDS   = [101]
        SF_RIGHT_IDS  = [102]
        FINAL_ID      = 104
        THIRD_ID      = 103

        def get_by_ids(stage_df, id_list):
            rows = []
            for mid in id_list:
                match = stage_df[stage_df["match_id"] == mid]
                if len(match) > 0:
                    rows.append(match.iloc[0])
                else:
                    # placeholder empty row
                    rows.append(pd.Series({
                        "match_id": mid, "team1": f"W?", "team2": f"W?",
                        "stage": "round of 32", "category": "TBD",
                        "winner": "", "score_team1": "", "score_team2": "",
                        "venue": "", "date": pd.NaT, "time": ""
                    }))
            return pd.DataFrame(rows).reset_index(drop=True)

        r32_left  = get_by_ids(bracket_df, R32_LEFT_IDS)
        r32_right = get_by_ids(bracket_df, R32_RIGHT_IDS)
        r16_left  = get_by_ids(bracket_df, R16_LEFT_IDS)
        r16_right = get_by_ids(bracket_df, R16_RIGHT_IDS)
        qf_left   = get_by_ids(bracket_df, QF_LEFT_IDS)
        qf_right  = get_by_ids(bracket_df, QF_RIGHT_IDS)
        sf_left_df  = get_by_ids(bracket_df, SF_LEFT_IDS)
        sf_right_df = get_by_ids(bracket_df, SF_RIGHT_IDS)

        fin_matches = bracket_df[bracket_df["match_id"] == FINAL_ID]
        fin_row = fin_matches.iloc[0] if len(fin_matches) > 0 else None
        third_matches = bracket_df[bracket_df["match_id"] == THIRD_ID]
        third_row = third_matches.iloc[0] if len(third_matches) > 0 else None

        lp = compute_positions(r32_left, r16_left, qf_left, sf_left_df)
        rp = compute_positions(r32_right, r16_right, qf_right, sf_right_df)

        # ── Canvas sizing ─────────────────────────────────────────────────────
        HALF_W   = CARD_W * 4 + COL_GAP * 3
        FIN_W    = CARD_W + COL_GAP * 2
        TOTAL_W  = HALF_W * 2 + FIN_W
        PADDING  = 40

        n_r32    = 8
        TOTAL_H  = n_r32 * (CARD_H + V_GAP) - V_GAP + PADDING * 2 + 60  # +60 for 3rd place card
        FIN_Y    = TOTAL_H / 2 - CARD_H / 2 - 30
        THIRD_Y  = FIN_Y + CARD_H + V_GAP + 20

        FIN_X    = PADDING + HALF_W + (FIN_W - CARD_W) / 2
        L_OFF    = PADDING
        R_OFF    = PADDING + HALF_W + FIN_W

        def rx(x):
            return R_OFF + (HALF_W - CARD_W) - x

        LABEL_H  = 32
        V_SHIFT  = PADDING + LABEL_H

        cards_html = ""
        lines_svg  = ""

        # ── Left half cards ───────────────────────────────────────────────────
        for stage_key, items in lp.items():
            for (x, y, row) in items:
                abs_x = L_OFF + x
                abs_y = V_SHIFT + y
                confirmed = not (
                    str(row["team1"]).startswith(("W","L","1","2","3")) or
                    str(row["team2"]).startswith(("W","L","1","2","3"))
                )
                card = make_match_card(row, confirmed=confirmed)
                cards_html += (
                    f"<div style='position:absolute; left:{abs_x}px; top:{abs_y}px; width:{CARD_W}px;'>"
                    f"{card}</div>"
                )

        # ── Right half cards (mirrored) ───────────────────────────────────────
        for stage_key, items in rp.items():
            for (x, y, row) in items:
                abs_x = rx(x)
                abs_y = V_SHIFT + y
                confirmed = not (
                    str(row["team1"]).startswith(("W","L","1","2","3")) or
                    str(row["team2"]).startswith(("W","L","1","2","3"))
                )
                card = make_match_card(row, confirmed=confirmed)
                cards_html += (
                    f"<div style='position:absolute; left:{abs_x}px; top:{abs_y}px; width:{CARD_W}px;'>"
                    f"{card}</div>"
                )

        # ── Final card ────────────────────────────────────────────────────────
        if fin_row is not None:
            confirmed_fin = not (
                str(fin_row["team1"]).startswith(("W","L","1","2","3")) or
                str(fin_row["team2"]).startswith(("W","L","1","2","3"))
            )
            fin_card = make_match_card(fin_row, confirmed=confirmed_fin)
            cards_html += (
                f"<div style='position:absolute; left:{FIN_X}px; top:{V_SHIFT + FIN_Y}px; "
                f"width:{CARD_W}px;'>{fin_card}</div>"
            )

        # ── 3rd place card (below final, slightly right-offset) ───────────────
        if third_row is not None:
            confirmed_third = not (
                str(third_row["team1"]).startswith(("W","L","1","2","3")) or
                str(third_row["team2"]).startswith(("W","L","1","2","3"))
            )
            third_card = make_match_card(third_row, confirmed=confirmed_third)
            third_label = (
                f"<div style='position:absolute; left:{FIN_X + CARD_W + 20}px; "
                f"top:{V_SHIFT + THIRD_Y - 20}px; "
                f"font-family:Bebas Neue,sans-serif; font-size:0.75rem; "
                f"color:#888; letter-spacing:0.1em;'>3RD PLACE</div>"
            )
            cards_html += third_label
            cards_html += (
                f"<div style='position:absolute; left:{FIN_X + CARD_W + 20}px; "
                f"top:{V_SHIFT + THIRD_Y}px; width:{CARD_W}px;'>{third_card}</div>"
            )

        # ── Connector lines ───────────────────────────────────────────────────
        def draw_connectors(half_pos, is_right=False):
            svg = ""
            stage_pairs = [("r32","r16"), ("r16","qf"), ("qf","sf")]
            for s1_key, s2_key in stage_pairs:
                s1_items = half_pos[s1_key]
                s2_items = half_pos[s2_key]
                for j, (x2, y2, _) in enumerate(s2_items):
                    i1, i2 = j * 2, j * 2 + 1
                    if i1 >= len(s1_items) or i2 >= len(s1_items):
                        continue
                    x1a, y1a, _ = s1_items[i1]
                    x1b, y1b, _ = s1_items[i2]
                    if not is_right:
                        xa_out = L_OFF + x1a + CARD_W
                        ya_mid = V_SHIFT + y1a + CARD_H / 2
                        xb_out = L_OFF + x1b + CARD_W
                        yb_mid = V_SHIFT + y1b + CARD_H / 2
                        x2_in  = L_OFF + x2
                        y2_mid = V_SHIFT + y2 + CARD_H / 2
                        mid_x  = xa_out + (x2_in - xa_out) / 2
                    else:
                        xa_out = rx(x1a)
                        ya_mid = V_SHIFT + y1a + CARD_H / 2
                        xb_out = rx(x1b)
                        yb_mid = V_SHIFT + y1b + CARD_H / 2
                        x2_in  = rx(x2) + CARD_W
                        y2_mid = V_SHIFT + y2 + CARD_H / 2
                        mid_x  = xa_out - (xa_out - x2_in) / 2
                    svg += (
                        f"<line x1='{xa_out}' y1='{ya_mid}' x2='{mid_x}' y2='{ya_mid}' stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{ya_mid}' x2='{mid_x}' y2='{yb_mid}' stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{yb_mid}' x2='{xb_out}' y2='{yb_mid}' stroke='#444' stroke-width='1.5'/>"
                        f"<line x1='{mid_x}' y1='{y2_mid}' x2='{x2_in}' y2='{y2_mid}' stroke='#666' stroke-width='1.5'/>"
                    )
            return svg

        lines_svg += draw_connectors(lp, is_right=False)
        lines_svg += draw_connectors(rp, is_right=True)

        # SF → Final (left)
        if lp["sf"] and fin_row is not None:
            x_sf, y_sf, _ = lp["sf"][0]
            sf_out_x  = L_OFF + x_sf + CARD_W
            sf_mid_y  = V_SHIFT + y_sf + CARD_H / 2
            fin_in_x  = FIN_X
            fin_mid_y = V_SHIFT + FIN_Y + CARD_H / 2
            mid_x     = sf_out_x + (fin_in_x - sf_out_x) / 2
            lines_svg += (
                f"<line x1='{sf_out_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{sf_mid_y}' stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{fin_mid_y}' stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{fin_mid_y}' x2='{fin_in_x}' y2='{fin_mid_y}' stroke='#888' stroke-width='2'/>"
            )

        # SF → Final (right)
        if rp["sf"] and fin_row is not None:
            x_sf, y_sf, _ = rp["sf"][0]
            sf_in_x   = rx(x_sf)
            sf_mid_y  = V_SHIFT + y_sf + CARD_H / 2
            fin_out_x = FIN_X + CARD_W
            fin_mid_y = V_SHIFT + FIN_Y + CARD_H / 2
            mid_x     = fin_out_x + (sf_in_x - fin_out_x) / 2
            lines_svg += (
                f"<line x1='{sf_in_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{sf_mid_y}' stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{sf_mid_y}' x2='{mid_x}' y2='{fin_mid_y}' stroke='#888' stroke-width='2'/>"
                f"<line x1='{mid_x}' y1='{fin_mid_y}' x2='{fin_out_x}' y2='{fin_mid_y}' stroke='#888' stroke-width='2'/>"
            )

        # ── Stage labels ──────────────────────────────────────────────────────
        r_r32_x = rx(0)
        r_r16_x = rx(CARD_W + COL_GAP)
        r_qf_x  = rx((CARD_W + COL_GAP) * 2)
        r_sf_x  = rx((CARD_W + COL_GAP) * 3)

        label_positions = [
            (L_OFF,                          "ROUND OF 32"),
            (L_OFF + CARD_W + COL_GAP,       "ROUND OF 16"),
            (L_OFF + (CARD_W + COL_GAP) * 2, "QUARTER-FINAL"),
            (L_OFF + (CARD_W + COL_GAP) * 3, "SEMI-FINAL"),
            (FIN_X,                           "FINAL"),
            (r_sf_x,                          "SEMI-FINAL"),
            (r_qf_x,                          "QUARTER-FINAL"),
            (r_r16_x,                         "ROUND OF 16"),
            (r_r32_x,                         "ROUND OF 32"),
        ]

        labels_html = ""
        for lx, label in label_positions:
            labels_html += (
                f"<div style='position:absolute; left:{lx}px; top:{PADDING - 4}px; "
                f"width:{CARD_W}px; text-align:center; "
                f"font-family:Bebas Neue,sans-serif; font-size:0.8rem; "
                f"color:#666; letter-spacing:0.12em;'>{label}</div>"
            )

        # ── Legend ────────────────────────────────────────────────────────────
        legend_html = "".join([
            f"<span style='display:inline-flex; align-items:center; gap:5px; margin-right:16px; "
            f"font-family:Barlow,sans-serif; font-size:0.75rem; color:{CAT_TEXT[c]};'>"
            f"<span style='width:10px; height:10px; border-radius:2px; background:{CAT_COLORS[c]}; "
            f"display:inline-block;'></span>{c}</span>"
            for c in ["Must Watch", "Worth Watching", "Optional", "Skip", "TBD"]
        ])

        # ── Render ────────────────────────────────────────────────────────────
        with tab_bracket:

    # ... all your existing bracket data prep, compute_positions, 
    # cards_html, lines_svg, labels_html building code stays exactly as is ...

    # ── Render ── (this is your existing components.html, with the CSS added)
            components.html(
                f"""
                <!DOCTYPE html>
                <html>
                <head>
                <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">
                <style>
                body {{ margin: 0; padding: 0; background: #0a0a0a; }}
                .bracket-scroll {{
                    overflow-x: auto;
                    overflow-y: hidden;
                    padding-bottom: 16px;
                    scrollbar-width: thin;
                    scrollbar-color: #333 #111;
                }}
                .bracket-scroll::-webkit-scrollbar {{ height: 6px; }}
                .bracket-scroll::-webkit-scrollbar-track {{ background: #111; }}
                .bracket-scroll::-webkit-scrollbar-thumb {{ background: #444; border-radius: 3px; }}
                .bracket-canvas {{
                    position: relative;
                    width: {TOTAL_W + PADDING * 2}px;
                    height: {TOTAL_H + LABEL_H}px;
                    background: #0a0a0a;
                }}
                @keyframes sbpulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.25}} }}
                .bracket-card {{
                    cursor: pointer;
                    transition: box-shadow 0.2s ease, transform 0.15s ease;
                }}
                .bracket-card:hover {{
                    box-shadow: 0 0 0 2px #ffffff55, 0 4px 16px rgba(0,0,0,0.6) !important;
                    transform: translateY(-1px);
                    z-index: 10;
                    position: relative;
                }}
                </style>
                </head>
                <body>
                <div style="font-family:Barlow,sans-serif; font-size:0.78rem; color:#666;
                margin-bottom:10px; padding:4px 8px;">
                {legend_html}
                </div>
                <div class="bracket-scroll">
                <div class="bracket-canvas">
                    <svg style="position:absolute; top:0; left:0; width:100%; height:100%;
                    pointer-events:none; overflow:visible;">
                    {lines_svg}
                    </svg>
                    {labels_html}
                    {cards_html}
                </div>
                </div>
                </body>
                </html>
                """,
                height=TOTAL_H + LABEL_H + 60,
                scrolling=True,
            )
# ── Group Standings Tab ───────────────────────────────────────────────────────
if "standings" in active_tabs:
    with tab_standings:
        if "standings_loaded" not in st.session_state:
            st.markdown("<p style='color:#888; text-align:center; padding:2rem; font-family:Barlow,sans-serif;'>Click to load standings</p>", unsafe_allow_html=True)
            if st.button("📊 Load Standings", use_container_width=True):
                st.session_state["standings_loaded"] = True
                st.rerun()
        else:
            standings = build_group_standings(df)
            groups = list(standings.keys())
            cols_per_row = 1 if IS_MOBILE else 4
            rows = [groups[i:i+4] for i in range(0, len(groups), 4)]
            for group_row in rows:
                cols = st.columns(len(group_row))
                for col, group in zip(cols, group_row):
                    with col:
                        group_html = (
                            f"<p style='font-family:Bebas Neue,sans-serif; font-size:1.2rem; "
                            f"color:#ffffff; letter-spacing:0.1em; margin-bottom:0.5rem; "
                            f"border-left:3px solid #ffffff; padding-left:0.6rem;'>"
                            f"Group {group}</p>"
                        )

                        for rank_idx, (team, stats) in enumerate(standings[group], 1):
                            bg = "#1a2e1a" if rank_idx <= 2 else "#1a1a1a"
                            border = "#2d8a2d" if rank_idx <= 2 else "#333333"
                            rank_color = "#90ee90" if rank_idx <= 2 else "#666666"
                            gd_str = f"+{stats['gd']}" if stats['gd'] > 0 else str(stats['gd'])

                            group_html += (
                                f"<div style='background:{bg}; border:1px solid {border}; "
                                f"border-radius:8px; padding:0.5rem 0.75rem; margin-bottom:0.4rem; "
                                f"font-family:Barlow,sans-serif;'>"
                                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                                f"<div style='display:flex; align-items:center; gap:6px;'>"
                                f"<span style='color:{rank_color}; font-weight:700; font-size:0.85rem; min-width:16px;'>{rank_idx}</span>"
                                f"<span style='color:#ffffff; font-size:0.85rem; font-weight:600;'>{team}</span>"
                                f"</div>"
                                f"<span style='color:#ffffff; font-weight:700; font-size:1rem;'>{stats['points']}</span>"
                                f"</div>"
                                f"<div style='display:flex; justify-content:space-between; "
                                f"margin-top:0.3rem; font-size:0.72rem; color:#888;'>"
                                f"<span>P:{stats['played']}</span>"
                                f"<span>W:{stats['w']}</span>"
                                f"<span>D:{stats['d']}</span>"
                                f"<span>L:{stats['l']}</span>"
                                f"<span>GF:{stats['gf']}</span>"
                                f"<span>GD:{gd_str}</span>"
                                f"</div>"
                                f"</div>"
                            )

                        st.markdown(group_html, unsafe_allow_html=True)

# ── Schedule Tab ──────────────────────────────────────────────────────────────
with tab_schedule:
    st.info("Use the filters in the sidebar to control which matches appear.")

    # ── View toggle ──────────────────────────────────────────────
    view_mode = st.radio(
        "Show",
        ["Upcoming", "Results", "All"],
        index=0,
        horizontal=True,
        key="schedule_view_mode"
    )

    schedule_df = df.copy()

    # Apply view mode filter
    def is_played(val):
        s = str(val).strip() if pd.notna(val) else ""
        return s != "" and s.lower() not in ["nan", "0", "tbd"]

    if view_mode == "Upcoming":
        schedule_df = schedule_df[~schedule_df["winner"].apply(is_played)]
    elif view_mode == "Results":
        schedule_df = schedule_df[schedule_df["winner"].apply(is_played)]

    # Apply sidebar filters
    if schedule_team != "All Teams":
        schedule_df = schedule_df[
            (schedule_df["team1"] == schedule_team) |
            (schedule_df["team2"] == schedule_team)
        ]

    if selected_categories:
        knockout_mask = schedule_df["stage"].str.lower().isin(
            ["round of 32", "round of 16", "quarter-final", "semi-final", "play-off for third place", "final"]
        )
        schedule_df = schedule_df[
            knockout_mask | schedule_df["category"].isin(selected_categories)
        ]

    if schedule_stage != "All Stages":
        schedule_df = schedule_df[schedule_df["stage"] == schedule_stage]

    schedule_df["local_date"] = schedule_df["match_datetime"].apply(
        lambda dt: dt.astimezone(user_tz).date()
    )

    if len(schedule_df) == 0:
        st.markdown("<p style='font-family:Barlow,sans-serif; color:#888; text-align:center; padding:2rem;'>No matches found with current filters.</p>", unsafe_allow_html=True)
    else:
        def render_schedule_row(row):
            category = str(row["category"])
            colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["TBD"])
            short_reason, _ = parse_reason(row["reason"])
            winner = str(row["winner"]) if pd.notna(row["winner"]) and str(row["winner"]) != "" else ""
            result_text = ""
            if winner:
                s1 = str(row["score_team1"]) if pd.notna(row["score_team1"]) else ""
                s2 = str(row["score_team2"]) if pd.notna(row["score_team2"]) else ""
                if s1 and s2:
                    result_text = f"{s1}–{s2} · {winner} win"
            is_fav = favorite_team and (
                str(row["team1"]) == favorite_team or
                str(row["team2"]) == favorite_team
            )

            t1 = str(row["team1"])
            t2 = str(row["team2"])

            # Display slot codes nicely if not yet resolved
            def slot_display(name):
                if name.startswith("W"):
                    return f"<span style='color:#888; font-style:italic;'>Winner M{name[1:]}</span>"
                if name.startswith("L"):
                    return f"<span style='color:#888; font-style:italic;'>Runner-up M{name[1:]}</span>"
                return name

            flag1 = get_flag_b64(t1) if not t1.startswith(("W", "L", "1", "2", "3")) else ""
            flag2 = get_flag_b64(t2) if not t2.startswith(("W", "L", "1", "2", "3")) else ""
            t1_display = slot_display(t1)
            t2_display = slot_display(t2)

            with st.container():
                left, right = st.columns([3, 1])
                with left:
                    st.markdown(
                        f"<span style='background:{colors['badge_bg']}; color:{colors['badge_text']}; "
                        f"padding:0.2rem 0.7rem; border-radius:20px; font-size:0.7rem; "
                        f"font-weight:700; letter-spacing:0.1em;'>{category}</span>"
                        f"{'  ⭐' if is_fav else ''}",
                        unsafe_allow_html=True
                    )
                    confirmed_badge = ""

                    st.markdown(
                        f"<p style='font-family:Bebas Neue,sans-serif; font-size:1.3rem; "
                        f"color:#ffffff; margin:0.2rem 0; letter-spacing:0.06em;'>"
                        f"{flag1} {t1_display} vs {t2_display} {flag2}{confirmed_badge}</p>",
                        unsafe_allow_html=True
                    )
                    st.caption(f"📍 {row['venue']}  ·  {row['group'] if pd.notna(row['group']) else row['stage']}")
                    if short_reason and short_reason != "No preview available.":
                        st.caption(f"_{short_reason}_")
                with right:
                    local_dt = row["match_datetime"].astimezone(user_tz)
                    date_display = local_dt.strftime("%b %d")
                    if result_text:
                        s1 = str(row["score_team1"]).split(".")[0]
                        s2 = str(row["score_team2"]).split(".")[0]
                        winner_name = str(row["winner"])
                        result_label = "Draw" if winner_name == "Draw" else f"{winner_name} win"
                        st.markdown(
                            f"<p style='text-align:right; font-family:Barlow,sans-serif; "
                            f"font-size:1rem; color:#f0c040; font-weight:700; margin:0;'>"
                            f"{s1}–{s2}<br>"
                            f"<span style='font-size:0.72rem; color:#f0c040; font-weight:500;'>{result_label}</span><br>"
                            f"<span style='font-size:0.72rem; color:#666; font-weight:400;'>{date_display}</span></p>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<p style='text-align:right; font-family:Barlow,sans-serif; "
                            f"font-size:1rem; color:#ffffff; font-weight:700; margin:0;'>"
                            f"{local_dt.strftime('%H:%M')}<br>"
                            f"<span style='font-size:0.72rem; color:#666;'>{date_display}</span></p>",
                            unsafe_allow_html=True
                        )

        # ── Split into group stage vs knockouts ───────────────────────
        GROUP_STAGE_VALUES   = ["group stage"]
        KNOCKOUT_STAGE_VALUES = ["round of 32", "round of 16", "quarter-final", "semi-final", "play-off for third place", "final"]
        STAGE_ORDER_MAP = {s: i for i, s in enumerate(KNOCKOUT_STAGE_VALUES)}

        group_sched    = schedule_df[schedule_df["stage"].str.lower().isin(GROUP_STAGE_VALUES)]
        knockout_sched = schedule_df[schedule_df["stage"].str.lower().isin(KNOCKOUT_STAGE_VALUES)]

        if len(schedule_df) == 0:
            st.markdown("<p style='font-family:Barlow,sans-serif; color:#888; text-align:center; padding:2rem;'>No matches found with current filters.</p>", unsafe_allow_html=True)

        # ── Group Stage ───────────────────────────────────────────────
        if len(group_sched) > 0:
            for match_date, date_group in group_sched.groupby("local_date", sort=True):
                date_label = pd.Timestamp(match_date).strftime("%A, %B %d")
                match_count = len(date_group)
                st.markdown(
                    f"<div style='margin:1.5rem 0 0.8rem 0;'><p style='font-family:Bebas Neue,sans-serif; "
                    f"font-size:1.3rem; color:#ffffff; letter-spacing:0.08em; margin:0; "
                    f"border-left:3px solid #444; padding-left:0.7rem;'>{date_label} "
                    f"<span style='font-family:Barlow,sans-serif; font-size:0.8rem; color:#666; "
                    f"font-weight:400; margin-left:0.8rem;'>{match_count} match{'es' if match_count > 1 else ''}"
                    f"</span></p></div>",
                    unsafe_allow_html=True
                )
                for _, row in date_group.iterrows():
                    render_schedule_row(row)

        # ── Knockout Stage ────────────────────────────────────────────
        if len(knockout_sched) > 0:
            st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
            st.markdown("""
                <p style='font-family:Bebas Neue,sans-serif; font-size:1.8rem; 
                color:#ffffff; letter-spacing:0.1em; margin:1rem 0 0.5rem 0;
                border-left:4px solid #f0c040; padding-left:0.8rem;'>
                🏆 Knockout Stage</p>
            """, unsafe_allow_html=True)

            knockout_sched = knockout_sched.copy()
            knockout_sched["stage_order"] = knockout_sched["stage"].str.lower().map(STAGE_ORDER_MAP)
            knockout_sched = knockout_sched.sort_values(["stage_order", "local_date"])

            for _, stage_group in knockout_sched.groupby("stage_order", sort=True):
                actual_stage_name = stage_group["stage"].iloc[0]
                st.markdown(
                    f"<p style='font-family:Bebas Neue,sans-serif; font-size:1.3rem; "
                    f"color:#f0c040; letter-spacing:0.08em; margin:1.2rem 0 0.5rem 0; "
                    f"border-left:3px solid #f0c040; padding-left:0.6rem;'>"
                    f"{actual_stage_name.upper()}</p>",
                    unsafe_allow_html=True
                )
                for _, row in stage_group.iterrows():
                    render_schedule_row(row)

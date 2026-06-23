import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import requests 
import urllib3
import ssl
from streamlit_autorefresh import st_autorefresh 

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

@st.cache_data(ttl=60)
def load_data():
    df = pd.read_csv("data/final/FIFA_WC_2026_data.csv")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", mixed = True)
    return df

df = load_data()
print(df[df["match_id"].isin([1,2])][["match_id","date","time","category"]].to_string())

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
# ── Timezone detection ─────────────────────────────────────────────────────────
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

def get_flag_b64(team_name):
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
        return f"<img src='data:image/png;base64,{data}' style='height:28px; width:42px; object-fit:cover; border-radius:3px; vertical-align:middle; margin:0 4px;'>"
    except Exception:
        return f"<span style='color:#666; font-size:0.9rem;'>[{team_name}]</span>"
    
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
</style>
""", unsafe_allow_html=True)

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
                f"<div class='sb-body'>"
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

all_teams = sorted([t for t in df["team1"].unique() if t not in 
                   ["TBD","1A","1B","1C","1D","1E","1F","1G","1H",
                    "1I","1J","1K","1L","2A","2B","2C","2D","2E",
                    "2F","2G","2H","2I","2J","2K","2L"] and 
                    not str(t).startswith(("3","W","L"))])

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


def render_card(row, favorite_team=None, rank=None):
    category = str(row["category"])
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["TBD"])
    short_reason, extended_reason = parse_reason(row["reason"])
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
    flag1 = get_flag_b64(row["team1"])
    flag2 = get_flag_b64(row["team2"])
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
    html += "<div style='font-family:Bebas Neue,sans-serif; font-size:2rem; letter-spacing:0.08em; color:#111111; margin:0.3rem 0; line-height:1.1;'>" + flag1 + " " + team1 + " vs " + team2 + " " + flag2 + "</div>"
    html += "<div style='font-size:0.85rem; color:#444444; margin-top:0.4rem; font-weight:500;'>📅 " + date_str + " &nbsp;·&nbsp; 🕐 " + time_str + " " + USER_TZ_LABEL + " &nbsp;·&nbsp; 📍 " + venue + "</div>"

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

today_matches = df[
    (df["match_datetime"] > NOW) &           # strictly future only
    (df["match_datetime"] <= next_24h) &
    (df["category"] != "TBD") &
    (df["category"].isin(selected_categories)) &
    (df["winner"].fillna("") == "")          # not already finished
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
    active_tabs = ["schedule"]
else:
    tab_standings, tab_schedule = st.tabs([
        "📊 Group Standings",
        "📅 Fixtures & Results"
    ])
    active_tabs = ["standings", "schedule"]

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
                            flag = get_flag_b64(team)
                            gd_str = f"+{stats['gd']}" if stats['gd'] > 0 else str(stats['gd'])

                            group_html += (
                                f"<div style='background:{bg}; border:1px solid {border}; "
                                f"border-radius:8px; padding:0.5rem 0.75rem; margin-bottom:0.4rem; "
                                f"font-family:Barlow,sans-serif;'>"
                                f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                                f"<div style='display:flex; align-items:center; gap:6px;'>"
                                f"<span style='color:{rank_color}; font-weight:700; font-size:0.85rem; min-width:16px;'>{rank_idx}</span>"
                                f"{flag}"
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
        schedule_df = schedule_df[schedule_df["category"].isin(selected_categories)]

    if schedule_stage != "All Stages":
        schedule_df = schedule_df[schedule_df["stage"] == schedule_stage]

    schedule_df["local_date"] = schedule_df["match_datetime"].apply(
        lambda dt: dt.astimezone(user_tz).date()
    )

    if len(schedule_df) == 0:
        st.markdown("<p style='font-family:Barlow,sans-serif; color:#888; text-align:center; padding:2rem;'>No matches found with current filters.</p>", unsafe_allow_html=True)
    else:
        for match_date, date_group in schedule_df.groupby("local_date", sort=True):
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
                        st.markdown(
                            f"<p style='font-family:Bebas Neue,sans-serif; font-size:1.3rem; "
                            f"color:#ffffff; margin:0.2rem 0; letter-spacing:0.06em;'>"
                            f"{get_flag_b64(row['team1'])} {row['team1']} vs {row['team2']} {get_flag_b64(row['team2'])}</p>",
                            unsafe_allow_html=True
                        )
                        st.caption(f"📍 {row['venue']}  ·  {row['group'] if pd.notna(row['group']) else row['stage']}")
                        if short_reason and short_reason != "No preview available.":
                            st.caption(f"_{short_reason}_")
                    with right:
                        local_dt = row["match_datetime"].astimezone(user_tz)
                        local_time = local_dt.strftime("%H:%M")
                        date_display = local_dt.strftime("%b %d")
                        if result_text:
                            s1 = str(row['score_team1']).split('.')[0]
                            s2 = str(row['score_team2']).split('.')[0]
                            winner_name = str(row['winner'])
                            result_label = "Draw" if winner_name == "Draw" else f"{winner_name} win"
                            st.markdown(
                                f"<p style='text-align:right; font-family:Barlow,sans-serif; "
                                f"font-size:1rem; color:#f0c040; font-weight:700; margin:0;'>"
                                f"{s1}–{s2}<br>"
                                f"<span style='font-size:0.72rem; color:#f0c040; font-weight:500;'>{result_label}</span><br>"
                                f"<span style='font-size:0.72rem; color:#666; font-weight:400;'>{date_display}</span></p>",
                                unsafe_allow_html=True
                            )

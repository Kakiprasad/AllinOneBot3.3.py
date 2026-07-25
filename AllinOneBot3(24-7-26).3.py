import cloudscraper
import requests
import time
import re
import os
import sys
import pytz
import gc
import feedparser
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from deep_translator import GoogleTranslator
from google import genai
from apscheduler.schedulers.background import BackgroundScheduler
import html
import pymongo

# --- SYSTEM ENCODING ---
sys.stdout.reconfigure(encoding='utf-8')

# --- టైమ్‌ゾーン సెటప్ ---
IST = pytz.timezone("Asia/Kolkata")
US = pytz.timezone("US/Eastern")
EU = pytz.timezone("Europe/Berlin")
JP = pytz.timezone("Asia/Tokyo")
HK = pytz.timezone("Asia/Hong_Kong")

# ==========================================================
# 🔍 LOGGING & CORE UTILITIES (ముందే ఉండాలి)
# ==========================================================
def log(msg, level="INFO"):
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] [{level}] {msg}")

# ==========================================================
# ⚙️ CONFIGURATION & BOT INTERFACE
# ==========================================================
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# 🎯 డ్యూయల్ API కీలు (1: సమ్మరీకి, 2: ఆన్-డిమాండ్ AI ఏజెంట్‌కి)
GEMINI_API_KEY_1 = os.getenv("GEMINI_API_KEY_1")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")

# ==========================================================
# 🍃 MONGODB DATABASE SETUP
# ==========================================================
MONGO_URI = os.getenv("MONGODB_URI")

try:
    mongo_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo_client["telegram_bot_db"]
    
    sent_links_col = db["sent_links"]
    news_store_col = db["news_store"]
    
    mongo_client.admin.command('ping')
    log("✅ MongoDB Connection Successful!")
except Exception as e:
    log(f"❌ MongoDB Connection Failed: {e}", "ERROR")

if not TOKEN or not CHAT_ID:
    print("⚠️ Warning: Bot Token లేదా Chat ID సెట్ చేయబడలేదు! దయచేసి చెక్ చేయండి.")

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)
MODEL_NAME = "gemini-2.5-flash" 

# జెమిని క్లయింట్లు (డ్యూయల్)
client_1 = genai.Client(api_key=GEMINI_API_KEY_1) if GEMINI_API_KEY_1 else None
client_2 = genai.Client(api_key=GEMINI_API_KEY_2) if GEMINI_API_KEY_2 else None

# ==========================================================
# 📊 DATA STORES & WATCHLISTS
# ==========================================================
rss_news_store = []
sent_links = set()
sent_news = set()
sent_alerts = {}
sudden_move_sent = {}
gap_alert_sent = {}
pinned_messages_store = []
last_reset_date = datetime.now(IST).date()

# 📦 AI Agent విశ్లేషణలు మరియు Weekly Reports కోసం ఇన్-మెమొరీ వాల్ట్
analysis_vault = {}

MAX_NEWS = 5000
CLEAR_COUNT = 1000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

## 🔴 చంటి గారి 100% పక్కా మాస్టర్ వాచ్‌లిస్ట్
MY_WATCHLIST = [
    "ANANTRAJ", "ANANT RAJ", "APOLLO", "APOLLO HOSPITALS", "BBOX", "BLACK BOX", 
    "BEL", "BHARAT ELECTRONICS", "BHARTIARTL", "BHARTI AIRTEL", "AIRTEL", 
    "BLS", "BLS INTERNATIONAL", "BLUECLOUD", "BLUE CLOUD", "BSE", "BSE LTD",
    "CDSL", "CGPOWER", "CG POWER", "CHOLAFIN", "CHOLAMANDALAM", "CLEANMAX", "CLEAN MAX",
    "COFORGE", "DIXON", "DIXON TECH", "E2E", "E2E NETWORKS", "EIEL", "Enviro Infra Engineers Ltd", 
    "ETERNAL", "FRACTAL", "GMDCLTD", "GMDC", "GOKEX", "GOKALDAS EXPORTS", 
    "GROWW", "GRSE", "EMMVEE", "EMMVEE SOLAR", "EMMVEE PHOTOVOLTAIC", 
    "HAL", "HINDUSTAN AERONAUTICS", "HDFCBANK", "HDFC BANK", "HINDCOPPER", "HINDUSTAN COPPER",
    "IDEA", "VODAFONE IDEA", "IDFCFIRSTB", "IDFC FIRST", "INDIGO", "INTERGLOBE AVIATION",
    "INFY", "INFOSYS", "INTERARCH", "ITC", "ITCHOTELS", "ITC HOTELS", "JKTYRE", "JK TYRE",
    "JSWSTEEL", "JSW STEEL", "KALAMANDIR", "SAI SILKS", "KALYANKJIL", "KALYAN JEWELLERS", 
    "KAYNES", "KAYNES TECH", "KEC", "KEC INTERNATIONAL",
    "LEMONTREE", "LEMON TREE", "LENSKART", "LGEINDIA", "LG ELECTRONICS", "LT", "L&T", 
    "LARSEN", "M&M", "MAHINDRA", "MAZDOCK", "MAZAGON DOCK", "MCX", "MEESHO", 
    "NESTLEIND", "NESTLE", "NESTLE INDIA", "NH", "NARAYANA HRUDAYALAYA", 
    "NTPC", "NYKAA", "FSN E-COMMERCE","OLAELEC", "OLA ELECTRIC", "POLYCAB", "PROTEAN", 
    "RELIANCE", "RIL", "PROTEAN eGOV TECHNOLOGIES", "PROTEAN eGOV", "RELIANCE INDUSTRIES", "RELIANCE JIO", "RELIANCE RETAIL", 
    "SAILIFE", "SAI LIFE", "SBIN", "SBI", "STATE BANK", "SEPC", "SHAKTIPUMP", "SHAKTI PUMPS",
    "SHRIRAMFIN", "SHRIRAM FINANCE", "SJS", "SJS ENTERPRISES", "SKIPPER", "SONACOMS", "SONA BLW",
    "SUZLON", "SUZLON ENERGY", "TATASTEEL", "TATA STEEL", "TCS", "TIPSMUSIC", "TIPS MUSIC",
    "TITAN", "TITAN COMPANY", "TVSMOTOR", "TVS MOTOR", "URBANCO", "URBAN COMPANY",
    "WABAG", "VA TECH WABAG", "WAAREEENER", "WAAREE ENERGIES", "YATHARTH", "YATHARTH HOSPITAL", 
    "YATRA", "YATRA ONLINE", "ZAGGLE", "ZAGGLE PREPAID", "bhel", "భెల్", "bharat heavy electricals", "bharat heavy electricals limited",
    "physicswallah", "physics wallah", "pwl ", "physicswallah limited"
]

MARKET_KEYWORDS = [
    "rbi rate", "repo rate", "rate cut", "rate hike", "fed decision", "fomc", "interest rate", "rate",
    "warsh", "kevin warsh", "malhotra", "sanjay malhotra", "shaktikanta", "shaktikanta das", "monetary policy", 
    "వడ్డీ రేటు", "రెపో రేటు",
    "budget 2026", "union budget", "budget", "gst rate change", "government policy", "corporate tax",
    "cabinet decision", "import duty", "export ban", "government decision", "govt decision", "gdp growth", 
    "us gdp", "cpi inflation", "india gdp", "inflation", "gdp", "cabinet meeting",
    "ప్రభుత్వ నిర్ణయం", "బడ్జెట్", "ద్రవ్యోల్బణం",
    "war", "strike", "strikes", "attack", "attacks", "military", "sanctions", "iran", "us-iran",
    "crude", "oil", "brent", "opec", "omc", "dollar", "crude spike", "above $", "surge",
    "యుద్ధం", "దాడి", "దాడులు", "సైనిక", "ఆంక్షలు", "ఇరాన్", "చమురు", "క్రూడ్", "డాలర్", "crude oil",
    "market crash", "circuit breaker", "scam", "sebi ban", "emergency", "urgent", "breaking",
    "అత్యవసర", "rbi mpc", "mpc", "rupee", "రూపాయి"
]

IMPORTANT_KEYWORDS = MARKET_KEYWORDS + [stock.lower() for stock in MY_WATCHLIST]

TIMINGS = {
    "GIFT Nifty": ("06:30", "02:45"),
    "Nikkei (Japan)": ("05:30", "11:30"),
    "KOSPI (S.Korea)": ("05:30", "12:00"),
    "Hang Seng (HK)": ("06:45", "13:30"),
    "DAX (Germany)": ("12:30", "21:00"),
    "FTSE (UK)": ("12:30", "21:00"),
    "Dow Jones (US)": ("19:00", "01:30"),
    "Nasdaq (US)": ("19:00", "01:30"),
    "S&P 500 (US)": ("19:00", "01:30"),
    "Gold (Commodity)": ("04:30", "03:30"),
    "Silver (Commodity)": ("04:30", "03:30"),
    "Brent Oil": ("05:30", "03:30"),
    "WTI Crude (US Oil)": ("03:30", "02:30"),
    "US 10Y Yield": ("18:30", "03:30"),
    "Bitcoin (Daily)": ("05:30", "05:29"),
}

symbols = {
    "GIFT Nifty": "^NSEI", 
    "Dow Jones (US)": "^DJI",
    "Nasdaq (US)": "^IXIC",
    "S&P 500 (US)": "^GSPC",
    "Nikkei (Japan)": "^N225",
    "KOSPI (S.Korea)": "^KS11",
    "Hang Seng (HK)": "^HSI",
    "DAX (Germany)": "^GDAXI",
    "FTSE (UK)": "^FTSE",
    "Gold (Commodity)": "GC=F",
    "Silver (Commodity)": "SI=F",
    "Brent Oil": "BZ=F",
    "WTI Crude (US Oil)": "CL=F",
    "Bitcoin (Daily)": "BTC-USD",
    "US 10Y Yield": "^TNX",
}

# ==========================================================
# 🛠️ TRANSLATION & CLEANING UTILITIES
# ==========================================================
def translate_to_telugu(text):
    if not text:
        return ""

    try:
        translator = GoogleTranslator(source="auto", target="te")
        text = text.replace(" || ", "\n")
        text = re.sub(
            r'([A-Z][A-Z0-9&\-\s]+:)',
            r'\n\1',
            text
        )

        lines = [x.strip() for x in text.split("\n") if x.strip()]
        translated = []

        for line in lines:
            try:
                translated.append(translator.translate(line))
            except:
                translated.append(line)

        return "\n".join(translated)

    except Exception:
        return text

def translate(text): return translate_to_telugu(text)

def safe_html_text(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def clean_html_tags(text):
    if not text: return ""
    return re.sub('<[^>]+>', '', text).strip()

def clean_news_title(title):
    if not title:
        return ""

    # 1. HTML ఎంటిటీలను క్లీన్ చేయడం
    title = html.unescape(title)
    title = title.replace("&nbsp;", " ").replace("\xa0", " ")
    
    # 2. 🆕 టైటిల్ లోపల వచ్చే లింకులను మరియు HTML ట్యాగ్‌లను పూర్తిగా తీసివేయడం
    title = re.sub(r'https?://\S+|www\.\S+', '', title)
    title = clean_html_tags(title)
    
    # 3. 🆕 చివరన అతుక్కునే సోర్స్ పేర్లను (- Investing.com వగైరా) కట్ చేసే మాస్టర్ రెజెక్స్
    sources_pattern = r"(Investing\.com|Moneycontrol\.com|Moneycontrol|CNBC-TV18|CNBC|Economic Times|ETMarkets\.com|Business Standard|Mint|Livemint|Reuters|NDTV Profit|ET NOW)"
    title = re.sub(rf"\s*[-–|]?\s*{sources_pattern}.*$", "", title, flags=re.IGNORECASE)

    # 4. చివర మిగిలిపోయిన హైఫన్‌లను తీసివేసి నీట్‌గా స్పేస్ ఇవ్వడం
    title = re.sub(r'\s*[-–|]\s*$', '', title)
    return ' '.join(title.split()).strip()

def check_if_important(text_to_check):
    if not text_to_check: return False
    lowercase_text = text_to_check.lower()
    for keyword in IMPORTANT_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', lowercase_text): return True
    return False

def is_duplicate_news(new_title):
    if not new_title: return False
    def clean_for_compare(t): return set(re.findall(r'\w+', t.lower()))
    new_words = clean_for_compare(new_title)
    if not new_words: return False
    now = datetime.now(IST)
    cutoff = now - timedelta(minutes=15)
    for n in reversed(rss_news_store):
        if isinstance(n, dict) and n.get('time') >= cutoff:
            existing_words = clean_for_compare(n.get('title', ''))
            if not existing_words: continue
            intersection = new_words.intersection(existing_words)
            smaller_len = min(len(new_words), len(existing_words))
            if smaller_len > 0:
                match_percentage = (len(intersection) / smaller_len) * 100
                if match_percentage >= 80: return True
    return False

# 🆕 MongoDB నుండి పాత లింకులను లోడ్ చేసే ఫంక్షన్
def load_sent_links_from_db():
    try:
        links = set()
        for doc in sent_links_col.find({}, {"link": 1}):
            if "link" in doc:
                links.add(doc["link"])
        log(f"📦 Loaded {len(links)} sent links from MongoDB.")
        return links
    except Exception as e:
        log(f"❌ Error loading links from DB: {e}", "ERROR")
        return set()

# 🆕 కొత్త లింక్‌ను MongoDB లో దాచే ఫంక్షన్
def save_link_to_db(link):
    try:
        sent_links_col.update_one(
            {"link": link},
            {"$set": {"link": link, "timestamp": datetime.now(IST)}},
            upsert=True
        )
    except Exception as e:
        log(f"❌ Error saving link to DB: {e}", "ERROR")

# ==========================================================
# 💬 TELEGRAM MESSAGE SENDING HANDLERS
# ==========================================================
def send_long_message(chat_id, text, parse_mode='HTML'):
    if len(text) <= 3800:
        try: bot.send_message(chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception as e:
            log(f"⚠️ HTML Parse Error, sending plain text: {e}", "WARNING")
            bot.send_message(chat_id, clean_html_tags(text))
        return

    lines = text.split('\n\n')
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 2 > 3800:
            try: bot.send_message(chat_id, current_chunk, parse_mode=parse_mode, disable_web_page_preview=True)
            except: bot.send_message(chat_id, clean_html_tags(current_chunk))
            current_chunk = line + '\n\n'
        else: current_chunk += line + '\n\n'
    if current_chunk:
        try: bot.send_message(chat_id, current_chunk, parse_mode=parse_mode, disable_web_page_preview=True)
        except: bot.send_message(chat_id, clean_html_tags(current_chunk))

def safe_send(msg, chat_id=CHAT_ID, parse_mode="HTML", disable_preview=True):
    MAX_LENGTH = 4000
    parts = [msg[i:i+MAX_LENGTH] for i in range(0, len(msg), MAX_LENGTH)] if len(msg) > MAX_LENGTH else [msg]
    for part in parts:
        for i in range(3):
            try:
                bot.send_message(chat_id, part, parse_mode=parse_mode, disable_web_page_preview=disable_preview)
                break
            except Exception as e:
                log(f"Retry {i+1} in safe_send: {e}", "WARNING")
                time.sleep(3)

def get_image_url(entry):
    try:
        if hasattr(entry, 'media_content') and entry.media_content:
            url = entry.media_content[0]['url']
            if str(url).startswith('http'): return url
        summary_raw = entry.get('summary') or entry.get('description') or ""
        soup = BeautifulSoup(str(summary_raw), 'html.parser')
        img = soup.find('img')
        if img and img.get('src'):
            url = img['src']
            if str(url).startswith('http'): return url
        if hasattr(entry, 'links'):
            for link in entry.links:
                if 'image' in link.get('type', ''): return link.get('href')
    except: return None
    return None

def manage_memory():
    global rss_news_store
    if len(rss_news_store) > MAX_NEWS:
        rss_news_store = rss_news_store[CLEAR_COUNT:]
        log(f"✅ Memory cleaned.")

# ==========================================================
# 🧠 DUAL GEMINI AI UTILITY
# ==========================================================
def safe_gemini(prompt):
    active_client = client_1 or client_2
    if not active_client: return "Gemini AI Key Error"
    for i in range(3):
        try:
            response = active_client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return response.text
        except Exception as e:
            log(f"Gemini API Retry {i+1}: {e}", "WARNING")
            time.sleep(3)
    return "AI అందుబాటులో లేదు"

def safe_gemini_agent(news_text):
    active_client = client_2 or client_1
    if not active_client: return None

    prompt = f"""meru oka Senior Global Research Analyst Indian Stock Market mariyu Global Markets lo 50+ samvatsarala atyantha anubavam unna oka Market Legend meru. meru vandala kotla (Multi-Crore) institutional funds ni manage chese highly successful Professional Value Investor mariyu Macro Strategist . market cycles, sector rotations, mariyu smart money (FIIs/DIIs) yokka prathiey okka kadalikanu meru mundugaane anchana veyagalaru.

ee parinaamanni oka Top-Level Fund Manager mind-set tho chala pragalbhamga vishlesinchandi: {news_text}

CRITICAL RULES FOR GOOGLE SEARCH & ACCURACY:
1. USE LIVE SEARCH: ఈ వార్త నిజంగానే సెక్టార్ లేదా మార్కెట్ చేంజ్ తెచ్చేదైతే... వెంటనే గూగుల్ సెర్చ్ ఉపయోగించి ఆ సెక్టార్/మార్కెట్ యొక్క గత 2-3 సంవత్సరాల హిస్టరీ, ప్రస్తుత పరిస్థితి మరియు లేటెస్ట్ మేనేజ్‌మెంట్/గవర్నమెంట్ కామెంటరీ డేటాను సేకరించు.
2. FUTURE MARKET OUTLOOK: ఈ పరిణామం వల్ల రాబోయే రోజుల్లో FIIs, DIIs మరియు బిగ్ ప్లేయర్స్ సెంటిమెంట్ ఎలా ఉండబోతోంది, ఎలాంటి ట్రెండ్ రాబోతోంది అనేది స్పష్టంగా వివరించు.
3. NO HALLUCINATION: నీ సొంత ఊహలతో నంబర్లను లేదా పర్సంటేజీలను సృష్టించవద్దు. గూగుల్ సెర్చ్ లో దొరికిన కచ్చితమైన ఫ్యాక్ట్స్ ఆధారంగానే విశ్లేషణ రాయి.

OUTPUT FORMAT:
ముందుగా [ONE_LINE] అనే టాగ్ పెట్టి కేవలం ఒకే ఒక్క లైన్ లో క్విక్ విశ్లేషణ రాయి.
ఆ తర్వాత [DEEP_ANALYSIS] అనే టాగ్ పెట్టి, ఒక బిగ్ ఇన్వెస్టర్ మైండ్‌సెట్ తో దీని వెనుక ఉన్న అసలు కారణం ఏంటి, మార్కెట్/సెక్టార్ పై దీని దీర్ఘకాలిక ప్రభావం ఎలా ఉంటుంది అనేది చాలా అద్భుతమైన, సుదీర్ఘమైన పూర్తి తెలుగు విశ్లేషణను కింద వివరించు సర్."""

    try:
        response = active_client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config={"tools": [{"google_search": {}}]}
        )
        return response.text.strip()
    except Exception as e:
        log(f"AI Agent Error: {e}", "ERROR")
        return None

# ==========================================================
# 📈 MARKET DATA ENGINE & GAP ALERTS
# ==========================================================
def is_market_open(name):
    now_ist = datetime.now(IST)
    if "Bitcoin" in name or "BTC" in name: return "🟢"
    if any(x in name for x in ["GIFT Nifty", "WTI Crude", "Brent", "Gold", "Silver"]): return "🟢"

    mapping = {
        "Nikkei": (JP, "09:00", "15:00"), "Hang Seng": (HK, "09:30", "16:00"),
        "KOSPI": (JP, "09:00", "15:30"), # 🆕 KOSPI Timing
        "DAX": (EU, "09:00", "17:30"), "FTSE": (EU, "08:00", "16:30"),
        "Dow": (US, "09:30", "16:00"), "Nasdaq": (US, "09:30", "16:00"), 
        "S&P": (US, "09:30", "16:00"), "10Y": (US, "08:00", "17:00")
    }
    for key, (tz, start, end) in mapping.items():
        if key in name:
            now_local = now_ist.astimezone(tz).time()
            if datetime.strptime(start, "%H:%M").time() <= now_local < datetime.strptime(end, "%H:%M").time(): return "🟢"
            return "🔴"
    return "🔴" 

def get_data(symbol):
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}", headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if (price is None or price == 0) and "indicators" in result:
            closes = [c for c in result["indicators"]["quote"][0].get("close", []) if c]
            if closes: price = closes[-1]
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        return price, prev_close
    except: return None, None 

def check_gap_alert(name, price, prev_close, current_date):
    if not price or not prev_close: return
    gap_percent = ((price - prev_close) / prev_close) * 100
    gap_key = f"{name}_{current_date}_gap"
    if gap_key not in gap_alert_sent and abs(gap_percent) >= 1.0:
        direction = "📈 **GAP UP**" if gap_percent > 0 else "📉 **GAP DOWN**"
        safe_send(f"🚨 <b>GAP ALERT!</b>\n\n{name}\n{direction}: {gap_percent:+.2f}%\nCurrent: {price:.2f} | Prev Close: {prev_close:.2f}")
        gap_alert_sent[gap_key] = True 

# ==========================================================
# ⏱️ NIGHT TIME PULSE GENERATOR
# ==========================================================
def send_night_pulse_report():
    log("⏰ Automatically generating Night Market Pulse Report (8 PM to 6 AM)...")
    try:
        now = datetime.now(IST)
        cutoff_time = now - timedelta(hours=10)
        
        recent_important_news = []
        for n in rss_news_store:
            if isinstance(n, dict) and n.get('time') >= cutoff_time and n.get('type') == "NORMAL":
                raw_title = n.get('full_text', '').split("    ")[0]
                subject_match = re.search(r'\b[a-zA-Z0-9\s\&]+', raw_title)
                subject_title = subject_match.group(0).strip() if subject_match else "Market Update"
                
                news_block = (
                    f"<b>{subject_title}:-</b>\n"
                    f"  {safe_html_text(n.get('title', ''))}\n"
                    f"<b>సమ్మరీ:-</b>\n"
                    f"  {safe_html_text(n.get('desc', ''))}"
                )
                recent_important_news.append(news_block)

        if not recent_important_news:
            no_news_msg = "⚡ <b>🎯 NIGHT MARKET PULSE (06:00 AM)</b> ⚡\n📌 <b>మార్కెట్ అప్‌డేట్:</b> నిన్న రాత్రి 8:00 PM నుండి ఈరోజు ఉదయం 6:00 AM వరకు కీలకమైన వార్తలు ఏవీ రాలేదు సార్."
            bot.send_message(CHAT_ID, no_news_msg, parse_mode='HTML')
            log("📌 Night Pulse Report Completed: No news recorded.")
            return

        recent_important_news = list(dict.fromkeys(recent_important_news))
        pulse_body = "\n\n🔹🔹🔹\n\n".join(recent_important_news)
        full_report_msg = f"⚡ <b>🎯 NIGHT MARKET PULSE (06:00 AM)</b> ⚡\n(రాత్రి 08:00 PM నుండి ఉదయం 6:00 AM వరకు వచ్చిన కీలకమైన వార్తలు)\n\n{pulse_body}"
        
        send_long_message(CHAT_ID, full_report_msg, parse_mode='HTML')
        log(f"📌 Night Pulse Report Sent Successfully. Total items: {len(recent_important_news)}")
    except Exception as e: log(f"❌ Night Pulse Error: {e}", "ERROR")

# ==========================================================
# 🔄 LIVE RSS LOOPS & FEEDS WITH "ANALYZE WITH AI" BUTTON
# ==========================================================
RSS_FEEDS = {
    "CNBC": "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/latest.xml",
    "Investing_Main_News": "https://news.google.com/rss/search?q=site:investing.com+intitle:(%22Fed%22+OR+%22War%22+OR+%22Crude%22+OR+%22Markets%22+OR+%22Inflation%22+OR+%22Economy%22)&hl=en-IN&gl=IN&ceid=IN:en"
}

X_RSS_FEEDS = {
    "ET NOW (X)": "https://nitter.net/ETNOWlive/rss",
    "Redbox X": "https://nitter.net/REDBOXINDIA/rss" 
}

def clean_x_text(text):
    text = text.replace("||", "\n")
    junk = [r'http\S+', r'www\.\S+', r'@\w+', r'#\w+', r'⤵️']
    for p in junk:
        text = re.sub(p, '', text, flags=re.IGNORECASE)
    return clean_html_tags(text).strip()

sent_links = load_sent_links_from_db()

def fetch_normal_rss():
    log("🌍 NORMAL RSS LOOP STARTED...")
    while True:
        for name, url in RSS_FEEDS.items():
            for attempt in range(3):
                try:
                    res = requests.get(url, headers=HEADERS, timeout=25)
                    if res.status_code != 200:
                        continue
                        
                    feed = feedparser.parse(res.content)
                    if not feed.entries: 
                        break

                    for entry in feed.entries[:10]:
                        link = entry.get("link", "").strip()
                        raw_title = entry.get("title", "")
                        
                        clean_title = clean_news_title(raw_title)
                        tel_title = translate(clean_title)
                        tel_title = clean_news_title(tel_title)

                        summary_raw = entry.get("summary") or entry.get("description") or ""
                        clean_desc = clean_news_title(summary_raw)
                        tel_desc = translate(clean_desc[:800])
                        tel_desc = clean_news_title(tel_desc)

                        if not link or link in sent_links or is_duplicate_news(tel_title) or is_duplicate_news(clean_title): 
                            continue
                        
                        sent_links.add(link)
                        save_link_to_db(link)

                        unique_id = int(time.time() * 1000)
                        analyze_btn_id = f"ai_analyze_{unique_id}"
                        full_text_to_analyze = f"{clean_title} {clean_desc}"
                        
                        analysis_vault[analyze_btn_id] = {
                            "title": tel_title,
                            "english_title": clean_title,
                            "source": name,
                            "full_text": full_text_to_analyze,
                            "unique_id": unique_id,
                            "link": link
                        }

                        msg = (
                            f"📌 <b>{safe_html_text(tel_title)}</b>\n\n"
                            f"🇬🇧 <b>English Title:</b>\n{safe_html_text(clean_title)}\n\n"
                            f"🇮🇳 <b>తెలుగు సమ్మరీ:</b>\n{safe_html_text(tel_desc)}\n\n"
                            f"🌐 <b>{safe_html_text(name)}</b>\n"
                            f'🔗 <a href="https://translate.google.com/translate?sl=en&tl=te&u={link}">Read More in Telugu</a> | <a href="{link}">English Original</a>'
                        )

                        markup = InlineKeyboardMarkup()
                        analyze_btn = InlineKeyboardButton(text="🧠 Analyze with AI", callback_data=analyze_btn_id)
                        markup.add(analyze_btn)

                        ist_now = datetime.now(IST)
                        rss_news_store.append({"time": ist_now, "type": "NORMAL", "source": name, "title": tel_title, "desc": tel_desc, "link": link, "full_text": clean_title + " " + clean_desc})
                        manage_memory()

                        try:
                            bot.send_message(CHAT_ID, msg, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=False)
                        except Exception as e: 
                            log(f"❌ Telegram error in Normal RSS: {e}", "ERROR")
                        time.sleep(1)
                    
                    break 

                except requests.exceptions.Timeout:
                    log(f"⚠️ Timeout on {name} (Attempt {attempt+1}/3). Retrying...", "WARNING")
                    time.sleep(2)
                except Exception as e:
                    log(f"❌ RSS Error {name}: {e}", "ERROR")
                    break
        time.sleep(120)

def fetch_x_rss():
    log("🐦 X RSS STARTED...")
    scraper = cloudscraper.create_scraper()
    while True:
        for name, url in X_RSS_FEEDS.items():
            try:
                res = scraper.get(url, timeout=20)
                if res.status_code != 200: continue
                feed = feedparser.parse(res.content)

                for entry in feed.entries[:5]:
                    link = entry.get("link", "").strip()

                    raw_title = entry.get("title", "")
                    title = clean_x_text(raw_title)
                    tel_title = translate(title)

                    if not link or link in sent_links or is_duplicate_news(tel_title) or is_duplicate_news(title): continue
                    
                    sent_links.add(link)
                    save_link_to_db(link)
                    
                    is_important = check_if_important(title) or check_if_important(tel_title)
                    g_trans_url = f"https://translate.google.com/translate?sl=en&tl=te&u={link}"

                    header = f"🚀 <b>{safe_html_text(name)} Update</b>\n\n"
                    msg = f"{header}📌 <b>{safe_html_text(tel_title)}</b>\n\n🇬🇧 {safe_html_text(title)}\n\n🔗 <a href='{g_trans_url}'>Read More in Telugu</a> | <a href='{link}'>English Original</a>"
                    
                    unique_id = int(time.time() * 1000)
                    analyze_btn_id = f"ai_analyze_{unique_id}"
                    
                    analysis_vault[analyze_btn_id] = {
                        "title": tel_title,
                        "english_title": title,
                        "source": name,
                        "full_text": title,
                        "unique_id": unique_id,
                        "link": link
                    }

                    markup = InlineKeyboardMarkup()
                    analyze_btn = InlineKeyboardButton(text="🧠 Analyze with AI", callback_data=analyze_btn_id)
                    markup.add(analyze_btn)

                    ist_now = datetime.now(IST)
                    rss_news_store.append({"time": ist_now, "type": "X", "source": name, "title": tel_title, "link": link})
                    manage_memory()

                    image_url = get_image_url(entry)
                    try:
                        if image_url:
                            try: sent_msg = bot.send_photo(CHAT_ID, image_url, caption=msg[:1024], reply_markup=markup, parse_mode='HTML')
                            except Exception: sent_msg = bot.send_photo(CHAT_ID, image_url, caption=clean_html_tags(msg)[:1024], reply_markup=markup)
                        else:
                            sent_msg = bot.send_message(CHAT_ID, msg, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=False)
                            
                        # 🆕 పిన్ లాజిక్: ET NOW అలర్ట్ ముఖ్యమైనదైతే పిన్ చేయడం
                        if is_important and sent_msg:
                            bot.pin_chat_message(CHAT_ID, sent_msg.message_id, disable_notification=False)
                            pinned_messages_store.append({"message_id": sent_msg.message_id, "time": datetime.now(IST)})
                            log(f"📌 Pinned important ET NOW message ID: {sent_msg.message_id}")
                            
                    except Exception as e: log(f"❌ X Telegram Error: {e}", "ERROR")
                    time.sleep(2)
            except Exception as e: log(f"❌ X RSS Error {name}: {e}", "ERROR")
        time.sleep(120)

# ==========================================================
# 🎛️ CALLBACK LISTENER FOR AI AGENT & WEEKLY PAGINATION BUTTONS
# ==========================================================
@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    global analysis_vault
    msg_key = call.data
    
    try: bot.answer_callback_query(call.id)
    except: pass
    
    # 1. 🧠 "Analyze with AI" బటన్ నొక్కినప్పుడు
    if msg_key.startswith("ai_analyze_"):
        if msg_key in analysis_vault:
            vault_item = analysis_vault[msg_key]
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📌 <b>{vault_item['title']}</b>\n\n"
                     f"⏳ <i>జెమిని AI ప్రత్యక్ష మార్కెట్ డేటాతో విశ్లేషణ చేస్తోంది... దయచేసి కొద్దిసెకన్లు వేచి ఉండండి...</i>",
                parse_mode="HTML"
            )
            
            agent_output = safe_gemini_agent(vault_item['full_text'])
            
            if agent_output and "[DEEP_ANALYSIS]" in agent_output:
                parts = agent_output.split("[DEEP_ANALYSIS]")
                one_line_part = parts[0].replace("[ONE_LINE]", "").replace("HIGH_IMPACT", "").strip()
                deep_analysis_part = parts[1].strip()
                
                deep_analysis_part = re.sub(r'(\n\s*\d+[\.\)]\s*)', r'\n\n\1', deep_analysis_part)
                deep_analysis_part = re.sub(r'(\n\s*\*+\s*)', r'\n\n\1', deep_analysis_part)
                deep_analysis_part = re.sub(r'\n{3,}', '\n\n', deep_analysis_part)
                
                safe_one_line = safe_html_text(one_line_part)
                
                def split_analysis(text, size=3500):
                    return [text[i:i+size] for i in range(0, len(text), size)]
                
                report_parts = split_analysis(deep_analysis_part.strip())
                unique_id = vault_item['unique_id']
                
                view_id = f"view_{unique_id}"
                back_id = f"back_{unique_id}"
                
                short_telegram_msg = f"📢 <b>రీసెర్చ్ టీమ్ లైవ్ అలర్ట్</b>\n\n" \
                                     f"🗞️ <b>వార్త:</b> {vault_item['title']}\n" \
                                     f"🌐 <b>మూలం:</b> {vault_item['source']}\n" \
                                     f"💡 <b>క్విక్ వ్యూ:</b> {safe_one_line}"

                analysis_vault[view_id] = {
                    "title": vault_item['title'],
                    "source": vault_item['source'],
                    "parts": report_parts,
                    "original_text": short_telegram_msg,
                    "back_key": back_id
                }
                analysis_vault[back_id] = view_id

                markup = InlineKeyboardMarkup()
                view_btn = InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{unique_id}_0")
                markup.add(view_btn)
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=short_telegram_msg,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"📌 <b>{vault_item['title']}</b>\n\n"
                         f"❌ <i>క్షమించండి, ప్రస్తుతం AI విశ్లేషణ అందుబాటులో లేదు.</i>",
                    parse_mode="HTML"
                )

    # 2. 📄 పేజినేషన్ బటన్లు (Previous, Next, Pages) - లైవ్ వార్తలకు & Weekly రిపోర్ట్ కి రెండింటికీ పనిచేస్తుంది
    elif msg_key.startswith("page_"):
        parts_key = msg_key.split("_")
        unique_id = parts_key[1]
        current_page = int(parts_key[2])
        vault_id = f"view_{unique_id}"
        
        if vault_id in analysis_vault:
            vault_data = analysis_vault[vault_id]
            report_parts = vault_data["parts"]
            total_pages = len(report_parts)
            page_content = report_parts[current_page]
            
            full_report = f"📊 <b>పూర్తి రీసెర్చ్ నివేదిక (Page {current_page + 1}/{total_pages})</b>\n\n" \
                          f"🗞 <b>టైటిల్:</b> {vault_data['title']}\n" \
                          f"--------------------------------------------------\n\n" \
                          f"{page_content.strip()}"
            
            markup = InlineKeyboardMarkup()
            row_btns = []
            if current_page > 0:
                row_btns.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"page_{unique_id}_{current_page - 1}"))
            if current_page < total_pages - 1:
                row_btns.append(InlineKeyboardButton(text="➡️ Next", callback_data=f"page_{unique_id}_{current_page + 1}"))
            
            if row_btns: markup.row(*row_btns)
            markup.add(InlineKeyboardButton(text="🏠 Back to Alert", callback_data=vault_data['back_key']))
            
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=full_report, reply_markup=markup, parse_mode="HTML")

    # 3. 🏠 'Back to Alert' బటన్
    elif msg_key.startswith("back_"):
        if msg_key in analysis_vault:
            view_key = analysis_vault[msg_key]
            if view_key in analysis_vault:
                vault_data = analysis_vault[view_key]
                parts_key = view_key.split("_")[1]
                
                original_markup = InlineKeyboardMarkup()
                original_markup.add(InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{parts_key}_0"))
                
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=vault_data['original_text'], reply_markup=original_markup, parse_mode="HTML")

# ==========================================================
# 📊 GLOBAL MARKET LIVE TABLE LOGIC
# ==========================================================
def send_market_table():
    log("📊 Automatically broadcasting Global Market Live Table...")
    table_content = f"{'-' * 52}\n"
    table_content += f"{'Mkt':<14} {'Price':>9} {'+/-Pts':>8} {'%':>6} {'Trnd':>4}\n"
    table_content += f"{'-' * 52}\n"
    current_date = datetime.now(IST).date()
    
    for name, sym in symbols.items():
        price, prev_close = get_data(sym)
        if price and prev_close:
            diff = price - prev_close
            change = (diff / prev_close) * 100
            check_gap_alert(name, price, prev_close, current_date)
            trend = "📈" if change > 0.3 else ("📉" if change < -0.3 else "➖")
            status = is_market_open(name)
            short_name = name.split(' (')[0][:11]
            table_content += f"{status}{short_name:<12} {price:>9.1f} {diff:>8.1f} {change:>5.1f}% {trend:>2}\n"
    try: safe_send(f"📊 <b>Global Market Live</b>\n<pre>{table_content}</pre>")
    except Exception as e: print(e)

def calculate_historical_target_time(hour_input):
    now = datetime.now(IST)
    target = now.replace(hour=hour_input, minute=0, second=0, microsecond=0)
    if hour_input >= now.hour: target = target - timedelta(days=1)
    return target

def main_loop():
    global last_reset_date
    while True:
        try:
            now_ist_str = datetime.now(IST).strftime("%H:%M")
            current_date = datetime.now(IST).date()
            if current_date > last_reset_date:
                sent_alerts.clear()
                sudden_move_sent.clear()
                gap_alert_sent.clear()
                last_reset_date = current_date
                log("🔄 కొత్త రోజు ప్రారంభమైంది: డేటా రీసెట్ చేయబడింది.")

            for m_name, (o_time, _) in TIMINGS.items():
                alert_id = f"{m_name}_{current_date}"
                if now_ist_str == o_time and alert_id not in sent_alerts:
                    safe_send(f"🔔 <b>MARKET OPEN ALERT</b>\n\n🚀 {m_name} ప్రారంభమైంది! (IST: {o_time})")
                    sent_alerts[alert_id] = True 

            for name, sym in symbols.items():
                if is_market_open(name) == "🟢":
                    price, prev_close = get_data(sym)
                    if price and prev_close:
                        diff = price - prev_close
                        change = (diff / prev_close) * 100
                        check_gap_alert(name, price, prev_close, current_date) 
                        if abs(change) >= 1.50 and f"{name}_{current_date}_mv" not in sudden_move_sent:
                            safe_send(f"🚨 <b>VOLATILITY ALERT!</b>\n{name}: {change:.2f}% భారీ మార్పు!")
                            sudden_move_sent[f"{name}_{current_date}_mv"] = True 
        except Exception as e: print(f"Error in global loop: {e}")
        gc.collect() 
        time.sleep(60)

# ==========================================================
# 🤖 TELEGRAM BOT COMMAND HANDLERS
# ==========================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    log(f"📥 User {message.chat.id} triggered /start command.")
    safe_send("🚀 <b>బాట్ రెడీ చంటి గారు! అన్ని ఫిల్టర్స్ లోడ్ అయ్యాయి.</b>", chat_id=message.chat.id)

# ==========================================================
# 📊 WEEKLY CACHE & SOURCE WEIGHT CONFIGURATION
# ==========================================================
weekly_cache = {}

SOURCE_WEIGHT = {
    "Reuters": 5, "Bloomberg": 5, "RBI": 5, "Fed": 5, "SEBI": 5, "Govt Release": 5,
    "Moneycontrol": 4, "Economic Times": 4, "CNBC": 4, "CNBC-TV18": 4, "Business Standard": 4, "Mint": 4,
    "ET NOW (X)": 3, "ET NOW": 3, "Redbox X": 2, "X Post": 1
}

@bot.message_handler(commands=['weekly'])
def generate_master_weekly_report(message):
    global weekly_cache
    log(f"📥 User {message.chat.id} triggered /weekly command.")
    
    now_time = datetime.now(IST)
    current_week_key = now_time.strftime('%Y-W%U') # ఈ వారానికి ప్రత్యేక క్యాష్ కీ
    
    # 🆕 1. CACHE CHECK (ఒకే వారంలో మళ్లీ పిలిస్తే ఇన్స్టంట్ రిపోర్ట్ ఇవ్వడం)
    if current_week_key in weekly_cache:
        log("⚡ Serving Weekly Report from Cache!")
        cached_data = weekly_cache[current_week_key]
        
        markup = InlineKeyboardMarkup()
        view_btn = InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{cached_data['unique_id']}_0")
        markup.add(view_btn)
        
        bot.send_message(message.chat.id, cached_data['short_msg'], reply_markup=markup, parse_mode="HTML")
        return

    waiting_msg = bot.send_message(
        message.chat.id, 
        "⏳ <b>చంటి గారు, గత 7 రోజుల RSS డేటాను ప్రాసెస్ చేస్తున్నాను... (Source Balancing, Deduplication & Python Theme Clustering)</b>", 
        parse_mode='HTML'
    )
    
    seven_days_ago = now_time - timedelta(days=7)
    
    try:
        # 🆕 2. TIME FILTERING & DEDUPLICATION
        raw_items = []
        dedup_titles = set()
        duplicates_count = 0
        
        for n in rss_news_store:
            if isinstance(n, dict) and n.get('time') >= seven_days_ago:
                clean_t = (n.get('title') or '').strip().lower()
                if clean_t in dedup_titles:
                    duplicates_count += 1
                    continue
                dedup_titles.add(clean_t)
                raw_items.append(n)
        
        if not raw_items:
            bot.edit_message_text(
                chat_id=message.chat.id, 
                message_id=waiting_msg.message_id, 
                text="⏳ <b>చంటి గారు, గత 7 రోజులకు సంబంధించి డేటాబేస్‌లో ఏ వార్తలు రికార్డ్ అవ్వలేదు సార్.</b>", 
                parse_mode='HTML'
            )
            return

        # 🆕 3. BALANCED SOURCE CAP (ప్రతి Source నుండి గరిష్టంగా 40-50 వార్తలు మాత్రమే)
        source_capped_items = []
        source_counts_cap = {}
        MAX_PER_SOURCE = 45
        
        for item in raw_items:
            src = item.get('source', 'ET NOW (X)')
            current_count = source_counts_cap.get(src, 0)
            if current_count < MAX_PER_SOURCE:
                source_capped_items.append(item)
                source_counts_cap[src] = current_count + 1

        # 🆕 4. PYTHON-LEVEL WEIGHTING & CHRONOLOGICAL SORTING
        sorted_news_items = sorted(
            source_capped_items,
            key=lambda x: (
                SOURCE_WEIGHT.get(x.get("source"), 1),
                x["time"]
            ),
            reverse=True
        )
        
        target_items = sorted_news_items[:250]
        total_news_count = len(target_items)

        # Dynamic Batching Logic
        if total_news_count < 50: batch_size = 25
        elif total_news_count < 150: batch_size = 40
        else: batch_size = 60

        total_batches = (total_news_count + batch_size - 1) // batch_size
        
        sorted_sources_str = ", ".join([f"{src}: {count}" for src, count in sorted(source_counts_cap.items(), key=lambda x: x[1], reverse=True)])
        start_date_str = target_items[-1]['time'].astimezone(IST).strftime('%d %b')
        end_date_str = target_items[0]['time'].astimezone(IST).strftime('%d %b %Y')

        # 🆕 5. DYNAMIC BATCH PROCESSING WITH TIMEOUT & NORMALIZATION
        intermediate_structured_outputs = []
        batch_num = 1
        
        for idx in range(0, total_news_count, batch_size):
            batch_items = target_items[idx : idx + batch_size]
            
            try:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=waiting_msg.message_id,
                    text=f"⏳ <b>చేస్తోంది సార్... (Batch {batch_num}/{total_batches} Processing)</b>\n"
                         f"📊 <b>స్కాన్ అయిన వార్తలు:</b> {min(idx + batch_size, total_news_count)}/{total_news_count}\n"
                         f"<i>డేటాను నార్మలైజ్ చేసి థీమ్స్‌గా వర్గీకరిస్తున్నాము...</i>",
                    parse_mode='HTML'
                )
            except: pass

            batch_text_list = []
            for i, n in enumerate(batch_items, idx + 1):
                arrival_time = n['time'].astimezone(IST).strftime('%d-%b %I:%M %p')
                clean_desc = (n.get('desc') or 'N/A')[:150].replace('\n', ' ')
                item_str = (
                    f"[{i}] Date: {arrival_time} | Source: {n.get('source', 'ET NOW (X)')}\n"
                    f"Title: {n.get('title', '')}\n"
                    f"Summary: {clean_desc}"
                )
                batch_text_list.append(item_str)
                
            batch_dataset_text = "\n----------------------------------------\n".join(batch_text_list)
            
            batch_prompt = f"""
            You are a Senior Research Analyst. Process this batch of market live updates ({len(batch_items)} items).

            DATASET BATCH:
            {batch_dataset_text}

            STRICT NORMALIZATION INSTRUCTIONS:
            - Do NOT summarize aggressively. Preserve every unique market-moving event.
            - Merge duplicate news items only.
            - Output strictly in the following structured format for each detected theme:

            THEME: [Name of the Market Theme]
            Supporting News: [Brief list of core facts]
            Companies: [Mention stock/company names or 'N/A']
            Impact: [High / Medium / Low]
            Category: [Corporate / Macro / Policy / Global]
            """
            
            batch_result = None
            for retry in range(3):
                try:
                    # Timeout guard in Gemini call
                    batch_result = safe_gemini(batch_prompt)
                    if batch_result and "AI అందుబాటులో లేదు" not in batch_result and "No significant news" not in batch_result:
                        break
                except Exception as b_err:
                    log(f"⚠️ Batch {batch_num} Retry {retry+1} error: {b_err}", "WARNING")
                    time.sleep(2)
                    
            if batch_result and "No significant news" not in batch_result:
                intermediate_structured_outputs.append(batch_result)
                
            batch_num += 1
            time.sleep(1)

        if not intermediate_structured_outputs:
            bot.edit_message_text(
                chat_id=message.chat.id, 
                message_id=waiting_msg.message_id, 
                text="⏳ <b>చంటి గారు, వార్తల ప్రాసెసింగ్‌లో సమగ్ర డేటా లభించలేదు సార్.</b>", 
                parse_mode='HTML'
            )
            return

        # 🆕 6. PYTHON-LEVEL INTERMEDIATE THEME MERGER (theme_map)
        theme_map = {}
        corporate_count = 0
        macro_count = 0

        for batch_out in intermediate_structured_outputs:
            blocks = batch_out.split("THEME:")
            for b in blocks:
                if not b.strip(): continue
                lines = b.strip().split("\n")
                theme_name = lines[0].strip()
                
                if "Corporate" in b: corporate_count += 1
                if "Macro" in b or "Policy" in b: macro_count += 1

                if theme_name in theme_map:
                    theme_map[theme_name].append(b.strip())
                else:
                    theme_map[theme_name] = [b.strip()]

        total_themes_generated = len(theme_map)
        
        # Merge themes into consolidated text
        consolidated_themes_text = ""
        for t_name, details in theme_map.items():
            consolidated_themes_text += f"\n=== THEME CLUSTER: {t_name} ===\n" + "\n".join(details) + "\n"

        # 🆕 7. MASTER CIO SYNTHESIS
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=waiting_msg.message_id,
                text="📝 <b>అన్ని థీమ్స్ పైథాన్‌లో మెర్జ్ అయ్యాయి! CIO లేఅవుట్‌లో ఫైనల్ విక్లీ రిపోర్ట్ జనరేట్ అవుతోంది సార్...</b>",
                parse_mode='HTML'
            )
        except: pass

        master_prompt = f"""
        You are acting as the Chief Investment Officer (CIO) and Head of Macro Research for a Top Multi-Billion Dollar Institutional Fund House.

        DATASET METADATA & PIPELINE STATS:
        - Total Analyzed: {total_news_count} News Items across {len(source_counts_cap)} Sources
        - Total Duplicates Filtered: {duplicates_count}
        - Total Unique Themes Generated: {total_themes_generated}
        - Corporate vs Macro Distribution: {corporate_count} Corporate / {macro_count} Macro & Policy
        - Source Breakdown: {sorted_sources_str}
        - Time Horizon: {start_date_str} to {end_date_str}

        CONSOLIDATED CLUSTERED THEMES DATASET:
        {consolidated_themes_text}

        STRICT INSTITUTIONAL RULES:
        1. NO EXTERNAL SEARCH / NO HALLUCINATION: Rely EXCLUSIVELY on the Normalized Dataset provided above. If evidence is insufficient for any section, explicitly state "Insufficient evidence in this week's dataset" instead of making assumptions.
        2. SOURCE WEIGHTING HIERARCHY: Prioritize official releases, Bloomberg, Reuters, Moneycontrol, ET NOW over generic social posts.
        3. STOCK SELECTION RULE: Only include specific stock names supported by multiple independent or high-trust developments. Avoid mentioning a stock unless there is clear evidence in the dataset.
        4. INTERNAL REASONING: Perform internal reasoning to synthesize cluster data. Do NOT expose internal reasoning.

        OUTPUT FORMAT & STRUCTURE (GENERATE IN CLEAN, HIGH-IMPACT PROFESSIONAL TELUGU):

        📊 **INSTITUTIONAL DATASET & PIPELINE STATS**
        - **సేకరించిన మొత్తం వార్తలు:** {total_news_count} ({duplicates_count} డ్యూప్లికేట్లు తొలగించబడ్డాయి)
        - **విశ్లేషించిన సోర్స్‌లు:** {len(source_counts_cap)} ({sorted_sources_str})
        - **గుర్తించిన మొత్తం థీమ్‌లు:** {total_themes_generated} ({corporate_count} Corporate / {macro_count} Macro)
        - **సమయం:** {start_date_str} నుండి {end_date_str} వరకు

        1. 📰 **వారంలో అత్యంత ముఖ్యమైన మార్కెట్ థీమ్‌లు (Core Market Moving Themes)**
           (Provide for each theme: Impact Score /10, Probability %, and Time Horizon [Immediate/Short/Long]).

        2. 🏛️ **Government, SEBI & Central Bank Policy Shifts** (RBI, Fed, Govt Decisions, Tax/Tariff Updates)

        3. 🏢 **Corporate & Sectoral Dynamics** (Defence, Solar/Renewable, Banking, IT, Auto, Capex - Highlight Stock Names in BOLD)

        4. 📈 **Global Macro & Commodities Matrix** (CPI, Crude Oil, Dollar Index, Bond Yields)

        5. 🟢 **Biggest Positive Theme** vs 🔴 **Biggest Negative Theme**

        6. 🎯 **Top 10 Institutional Signals** (Smart Money / FIIs vs DIIs Flow Analysis & Sector Rotation)

        7. 🗺️ **Risk Map & Opportunity Map**
           - Global Risk Score: X/10 | India Risk Score: X/10
           - Key Threats & Black Swan Risks

        8. 👁️ **Top 10 Stocks to Watch Next Week** (With specific verified catalysts in BOLD)

        9. 🔮 **Next Week Market Path Probability**:
           - 🐂 Bull Case Scenario
           - 🐻 Bear Case Scenario
           - ⚖️ Base Case Scenario (Most Likely Path)

        10. 💡 **Investor Action Plan & Strategic Recommendations**

        Formatting Rules: Highlight all stock names, indices, and numerical metrics in BOLD. Use clear spacing and bullet points.
        """

        active_client = client_2 or client_1
        report_text = None
        
        if active_client:
            for retry in range(3):
                try:
                    response = active_client.models.generate_content(
                        model=MODEL_NAME, 
                        contents=master_prompt
                    )
                    report_text = response.text.strip()
                    if report_text: break
                except Exception as m_err:
                    log(f"⚠️ Master Synthesis Retry {retry+1} error: {m_err}", "WARNING")
                    time.sleep(2)
                    
        if not report_text: report_text = "AI అందుబాటులో లేదు సార్."

        try: bot.delete_message(message.chat.id, waiting_msg.message_id)
        except: pass

        # 8. PAGINATION & CACHE SAVE
        def split_analysis(text, size=3200):
            return [text[i:i+size] for i in range(0, len(text), size)]

        report_parts = split_analysis(report_text)
        unique_id = int(time.time() * 1000)

        view_id = f"view_{unique_id}"
        back_id = f"back_{unique_id}"

        short_telegram_msg = f"📊 <b>INSTITUTIONAL WEEKLY MASTER BLUEPRINT (10/10)</b>\n" \
                             f"🏢 <b>విశ్లేషణ:</b> CIO Balanced Pipeline ({total_news_count} News Analyzed)\n" \
                             f"📈 <b>పైప్‌లైన్ గణాంకాలు:</b> {duplicates_count} Duplicates Cleared | {total_themes_generated} Themes\n" \
                             f"📅 <b>సమయం:</b> {start_date_str} నుండి {end_date_str} వరకు సేకరించిన డేటా\n" \
                             f"──────────────────────\n" \
                             f"💡 <i>సమగ్ర నివేదిక చదవడానికి కింద ఉన్న బటన్‌ను నొక్కండి సార్!</i>"

        analysis_vault[view_id] = {
            "title": f"WEEKLY MASTER BLUEPRINT ({total_news_count} News Items)",
            "source": "Institutional Research Desk",
            "parts": report_parts,
            "original_text": short_telegram_msg,
            "back_key": back_id
        }
        analysis_vault[back_id] = view_id

        # Save to Cache for this week
        weekly_cache[current_week_key] = {
            "unique_id": unique_id,
            "short_msg": short_telegram_msg
        }

        markup = InlineKeyboardMarkup()
        view_btn = InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{unique_id}_0")
        markup.add(view_btn)

        bot.send_message(message.chat.id, short_telegram_msg, reply_markup=markup, parse_mode="HTML")
        log("✅ 10/10 Perfect Institutional Weekly Pipeline with Cache executed successfully.")

    except Exception as e:
        log(f"❌ Weekly Report Pipeline Error: {e}", "ERROR")
        try: bot.delete_message(message.chat.id, waiting_msg.message_id)
        except: pass
        bot.send_message(message.chat.id, f"❌ వారపు విశ్లేషణలో లోపం వచ్చింది సార్: {safe_html_text(str(e))}")

@bot.message_handler(commands=['get', 'getred', 'getx'])
def get_news_by_time(message):
    cmd_name = message.text.split()[0]
    log(f"📥 Command Received: User {message.chat.id} triggered '{message.text}'")
    
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): 
        log(f"⚠️ Command Rejected: Invalid or missing hour argument in '{message.text}'")
        return
    hour = int(args[1])
    
    waiting_msg = bot.send_message(
        message.chat.id, 
        "⏳ <b>చంటి గారు, RSS ఫీడ్‌లోని కీలకమైన వార్తలను తీసుకొస్తున్నాను... కొంచెం సమయం పడుతుంది సార్.</b>", 
        parse_mode='HTML'
    )
    
    target_time = calculate_historical_target_time(hour)
    raw_date_part = target_time.strftime('%d-%m-%Y')
    clean_date_part = "-".join([str(int(x)) for x in raw_date_part.split('-')])
    time_part = target_time.strftime('%I %p').lstrip('0')
    cutoff_display_str = f"{clean_date_part} {time_part}"
    
    current_date_str = datetime.now(IST).strftime('%d-%b-%Y')
    current_time_str = datetime.now(IST).strftime('%H:%M')
    
    source_type = "NORMAL"
    if 'getred' in message.text: source_type = "REDBOX"
    elif 'getx' in message.text: source_type = "X"
    
    filtered = []
    for n in rss_news_store:
        if isinstance(n, dict) and n.get('time') >= target_time:
            if source_type == "REDBOX" and n.get('source') == "Redbox X": filtered.append(n)
            elif source_type == "X" and n.get('type') == "X" and n.get('source') != "Redbox X": filtered.append(n)
            elif source_type == "NORMAL" and n.get('type') == "NORMAL": filtered.append(n)
            
    filtered.sort(key=lambda x: x['time']) 
    total_news_count = len(filtered)
    
    icon = "🕒" if source_type == "NORMAL" else ("🚩" if source_type == "REDBOX" else "🐦")
    title_label = "Normal RSS" if source_type == "NORMAL" else ("Redbox" if source_type == "REDBOX" else "X RSS")
    
    report_header = (
        f"{icon} <b>{title_label} ({cutoff_display_str} నుండి వచ్చిన మొత్తం వార్తలు):</b>\n"
        f"📅 <b>తేదీ:</b> {current_date_str} | <b>సమయం:</b> {current_time_str}\n"
        f"📊 <b>మొత్తం లభించిన వార్తలు:</b> {total_news_count} రికార్డులు\n"
        f"──────────────────────"
    )
    
    try: 
        bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception as err: 
        log(f"⚠️ Failed to delete waiting message: {err}", "WARNING")
    
    bot.send_message(message.chat.id, report_header, parse_mode='HTML')
    
    if not filtered:
        bot.send_message(message.chat.id, f"⏳ ఈ సమయం ({cutoff_display_str}) నుండి ఎటువంటి వార్తలు రికార్డ్ అవ్వలేదు సార్.", parse_mode='HTML')
        return
        
    for i, n in enumerate(filtered, 1):
        arrival_time = n['time'].astimezone(IST).strftime('%I:%M %p')
        
        if source_type == "NORMAL":
            raw_title = n.get('full_text', '').split("    ")[0]
            subject_match = re.search(r'\b[a-zA-Z0-9\s\&]+', raw_title)
            
            if subject_match:
                full_subject = subject_match.group(0).strip()
                words = full_subject.split()
                subject_title = " ".join(words[:3]) if len(words) > 3 else full_subject
            else:
                subject_title = "Market Update"
                
            g_url = f"https://translate.google.com/translate?sl=en&tl=te&u={n.get('link','')}"
            
            msg_block = (
                f"🔢 <b>[#{i}/{total_news_count}]</b>  ⏰ <b>[{arrival_time}]</b>\n"
                f"🔹 <b>{safe_html_text(subject_title)}:</b>\n\n"
                f"{safe_html_text(n['title'])}\n\n"
                f"🔗 <a href='{g_url}'>Read More in Telugu</a> | <a href='{n.get('link','')}'>English Original</a>"
            )
            bot.send_message(message.chat.id, msg_block, parse_mode='HTML', disable_web_page_preview=True)
        else:
            raw_x_text = n['title']
            x_words = raw_x_text.split()
            short_x_subject = " ".join(x_words[:3]) if len(x_words) > 3 else "Flash Update"
            
            msg_block = (
                f"🔢 <b>[#{i}/{total_news_count}]</b>  ⏰ <b>[{arrival_time}]</b>\n"
                f"{icon} <b>{safe_html_text(short_x_subject)}:</b>\n\n"
                f"{safe_html_text(raw_x_text)}"
            )
            bot.send_message(message.chat.id, msg_block, parse_mode='HTML', disable_web_page_preview=True)
            
        time.sleep(0.4)
        
    final_end_msg = (
        f"──────────────────────\n"
        f"✅ <b>చంటి గారు, ఇప్పటివరకు ఉన్న అన్ని వార్తలు వచ్చేసాయి సార్!</b>\n"
        f"📌 <b>మొత్తం పంపిన వార్తల సంఖ్య: {total_news_count}</b>"
    )
    bot.send_message(message.chat.id, final_end_msg, parse_mode='HTML')

@bot.message_handler(commands=['summary'])
def master_ai_summary_by_hours(message):
    log(f"📥 Command Received: User {message.chat.id} triggered '{message.text}'")
    args = message.text.split()
    hour = int(args[1]) if len(args) > 1 and args[1].isdigit() else 6
    
    target_time = calculate_historical_target_time(hour)
    
    normal_news = [
        n for n in rss_news_store 
        if isinstance(n, dict) 
        and n.get('time') >= target_time 
        and n.get('type') == "NORMAL"
    ]
    total_news_count = len(normal_news)
    
    if not normal_news:
        bot.send_message(message.chat.id, f"⏳ <b>చంటి గారు, గత ({hour}) గంటల్లో Normal RSS ఫీడ్‌లో ఏ వార్తలు రికార్డ్ అవ్వలేదు సార్.</b>", parse_mode='HTML')
        return

    batch_size = 20
    total_batches = (total_news_count + batch_size - 1) // batch_size
    
    estimated_seconds = (total_batches - 1) * 20 
    minutes, seconds = divmod(estimated_seconds, 60)
    time_display = f"{minutes} నిమిషాల {seconds} సెకన్లు" if minutes > 0 else f"{seconds} సెకన్లు"

    waiting_msg = bot.send_message(
        message.chat.id, 
        f"⏳ <b>చంటి గారు, గత {hour} గంటల ET NOW & NDTV Profit వార్తల సమాచారాన్ని సేకరిస్తున్నాను...</b>\n\n"
        f"📊 <b>మొత్తం వార్తలు:</b> {total_news_count} ({total_batches} బ్యాచ్‌లు)\n"
        f"⏰ <b>పట్టే అంచనా సమయం:</b> ~{time_display}\n\n"
        f"<i>⚠️ డైలీ కోటా అవ్వకుండా ఉండటానికి ప్రతి 20 వార్తలను ఒకే బ్యాచ్‌గా చేసి, బ్యాచ్ కి మధ్య 20 సెకన్ల విరామంతో జెమిని ఏఐ స్కాన్ చేస్తోంది సార్. దయచేసి ఓపిక పట్టండి...</i>", 
        parse_mode='HTML'
    )
    
    aggregated_analysis_chunks = []
    start_time = time.time()
    batch_counter = 1
    
    try:
        for idx in range(0, total_news_count, batch_size):
            batch = normal_news[idx : idx + batch_size]
            batch_text = "\n".join([f"- {n['title']}" for n in batch])
            
            chunk_prompt = f"""
            You are acting as the Head of an Elite International Research Team. Review this batch of market live updates:
            {batch_text}
            
            Extract and summarize all critical technical insights, corporate declarations, national developments, and macro global changes. 
            Keep the layout compact and concise for synthesis.
            """
            
            chunk_analysis = safe_gemini(chunk_prompt)
            
            if "AI అందుబాటులో లేదు" in chunk_analysis or "Key Error" in chunk_analysis:
                raise Exception("Gemini API responding with errors or Rate Limits.")
                
            aggregated_analysis_chunks.append(chunk_analysis)
            
            if idx + batch_size < total_news_count:
                remaining_batches = total_batches - batch_counter
                rem_seconds = remaining_batches * 20
                rem_min, rem_sec = divmod(rem_seconds, 60)
                rem_display = f"{rem_min}m {rem_sec}s" if rem_min > 0 else f"{rem_sec}s"
                
                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=waiting_msg.message_id,
                        text=f"⏳ <b>జెమిని ద్వారా బల్క్ బ్యాచ్ ప్రాసెసింగ్ జరుగుతోంది సార్...</b>\n\n"
                             f"🔄 <b>పూర్తయిన బ్యాచ్‌లు:</b> {batch_counter}/{total_batches}\n"
                             f"⏳ <b>మిగిలిన సమయం:</b> ~{rem_display}\n\n"
                             f"<i>📊 స్కాన్ అవుతున్న వార్తలు: {idx + batch_size} వరకు విజయవంతంగా పూర్తయింది.</i>",
                        parse_mode='HTML'
                    )
                except:
                    pass
                    
                time.sleep(20) 
            batch_counter += 1
        
        try:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=waiting_msg.message_id,
                text="<b>📝 అన్ని బ్యాచ్‌ల సేకరణ పూర్తయింది చంటి గారు! గ్లోబల్ రీసెర్చ్ టీమ్ హెడ్ ఫైనల్ మాస్టర్ రిపోర్ట్ తయారు చేస్తున్నారు... ఒకే ఒక్క నిమిషం సార్.</b>",
                parse_mode='HTML'
            )
        except:
            pass

        combined_raw_analysis = "\n\n".join(aggregated_analysis_chunks)
        
        master_research_prompt = f"""
                మీరు ఒక ఇంటర్నేషనల్ రీసెర్చ్ టీమ్ హెడ్ (Elite Global Institutional Research Team Head). 
                గత కొన్ని గంటలుగా సేకరించిన ఈ క్రింది కీలకమైన ఆర్థిక మరియు మార్కెట్ సమాచార సమూహాన్ని పూర్తిగా విశ్లేషించి, ఒక లోతైన ప్రొఫెషనల్ నివేదికను సిద్ధం చేయండి.
                
                DATASET TO ANALYZE:
                {combined_raw_analysis}
                
                Generate a highly polished, deep institutional summary in clean, professional Telugu. 
                Strictly structure the response into these 3 specific sections:
        
                1. 🚀 Stock Market & Corporate Analysis
                   - Provide benchmark index trajectory, market sentiment, and sector-wise news (Defense, Solar/Renewable, Railways, Banking, Tech, etc.).
                   - Clearly highlight specific stock names involved (e.g., HAL, BEL, IREDA, HDFC Bank, etc.) with actionable insights.
        
                2. 🇮🇳 National Business & Policy News
                   - Detail key domestic macroeconomic developments, RBI/Government policy decisions, GST/Tax updates, and national economic indicators.
        
                3. 🌍 International Market & Global Trends
                   - Outline critical international developments, US Fed decisions, inflation data, crude oil trends, foreign markets (US, Asia, Europe), and geopolitical factors.
        
                Formatting & Tone Instructions:
                - Language: Professional, high-impact Telugu script.
                - Style: Give clear, actionable market insights and highlight important stock names prominently in bold.
                - Spacing: Use clean paragraph spacing and bullet points for effortless reading.
                """
        
        final_master_summary = safe_gemini(master_research_prompt)
        
        end_time = time.time()
        total_taken_seconds = int(end_time - start_time)
        t_min, t_sec = divmod(total_taken_seconds, 60)
        taken_display = f"{t_min} నిమిషాల {t_sec} సెకన్లు" if t_min > 0 else f"{t_sec} sec"

        try: 
            bot.delete_message(message.chat.id, waiting_msg.message_id)
        except: 
            pass
        
        current_time_str = datetime.now(IST).strftime('%I:%M %p')
        header = f"💥 <b>GLOBAL RESEARCH TEAM MASTER PULSE</b> 💥\n" \
                 f"🏢 <b>నివేదిక:</b> రీసెర్చ్ టీమ్ హెడ్ అనాలసిస్ (Gemini 10-Batch Safe System)\n" \
                 f"🕒 <b>విశ్లేషణ సమయం:</b> గత {hour} గంటల డేటా (Generated at {current_time_str})\n" \
                 f"📊 <b>మొత్తం స్కాన్ చేసిన వార్తలు:</b> {total_news_count}\n" \
                 f"⏱️ <b>మొత్తం పట్టిన సమయం:</b> {taken_display}\n" \
                 f"──────────────────────\n\n"
        
        send_long_message(message.chat.id, header + final_master_summary, parse_mode='HTML')

    except Exception as e:
        log(f"❌ Master Summary Logic Error: {e}", "ERROR")
        try:
            bot.delete_message(message.chat.id, waiting_msg.message_id)
        except:
            pass
        bot.send_message(
            message.chat.id,
            f"❌ <b>సమ్మరీ లోపం (AI Error):</b>\n\n"
            f"చంటి గారు, జెమిని API కనెక్టివిటీ లో చిన్న లోపం వచ్చింది సార్.\n"
            f"<code>రిపోర్ట్ ఎర్రర్: {safe_html_text(str(e)[:200])}</code>\n\n"
            f"<i>💡 సూచన: కొద్దిసేపు ఆగి మళ్లీ ప్రయత్నించండి సార్, సమస్య సర్దుకుంటుంది!</i>",
            parse_mode='HTML'
        )

def get_commands_list_text():
    return ("╔════════════════════════╗\n   🤖  <b>MARKET BOT COMMANDS</b>  📊\n╚════════════════════════╝\n\n"
            "🧠 <b>AI DEEP RESEARCH SUMMARY</b>\n🔹 <code>/summary [hours]</code>\n🔹 <code>/weekly</code> (9-Section Blueprint)\n\n"
            "⏱ <b>FETCH NEWS BY HOUR</b>\n🔸 <code>/get [hour]</code>\n🔸 <code>/getx [hour]</code>\n🔸 <code>/getred [hour]</code>\n"
            "──────────────────────\n📌 <i>చంటి గారు, కమాండ్ కాపీ చేయడానికి Tap చేయండి!</i>")

@bot.message_handler(commands=['list'])
def list_commands(message): 
    log(f"📥 User {message.chat.id} requested commands /list.")
    safe_send(get_commands_list_text(), chat_id=message.chat.id)

# ==========================================================
# ⏱️ BACKGROUND ALERTS & WEB SERVER 
# ==========================================================
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

scheduler.add_job(send_night_pulse_report, 'cron', hour=6, minute=0)
scheduler.add_job(send_market_table, 'interval', minutes=10)
scheduler.start()

app = Flask('')
@app.route('/')
def home(): return "Bot is running perfectly!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================================
# 🏁 MAIN EXECUTION EXECUTOR
# ==========================================================
if __name__ == "__main__":
    log("🚀 Starting Combined Master Market Bot...")
    try: safe_send("✅ చంటి గారు, కంబైన్డ్ మాస్టర్ బాట్ విజయవంతంగా ప్రారంభమైంది!")
    except: pass

    Thread(target=run_server).start()
    Thread(target=main_loop, daemon=True).start()
    Thread(target=fetch_normal_rss, daemon=True).start()
    Thread(target=fetch_x_rss, daemon=True).start()
    
    while True:
        try: bot.infinity_polling(timeout=90, long_polling_timeout=15, skip_pending=True)
        except Exception as e:
            log(f"⚠️ Connection lost, reconnecting in 10s: {e}", "WARNING")
            time.sleep(10)
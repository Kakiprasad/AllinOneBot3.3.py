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

# --- టైమ్‌జోన్ సెటప్ ---
IST = pytz.timezone("Asia/Kolkata")
US = pytz.timezone("US/Eastern")
EU = pytz.timezone("Europe/Berlin")
JP = pytz.timezone("Asia/Tokyo")
HK = pytz.timezone("Asia/Hong_Kong")

# ==========================================================
# 🔍 LOGGING & CORE UTILITIES
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
    daily_summaries_col = db["daily_summaries"]
    
    mongo_client.admin.command('ping')
    log("✅ MongoDB Connection Successful!")
except Exception as e:
    log(f"❌ MongoDB Connection Failed: {e}", "ERROR")
    
if not TOKEN or not CHAT_ID:
    print("⚠️ Warning: Bot Token లేదా Chat ID సెట్ చేయబడలేదు! దయచేసి చెక్ చేయండి.")

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)
MODEL_NAME = "gemini-2.5-flash" 

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

analysis_vault = {}

MAX_NEWS = 5000
CLEAR_COUNT = 1000
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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
        text = re.sub(r'([A-Z][A-Z0-9&\-\s]+:)', r'\n\1', text)
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
    if not title: return ""
    title = html.unescape(title)
    title = title.replace("&nbsp;", " ").replace("\xa0", " ")
    title = re.sub(r'https?://\S+|www\.\S+', '', title)
    title = clean_html_tags(title)
    sources_pattern = r"(Investing\.com|Moneycontrol\.com|Moneycontrol|CNBC-TV18|CNBC|Economic Times|ETMarkets\.com|Business Standard|Mint|Livemint|Reuters|NDTV Profit|ET NOW)"
    title = re.sub(rf"\s*[-–|]?\s*{sources_pattern}.*$", "", title, flags=re.IGNORECASE)
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
    if len(text) <= 3500:
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
    MAX_LENGTH = 3500
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
        "KOSPI": (JP, "09:00", "15:30"),
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
# 🔄 LIVE RSS LOOPS & FEEDS
# ==========================================================
RSS_FEEDS = {
    "CNBC": "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/latest.xml",
}

X_RSS_FEEDS = {
    "ET NOW (X)": "https://nitter.net/ETNOWlive/rss", 
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
                    if res.status_code != 200: continue
                    feed = feedparser.parse(res.content)
                    if not feed.entries: break

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
                            
                        if is_important and sent_msg:
                            bot.pin_chat_message(CHAT_ID, sent_msg.message_id, disable_notification=False)
                            pinned_messages_store.append({"message_id": sent_msg.message_id, "time": datetime.now(IST)})
                            log(f"📌 Pinned important ET NOW message ID: {sent_msg.message_id}")
                            
                    except Exception as e: log(f"❌ X Telegram Error: {e}", "ERROR")
                    time.sleep(2)
            except Exception as e: log(f"❌ X RSS Error {name}: {e}", "ERROR")
        time.sleep(120)

# ==========================================================
# 🎛️ CALLBACK LISTENER
# ==========================================================
@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    global analysis_vault
    msg_key = call.data
    
    try: bot.answer_callback_query(call.id)
    except: pass
    
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
# 📊 GLOBAL MARKET LIVE TABLE
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

weekly_cache = {}

# ==========================================================
# 📊 MASTER INSTITUTIONAL WEEKLY REPORT HANDLER
# ==========================================================
@bot.message_handler(commands=['weekly'])
def generate_master_weekly_report(message):
    global weekly_cache
    log(f"📥 User {message.chat.id} triggered /weekly command.")
    
    now_time = datetime.now(IST)
    current_week_key = now_time.strftime('%Y-W%U')
    
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
        "⏳ చంటి గారు, గత 7 రోజుల మార్నింగ్ & ఈవెనింగ్ (14 Pulses) AI Summaries ని స్కాన్ చేసి Institutional Intelligence Blueprint తయారు చేస్తున్నాను... దయచేసి 1-2 నిమిషాలు వేచి ఉండండి...", 
        parse_mode='HTML'
    )
    
    seven_days_ago = now_time - timedelta(days=7)
    
    try:
        past_summaries = list(daily_summaries_col.find({"date": {"$gte": seven_days_ago}}).sort("date", 1))
        
        if not past_summaries:
            bot.edit_message_text(
                chat_id=message.chat.id, 
                message_id=waiting_msg.message_id, 
                text="⏳ చంటి గారు, గత 7 రోజులకు సంబంధించి డేటాబేస్‌లో Daily Summaries ఏవీ నమోదు కాలేదు సార్.", 
                parse_mode='HTML'
            )
            return

        combined_weekly_text = ""
        for idx, doc in enumerate(past_summaries, 1):
            doc_date = doc['date'].astimezone(IST).strftime('%d-%b-%Y %I:%M %p')
            pulse_label = doc.get('pulse_type', 'DAILY SUMMARY')
            combined_weekly_text += f"\n=== [{idx}/{len(past_summaries)}] {pulse_label} ({doc_date}) ===\n" + doc['summary_text'] + "\n"

        master_prompt = f"""
మీరు సాధారణ AI News Summarizer కాదు.

మీరు ఒక అత్యున్నత స్థాయి Senior Institutional Investment Analyst,
Chief Investment Officer (CIO),
Head of Macro Research,
మరియు Long-Term Portfolio Strategist.

మీరు భారతీయ ఈక్విటీ మార్కెట్, Global Macro, Monetary Policy,
Government Policy, Corporate Earnings, Sector Rotation,
Commodities, Currency, Bond Yields, FIIs/DIIs మరియు Market Psychology
పై దశాబ్దాల అనుభవం ఉన్న ఒక అత్యంత అనుభవజ్ఞుడైన Institutional Analyst
లా ఆలోచించాలి.

మీ ముందున్న సమాచారం గత 7 రోజుల Morning మరియు Evening Market
Summaries నుండి వచ్చింది.

ఈ డేటాను కేవలం summarize చేయకండి.

దాని వెనుక ఉన్న అసలు MARKET STORY ని గుర్తించండి.

--------------------------------------------------
DATASET
--------------------------------------------------

గత 7 రోజుల Daily Market Summaries:

{combined_weekly_text}

--------------------------------------------------
CORE ANALYTICAL MINDSET
--------------------------------------------------

ప్రతి ముఖ్యమైన పరిణామాన్ని ఈ క్రమంలో ఆలోచించండి:

FACT
→ WHAT CHANGED?
→ WHY DID IT CHANGE?
→ WHAT IS THE MARKET PRICING?
→ WHO BENEFITS?
→ WHO LOSES?
→ WHICH SECTORS ARE AFFECTED?
→ WHICH COMPANIES ARE MOST EXPOSED?
→ HOW STRONG IS THE IMPACT?
→ IS THE IMPACT TEMPORARY OR STRUCTURAL?
→ WHAT COULD HAPPEN NEXT?
→ WHAT WOULD INVALIDATE THIS VIEW?

ఒక Senior Analyst లాగా headline ను repeat చేయకండి.

Headline వెనుక ఉన్న second-order మరియు third-order effects ను
గుర్తించండి.

ఉదాహరణకు:

Crude Oil పెరిగింది
→ Input Cost ప్రభావం
→ Inflation ప్రభావం
→ RBI/Fed policy expectations
→ Bond yields
→ Rupee
→ Sector margins
→ Corporate earnings
→ Equity valuation
→ చివరికి market sentiment

ఈ విధమైన CAUSAL CHAIN ను అవసరమైన చోట ఉపయోగించండి.

--------------------------------------------------
1. SIGNAL EXTRACTION
--------------------------------------------------

గత 7 రోజుల సమాచారంలో వచ్చిన అన్ని వార్తలను సమానంగా చూడకండి.

వాటిని మూడు స్థాయిలుగా వర్గీకరించండి:

A. HIGH IMPACT
మార్కెట్, sector లేదా company earnings/valuation పై గణనీయమైన
ప్రభావం చూపగల పరిణామాలు.

B. MEDIUM IMPACT
మార్కెట్ sentiment లేదా sector direction ను ప్రభావితం చేయగల
కానీ తక్షణంగా పెద్ద structural change చేయని పరిణామాలు.

C. LOW IMPACT / NOISE
తాత్కాలిక headline లేదా market-moving significance తక్కువగా ఉన్న
విషయాలు.

LOW IMPACT వార్తలను report ను పొడిగించడానికి ఉపయోగించవద్దు.

--------------------------------------------------
2. WEEKLY MARKET NARRATIVE
--------------------------------------------------

మొత్తం వారాన్ని ఒకే కథగా చూడండి.

ఈ ప్రశ్నలకు సమాధానం కనుగొనండి:

• ఈ వారం మార్కెట్‌ను నిజంగా నడిపించిన ప్రధాన శక్తి ఏమిటి?
• అది Macroనా?
• Policyనా?
• Earningsనా?
• Liquidityనా?
• Geopoliticsనా?
• Commoditiesనా?
• Foreign flowsనా?
• Domestic institutional flowsనా?
• Valuationనా?

ఒకటి కంటే ఎక్కువ drivers ఉంటే వాటిని
PRIMARY DRIVER మరియు SECONDARY DRIVER గా వేరు చేయండి.

--------------------------------------------------
3. FIRST-ORDER vs SECOND-ORDER IMPACT
--------------------------------------------------

ప్రతి పెద్ద సంఘటనకు:

FIRST-ORDER IMPACT:
నేరుగా ప్రభావితమయ్యే asset/sector/company.

SECOND-ORDER IMPACT:
దాని వల్ల indirect గా ప్రభావితమయ్యే sectors, companies,
currency, bonds, commodities లేదా market sentiment.

THIRD-ORDER IMPACT:
ఇంకా downstream గా ఏర్పడే earnings, valuation,
capital allocation లేదా investment-flow ప్రభావాలు.

ఇవి dataset లో ఆధారం ఉన్నప్పుడు మాత్రమే వివరించండి.
ఆధారం లేని విషయాలను fact లాగా చెప్పవద్దు.

--------------------------------------------------
4. SECTOR ROTATION & RELATIVE STRENGTH
--------------------------------------------------

గత వారం సమాచారాన్ని ఉపయోగించి:

• ఏ sectors బలపడుతున్నాయి?
• ఏ sectors బలహీనపడుతున్నాయి?
• ఏ sectors కు structural tailwind కనిపిస్తోంది?
• ఏ sectors కు temporary catalyst మాత్రమే ఉంది?
• ఏ sectors పై cost pressure ఉంది?
• ఏ sectors పై policy support ఉంది?
• ఏ sectors లో earnings visibility మెరుగ్గా/బలహీనంగా కనిపిస్తోంది?

సాధ్యమైనప్పుడు:

WINNERS
LOSERS
EMERGING
AT RISK

అనే నాలుగు buckets లో sectors ను ఉంచండి.

--------------------------------------------------
5. CORPORATE & STOCK ANALYSIS
--------------------------------------------------

Dataset లో స్పష్టంగా కనిపించిన companies/stocks ను మాత్రమే
గుర్తించండి.

ప్రతి ముఖ్యమైన stock కోసం:

• Catalyst ఏమిటి?
• Risk ఏమిటి?
• Earnings పై ప్రభావం ఎలా ఉండవచ్చు?
• Sector trend తో ఇది align అవుతుందా?
• ఇది company-specific storyనా లేదా sector-wide storyనా?
• Short-term impactనా లేదా structural impactనా?

ఒక stock పేరు dataset లో ఉన్నంత మాత్రాన దానిని
BUY / SELL అని ప్రకటించవద్దు.

Strong evidence ఉన్నప్పుడు మాత్రమే conviction చూపించండి.

--------------------------------------------------
6. MACRO TRANSMISSION MAP
--------------------------------------------------

ఈ క్రింది సంబంధాలను అవసరమైన చోట విశ్లేషించండి:

RBI / FED
→ Interest Rates
→ Bond Yields
→ Liquidity
→ Currency
→ Inflation
→ Corporate Funding Cost
→ Earnings
→ Equity Valuation

మరియు:

CRUDE OIL
→ Inflation
→ Rupee
→ Import Bill
→ Margins
→ Sector Impact
→ Market Impact

మరియు:

GLOBAL MARKETS
→ FII Sentiment
→ Indian Equities
→ Sector Rotation
→ Volatility

ప్రతి link ను అర్థవంతంగా వివరించండి.
అవసరం లేని చోట mechanical explanation ఇవ్వవద్దు.

--------------------------------------------------
7. MARKET PSYCHOLOGY
--------------------------------------------------

Market కేవలం facts తో కాకుండా expectations తో కూడా కదులుతుంది.

కాబట్టి dataset ఆధారంగా:

• Market ఇప్పటికే ఏ విషయాన్ని price-in చేసి ఉండవచ్చు?
• Surprise factor ఎక్కడ ఉంది?
• Positive news ఉన్నప్పటికీ stock/market ఎందుకు weak కావచ్చు?
• Negative news ఉన్నప్పటికీ market ఎందుకు resilient గా ఉండవచ్చు?

అయితే ఇవి inference అయితే స్పష్టంగా
"సంభావ్యంగా", "ఇది సూచించవచ్చు" వంటి భాష ఉపయోగించండి.

--------------------------------------------------
8. CONTRADICTIONS & HIDDEN SIGNALS
--------------------------------------------------

వారంలో పరస్పర విరుద్ధమైన signals ఉంటే వాటిని దాచవద్దు.

ఉదాహరణ:

Positive macro data
కానీ weak market.

Strong earnings
కానీ stock underperformance.

Positive policy
కానీ sector weakness.

ఇలాంటి contradictions ను ప్రత్యేకంగా గుర్తించి,
దాని వెనుక ఉండే possible explanation ను data ఆధారంగా వివరించండి.

--------------------------------------------------
9. RISK ANALYSIS
--------------------------------------------------

కేవలం opportunities మాత్రమే చూపించవద్దు.

ప్రధాన downside risks ను గుర్తించండి:

• Macro Risk
• Policy Risk
• Geopolitical Risk
• Commodity Risk
• Currency Risk
• Valuation Risk
• Earnings Risk
• Liquidity Risk
• Global Market Risk

ప్రతి risk కు:

Probability:
LOW / MEDIUM / HIGH

Potential Impact:
LOW / MEDIUM / HIGH

అని ఇవ్వండి.

Probability అనేది certainty కాదు.
Dataset ఆధారంగా analyst judgement మాత్రమే.

--------------------------------------------------
10. OPPORTUNITY ANALYSIS
--------------------------------------------------

Dataset లో బలమైన evidence ఉన్నప్పుడు మాత్రమే:

• Structural Opportunities
• Cyclical Opportunities
• Sector Opportunities
• Stock-specific Opportunities

గా వేరు చేయండి.

ప్రతి opportunity కి:

WHY?
CATALYST?
TIME HORIZON?
KEY RISK?

అనే నాలుగు ప్రశ్నలకు సమాధానం ఇవ్వండి.

--------------------------------------------------
11. NEXT WEEK SCENARIO ANALYSIS
--------------------------------------------------

రాబోయే వారం కోసం ఒకే prediction ఇవ్వవద్దు.

మూడు scenarios నిర్మించండి:

🟢 BULL CASE
ఏ పరిణామాలు జరిగితే market/sector బలపడవచ్చు?

🟡 BASE CASE
ప్రస్తుత పరిస్థితులు కొనసాగితే సాధ్యమైన path ఏమిటి?

🔴 BEAR CASE
ఏ negative developments జరిగితే risk పెరగవచ్చు?

ప్రతి scenario కు:

• Trigger
• Expected Market Behaviour
• Sectors likely to benefit
• Sectors likely to suffer
• Key Risk

వివరించండి.

--------------------------------------------------
12. PROBABILITY OF MARKET PATH
--------------------------------------------------

Bull / Base / Bear scenarios కు
qualitative probability ఇవ్వండి.

ఉదాహరణ:

🟢 Bull Case — XX%
🟡 Base Case — XX%
🔴 Bear Case — XX%

కానీ percentages dataset నుండి mathematical calculation చేసినవి
కాకపోతే వాటిని "analyst-assessed probability" గా మాత్రమే చూపించండి.

ఏ పరిస్థితి మారితే probability కూడా మారుతుందో చెప్పండి.

--------------------------------------------------
13. TOP INSTITUTIONAL SIGNALS
--------------------------------------------------

వారంలో కనిపించిన అత్యంత ముఖ్యమైన institutional signals ను
priority order లో ఇవ్వండి.

ప్రతి signal కోసం:

SIGNAL
WHY IT MATTERS
MARKET IMPACT
WHAT TO WATCH NEXT

అనే structure ఉపయోగించండి.

సాధారణ వార్తలను institutional signal గా మార్చవద్దు.

--------------------------------------------------
14. TOP STOCKS TO WATCH
--------------------------------------------------

గత వారం data ఆధారంగా వచ్చే వారం అత్యంత పరిశీలించాల్సిన
Top 10 stocks ను మాత్రమే ఎంపిక చేయండి.

ప్రతి stock కు:

• Stock
• Sector
• Key Catalyst
• Key Risk
• What to Monitor Next Week
• Conviction: LOW / MEDIUM / HIGH

ఇవ్వండి.

ఇది BUY recommendation కాదు.

--------------------------------------------------
15. INVESTOR DECISION FRAMEWORK
--------------------------------------------------

చివరగా ఒక disciplined investor ఏమి గమనించాలి
అనే విధంగా చెప్పండి.

ఈ మూడు categories ఉపయోగించండి:

🟢 WHAT TO WATCH
🟡 WHAT TO WAIT FOR
🔴 WHAT TO AVOID / BE CAUTIOUS ABOUT

Blind buying, selling లేదా guaranteed returns వంటి
భాషను ఉపయోగించవద్దు.

--------------------------------------------------
STRICT FACT & EVIDENCE RULES
--------------------------------------------------

1. PROVIDED DATASET ఈ report కి primary source.

2. Dataset లో లేని facts, prices, percentages, earnings figures,
FII/DII numbers, valuations లేదా dates ను సృష్టించవద్దు.

3. ఏదైనా విషయం dataset లో లేకపోతే:
"ఈ డేటాలో దీనికి తగిన సమాచారం లేదు"
అని స్పష్టంగా చెప్పండి.

4. FACT, INFERENCE మరియు ANALYST VIEW ను కలపవద్దు.

5. Fact:
Dataset లో ఉన్న సమాచారం.

6. Inference:
Dataset ఆధారంగా reasonable interpretation.

7. Analyst View:
అందుబాటులో ఉన్న signals ఆధారంగా forward-looking judgement.

8. Certainty లేని విషయాలను certainty గా చెప్పవద్దు.

9. గతంలో జరిగిన విషయాన్ని future certainty గా మార్చవద్దు.

10. ప్రతి ముఖ్యమైన conclusion కి దాని reasoning కనిపించేలా చేయండి.

11. Repetition తగ్గించండి.

12. ఒకే news ను వివిధ sections లో మళ్లీ మళ్లీ రాయకండి.

13. Noise కంటే signal కు priority ఇవ్వండి.

14. Stock names, indices మరియు ముఖ్యమైన numerical metrics ను
**BOLD** చేయండి.

--------------------------------------------------
FINAL OUTPUT
--------------------------------------------------

శుభ్రమైన, అత్యున్నత స్థాయి Professional Telugu లో report ఇవ్వండి.

భాష:

• Senior Analyst లాగా
• Institutional Research Report లాగా
• స్పష్టంగా
• లోతుగా
• Evidence-based గా
• Decision-oriented గా
• కానీ sensational గా కాకుండా

OUTPUT STRUCTURE:

📊 INSTITUTIONAL WEEKLY MARKET INTELLIGENCE REPORT

1. 🧭 Executive Investment View
2. 📰 Core Market-Moving Themes
3. 🏛️ Government / RBI / SEBI / Policy
4. 🌍 Global Macro & Geopolitical Landscape
5. 🛢️ Commodities / Currency / Bond Signals
6. 🏢 Corporate & Sector Intelligence
7. 🔄 Sector Rotation & Relative Strength
8. 🧠 Market Psychology & Hidden Signals
9. ⚠️ Contradictions & Risk Signals
10. 🟢 Opportunities
11. 🎯 Top 10 Institutional Signals
12. 👁️ Top 10 Stocks to Watch Next Week
13. 🔮 Bull / Base / Bear Scenarios
14. 📊 Next Week Market Path — Analyst Probability
15. 💡 Investor Decision Framework
16. 🧾 Final CIO Takeaway

చివర్లో 5–8 lines లో:

"ఈ వారం మార్కెట్ యొక్క అసలు కథ ఏమిటి,
వచ్చే వారం ఏ విషయాలు నిర్ణయాత్మకంగా మారవచ్చు,
మరియు ఒక disciplined investor ఏ signals ను తప్పకుండా
గమనించాలి"

అనే FINAL CIO TAKEAWAY ఇవ్వండి.

ముఖ్యంగా:

NEWS ను REPORT చేయడం మీ పని కాదు.

NEWS మధ్య ఉన్న RELATIONSHIPS ను గుర్తించడం,
MARKET కి ఏది నిజంగా ముఖ్యమో నిర్ణయించడం,
CAUSE → IMPACT → SECOND-ORDER EFFECT → RISK → OPPORTUNITY
గా ఆలోచించడం మీ ప్రధాన బాధ్యత.

మీ output ఒక సాధారణ weekly summary లాగా కాకుండా,
ఒక Senior Institutional Analyst తన Investment Committee కి
వారాంతంలో ఇచ్చే professional research briefing లాగా ఉండాలి.
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

        def split_analysis(text, size=3200):
            return [text[i:i+size] for i in range(0, len(text), size)]

        report_parts = split_analysis(report_text)
        unique_id = int(time.time() * 1000)

        view_id = f"view_{unique_id}"
        back_id = f"back_{unique_id}"

        short_telegram_msg = (
            f"📊 <b>INSTITUTIONAL WEEKLY MARKET INTELLIGENCE</b>\n"
            f"🏢 విశ్లేషణ: CIO & Macro Research Desk\n"
            f"📑 డేటా: గత 7 రోజుల ({len(past_summaries)} Pulses) సమగ్ర రీసెర్చ్ నివేదిక\n"
            f"──────────────────────\n"
            f"💡 పూర్తి 16 విభాగాల ఇన్స్టిట్యూషనల్ నివేదిక చదవడానికి కింద ఉన్న బటన్‌ను నొక్కండి సార్!"
        )

        analysis_vault[view_id] = {
            "title": "INSTITUTIONAL WEEKLY MARKET INTELLIGENCE REPORT",
            "source": "CIO Investment Committee",
            "parts": report_parts,
            "original_text": short_telegram_msg,
            "back_key": back_id
        }
        analysis_vault[back_id] = view_id

        weekly_cache[current_week_key] = {
            "unique_id": unique_id,
            "short_msg": short_telegram_msg
        }

        markup = InlineKeyboardMarkup()
        view_btn = InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{unique_id}_0")
        markup.add(view_btn)

        bot.send_message(message.chat.id, short_telegram_msg, reply_markup=markup, parse_mode="HTML")

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

# ==========================================================
# 🧠 REUSABLE AI SUMMARY GENERATOR PIPELINE
# ==========================================================
def process_ai_summary(hours, pulse_title, pulse_type, chat_id=None):
    now = datetime.now(IST)
    cutoff_time = now - timedelta(hours=hours)
    
    normal_news = [
        n for n in rss_news_store 
        if isinstance(n, dict) 
        and n.get('time') >= cutoff_time 
        and n.get('type') == "NORMAL"
    ]
    total_news_count = len(normal_news)
    
    target_chat = chat_id or CHAT_ID
    
    if not normal_news:
        no_news_msg = f"⚡ 🎯 <b>{pulse_title}</b> ⚡\n📌 అప్‌డేట్: గత {hours} గంటల్లో విశ్లేషణకు తగిన వార్తలు ఏవీ నమోదు కాలేదు సార్."
        bot.send_message(target_chat, no_news_msg, parse_mode='HTML')
        return

    batch_size = 20
    aggregated_analysis_chunks = []

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
        if chunk_analysis and "AI అందుబాటులో లేదు" not in chunk_analysis:
            aggregated_analysis_chunks.append(chunk_analysis)
        time.sleep(3)

    combined_raw_analysis = "\n\n".join(aggregated_analysis_chunks)
    
    master_research_prompt = f"""
        మీరు ఒక ఇంటర్నేషనల్ రీసెర్చ్ టీమ్ హెడ్ (Elite Global Institutional Research Team Head). 
        గత {hours} గంటలుగా ({pulse_title}) సేకరించిన ఈ క్రింది కీలకమైన ఆర్థిక మరియు మార్కెట్ సమాచార సమూహాన్ని పూర్తిగా విశ్లేషించి, ఒక లోతైన ప్రొఫెషనల్ నివేదికను సిద్ధం చేయండి.
        
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
    
    # 🍃 MONGODB DATABASE SAVE (Morning / Evening Pulse)
    try:
        daily_summaries_col.insert_one({
            "date": datetime.now(IST),
            "pulse_type": pulse_type,
            "summary_text": final_master_summary,
            "news_count": total_news_count
        })
        log(f"📦 Saved {pulse_type} to MongoDB successfully!")
    except Exception as db_err:
        log(f"❌ Error saving summary to DB: {db_err}", "ERROR")

    def split_analysis(text, size=3200):
        return [text[i:i+size] for i in range(0, len(text), size)]

    report_parts = split_analysis(final_master_summary)
    unique_id = int(time.time() * 1000)

    view_id = f"view_{unique_id}"
    back_id = f"back_{unique_id}"

    short_telegram_msg = (
        f"💥 <b>{pulse_title}</b> 💥\n"
        f"🏢 నివేదిక: గత {hours} గంటల మార్కెట్ సమాచార సమగ్ర విశ్లేషణ\n"
        f"📊 మొత్తం స్కాన్ చేసిన వార్తలు: {total_news_count}\n"
        f"──────────────────────\n"
        f"💡 సమగ్ర నివేదిక చదవడానికి కింద ఉన్న బటన్‌ను నొక్కండి సార్!"
    )

    analysis_vault[view_id] = {
        "title": f"{pulse_type} ({total_news_count} News Items)",
        "source": "Global Research Desk",
        "parts": report_parts,
        "original_text": short_telegram_msg,
        "back_key": back_id
    }
    analysis_vault[back_id] = view_id

    markup = InlineKeyboardMarkup()
    view_btn = InlineKeyboardButton(text="🔎 పూర్తి విశ్లేషణ చదవండి (Read Full View)", callback_data=f"page_{unique_id}_0")
    markup.add(view_btn)

    bot.send_message(target_chat, short_telegram_msg, reply_markup=markup, parse_mode="HTML")

# ==========================================================
# ⏱️ SCHEDULED PULSE FUNCTIONS (MORNING 6 AM & EVENING 8 PM)
# ==========================================================
def send_daily_morning_pulse_report():
    log("⏰ Automatically generating Daily Morning Market Summary Report (8 PM to 6 AM)...")
    try:
        process_ai_summary(hours=10, pulse_title="DAILY MORNING MARKET PULSE (06:00 AM)", pulse_type="MORNING PULSE")
    except Exception as e:
        log(f"❌ Daily Morning Pulse Error: {e}", "ERROR")

def send_daily_evening_pulse_report():
    log("⏰ Automatically generating Daily Evening Market Summary Report (6 AM to 8 PM)...")
    try:
        process_ai_summary(hours=14, pulse_title="DAILY EVENING MARKET PULSE (08:00 PM)", pulse_type="EVENING PULSE")
    except Exception as e:
        log(f"❌ Daily Evening Pulse Error: {e}", "ERROR")

# ==========================================================
# 🤖 ON-DEMAND MORNING & SUMMARY COMMANDS
# ==========================================================
@bot.message_handler(commands=['morning'])
def cmd_morning_summary(message):
    log(f"📥 User {message.chat.id} triggered /morning command.")
    bot.send_message(message.chat.id, "⏳ <b>చంటి గారు, నిన్న రాత్రి 8 PM నుండి ఈరోజు ఉదయం 6 AM వరకు వచ్చిన ఓవర్‌నైట్ వార్తలను విశ్లేషిస్తున్నాను...</b>", parse_mode='HTML')
    process_ai_summary(hours=10, pulse_title="MORNING OVERNIGHT PULSE", pulse_type="MORNING PULSE", chat_id=message.chat.id)

@bot.message_handler(commands=['summary'])
def master_ai_summary_by_hours(message):
    log(f"📥 Command Received: User {message.chat.id} triggered '{message.text}'")
    args = message.text.split()
    hour = int(args[1]) if len(args) > 1 and args[1].isdigit() else 6
    bot.send_message(message.chat.id, f"⏳ <b>చంటి గారు, గత {hour} గంటల మార్కెట్ వార్తలను విశ్లేషిస్తున్నాను...</b>", parse_mode='HTML')
    process_ai_summary(hours=hour, pulse_title=f"CUSTOM MARKET SUMMARY (Past {hour} Hours)", pulse_type="CUSTOM SUMMARY", chat_id=message.chat.id)

# ==========================================================
# ⏱️ SINGLE-LIST NEWS COMMANDS BY SOURCE
# ==========================================================
@bot.message_handler(commands=['xnews'])
def get_x_news_list(message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): 
        bot.send_message(message.chat.id, "⚠️ <b>గంటలను ఇవ్వండి సార్!</b>\nఉదాహరణ: <code>/xnews 6</code>", parse_mode='HTML')
        return
    fetch_filtered_news_list(message, source_type="X", hour=int(args[1]), title_label="ET NOW (X)")

@bot.message_handler(commands=['normalnews'])
def get_normal_news_list(message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit(): 
        bot.send_message(message.chat.id, "⚠️ <b>గంటలను ఇవ్వండి సార్!</b>\nఉదాహరణ: <code>/normalnews 6</code>", parse_mode='HTML')
        return
    fetch_filtered_news_list(message, source_type="NORMAL", hour=int(args[1]), title_label="Investing / Normal RSS")

def fetch_filtered_news_list(message, source_type, hour, title_label):
    log(f"📥 Command Triggered: {message.text} for {title_label}")
    target_time = calculate_historical_target_time(hour)
    
    filtered = []
    for n in rss_news_store:
        if isinstance(n, dict) and n.get('time') >= target_time:
            src = n.get('source', '')
            n_type = n.get('type', '')
            
            if source_type == "REDBOX" and ("Redbox" in src or "REDBOX" in src):
                filtered.append(n)
            elif source_type == "NORMAL" and (n_type == "NORMAL" or "Investing" in src):
                filtered.append(n)
            elif source_type == "X" and ("ET NOW" in src or n_type == "X"):
                if "Redbox" not in src:
                    filtered.append(n)

    filtered.sort(key=lambda x: x['time'])
    total_count = len(filtered)
    current_time_str = datetime.now(IST).strftime('%I:%M %p')

    if not filtered:
        bot.send_message(message.chat.id, f"⏳ గత ({hour}) గంటల్లో <b>{title_label}</b> నుండి ఏ వార్తలు రికార్డ్ అవ్వలేదు సార్.", parse_mode='HTML')
        return

    header = (
        f"📋 <b>{title_label} లైవ్ వార్తల లిస్ట్ (గత {hour} గంటలు):</b>\n"
        f"🕒 <b>సమయం:</b> {current_time_str}\n"
        f"📊 <b>మొత్తం వార్తలు:</b> {total_count}\n"
        f"──────────────────────\n\n"
    )

    list_lines = []
    for i, n in enumerate(filtered, 1):
        arrival_time = n['time'].astimezone(IST).strftime('%I:%M %p')
        title = n.get('title', '')
        line = f"<b>{i}. [{arrival_time}]:</b> {safe_html_text(title)}\n"
        list_lines.append(line)

    full_text = header + "\n".join(list_lines)
    send_long_message(message.chat.id, full_text, parse_mode='HTML')

# ==========================================================
# 🤖 COMMANDS LIST HANDLER
# ==========================================================
def get_commands_list_text():
    return (
        "╔════════════════════════╗\n"
        "   🤖 <b>MARKET BOT COMMANDS</b> 📊\n"
        "╚════════════════════════╝\n\n"
        "🧠 <b>AI DEEP RESEARCH SUMMARIES</b>\n"
        "🔹 <code>/morning</code> (8 PM to 6 AM Overnight AI Pulse)\n"
        "🔹 <code>/summary [hours]</code> (On-Demand AI Research with Read Full View)\n"
        "🔹 <code>/weekly</code> (7-Day 14 Pulses Master Blueprint)\n\n"
        "⏱ <b>SINGLE LIST NEWS BY SOURCE</b>\n"
        "🔸 <code>/xnews [hours]</code> (ET NOW X Only)\n"
        "🔸 <code>/normalnews [hours]</code> (Investing / Normal RSS Only)\n"
        "──────────────────────\n"
        "🔸 <code>/get [hour]</code> (Normal RSS Detail Flash)\n"
        "🔸 <code>/getx [hour]</code> (X RSS Detail Flash)\n"
        "🔸 <code>/getred [hour]</code> (Redbox X RSS Detail Flash)\n"
        "──────────────────────\n"
        "⏰ <b>AUTOMATIC SCHEDULES</b>\n"
        "📌 <code>Daily 06:00 AM</code> (Auto Morning Pulse & DB Save)\n"
        "📌 <code>Daily 08:00 PM</code> (Auto Evening Pulse & DB Save)\n"
        "📌 <code>Every 10 Mins</code> (Global Market Live Table)\n"
        "──────────────────────\n"
        "📌 <i>చంటి గారు, కమాండ్ కాపీ చేయడానికి Tap చేయండి!</i>"
    )

@bot.message_handler(commands=['list'])
def list_commands(message): 
    log(f"📥 User {message.chat.id} requested commands /list.")
    safe_send(get_commands_list_text(), chat_id=message.chat.id)

# ==========================================================
# ⏱️ BACKGROUND ALERTS & WEB SERVER 
# ==========================================================
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

scheduler.add_job(send_market_table, 'interval', minutes=10)
scheduler.add_job(send_daily_morning_pulse_report, 'cron', hour=15, minute=0)
scheduler.add_job(send_daily_evening_pulse_report, 'cron', hour=16, minute=0)
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

import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
import base64
import yaml
import shutil
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. SETUP & AUTH
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False

try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except:
    st.error("❌ config.yaml missing"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is not True:
    st.warning("🔒 Login Required"); st.stop()

# ==============================================================================
# 2. DATABASE ENGINE (THE ULTIMATE FIX)
# ==============================================================================
DB_NAME = "scraper_pro_final.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, keyword TEXT, city TEXT, country TEXT, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
        
        # Ensure all columns exist (Migration)
        cursor.execute("PRAGMA table_info(leads)")
        cols = [c[1] for c in cursor.fetchall()]
        for target in ['country', 'whatsapp', 'email', 'website']:
            if target not in cols:
                cursor.execute(f"ALTER TABLE leads ADD COLUMN {target} TEXT")
        conn.commit()

init_db()

def create_session(query_text):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (query_text, time.strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        return cur.lastrowid

def save_lead(session_id, d):
    """Explicit column mapping to prevent 'Data Not Found' error"""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                VALUES (:sid, :kw, :ct, :co, :nm, :ph, :web, :em, :adr, :wa)
            """, {
                "sid": session_id, "kw": d['Keyword'], "ct": d['City'], "co": d['Country'],
                "nm": d['Name'], "ph": d['Phone'], "web": d.get('Website', 'N/A'),
                "em": d.get('Email', 'N/A'), "adr": d.get('Address', 'N/A'), "wa": d.get('WhatsApp', 'N/A')
            })
            conn.commit()
    except Exception as e: print(f"Save Failure: {e}")

# ==============================================================================
# 3. SCRAPER CORE
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium: opts.binary_location = chromium
    
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

# ==============================================================================
# 4. UI & FILTERS
# ==============================================================================
st.markdown("<style>div.stButton > button:first-child { background-color: #FF4B2B; color:white; font-weight:bold; }</style>", unsafe_allow_html=True)

with st.sidebar:
    st.title("👤 Profile")
    user = st.session_state["username"]
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance FROM user_credits WHERE username=?", (user,)).fetchone()
        bal = res[0] if res else 100
    st.info(f"Credits: {bal if user != 'admin' else 'Unlimited'}")
    if st.button("Logout"): authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# Inputs
c1, c2, c3, c4 = st.columns([3,3,2,1])
kw_in = c1.text_input("Keywords", placeholder="cafe, lawyer")
city_in = c2.text_input("Cities", placeholder="Agadir, Casa")
country_in = c3.selectbox("Country", ["Morocco", "France", "USA", "Spain", "UAE"])
limit_in = c4.number_input("Limit", 1, 500, 20)

st.divider()
f1, f2, f3, f4 = st.columns(4)
check_phone = f1.checkbox("Must Have Phone", value=True)
check_web = f2.checkbox("Must Have Website", value=False)
check_email = f3.checkbox("Deep Email Scan", value=False)
depth = st.slider("Scroll Depth", 1, 50, 10)

if st.button("🚀 START ENGINE") and kw_in and city_in:
    st.session_state.running = True
    s_id = create_session(f"{kw_in} | {city_in}")
    all_data = []
    
    driver = get_driver()
    try:
        keywords = [k.strip() for k in kw_in.split(',')]
        cities = [c.strip() for c in city_in.split(',')]
        
        for city in cities:
            for kw in keywords:
                if not st.session_state.running: break
                
                gl_code = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                query = quote(f"{kw} in {city} {country_in}")
                driver.get(f"https://www.google.com/maps/search/{query}?hl=en&gl={gl_code}")
                time.sleep(4)
                
                # Scroll
                try:
                    pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                    for _ in range(depth):
                        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                        time.sleep(1.5)
                except: pass
                
                # Elements
                items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                count = 0
                for item in items:
                    if count >= limit_in or not st.session_state.running: break
                    try:
                        driver.execute_script("arguments[0].click();", item)
                        time.sleep(2)
                        
                        name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                        phone = "N/A"
                        try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                        except: pass
                        
                        web = "N/A"
                        try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                        except: pass
                        
                        # 🔥 STRICT FILTERS LOGIC
                        if check_phone and (phone == "N/A" or not phone): continue
                        if check_web and (web == "N/A" or not web): continue
                        
                        # WhatsApp
                        wa = "N/A"
                        clean_p = re.sub(r'\D', '', phone)
                        if any(clean_p.startswith(x) for x in ['2126', '2127', '06', '07']):
                            wa = f"https://wa.me/{clean_p}"

                        row = {"Keyword":kw, "City":city, "Country":country_in, "Name":name, "Phone":phone, "Website":web, "WhatsApp":wa}
                        all_data.append(row)
                        save_lead(s_id, row) # Save immediately
                        st.dataframe(pd.DataFrame(all_data), use_container_width=True)
                        count += 1
                    except: continue
        st.success("✅ Extraction Completed & Saved to Archives!")
    finally:
        driver.quit()
        st.session_state.running = False

# ==============================================================================
# 5. ARCHIVES (PRO READER)
# ==============================================================================
st.header("📜 Search Archives")
search_filter = st.text_input("🔍 Filter by City/Keyword", "")

with sqlite3.connect(DB_NAME) as conn:
    query = "SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC"
    sessions = pd.read_sql(query, conn, params=(f"%{search_filter}%",))

if not sessions.empty:
    for idx, s in sessions.iterrows():
        with st.expander(f"📦 {s['date']} | {s['query']}"):
            with sqlite3.connect(DB_NAME) as conn:
                # DYNAMIC READ: Reads whatever exists
                leads = pd.read_sql(f"SELECT * FROM leads WHERE session_id={s['id']}", conn)
                if not leads.empty:
                    st.dataframe(leads.drop(columns=['id', 'session_id']), use_container_width=True)
                else:
                    st.warning("Empty result for this session.")
else:
    st.info("No archives found.")

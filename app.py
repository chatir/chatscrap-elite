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
# 1. ELITE SYSTEM CONFIG
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro v9", layout="wide", page_icon="💎")

if 'running' not in st.session_state: st.session_state.running = False
if 'results_df' not in st.session_state: st.session_state.results_df = None

# ==============================================================================
# 2. THE NUCLEAR DATABASE FIX
# ==============================================================================
# اسم جديد لضمان توافق الأعمدة 100%
DB_NAME = "chatscrap_elite_pro_v9.db"
OLD_DB = "scraper_pro_final.db"

def init_db_v9():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # الجلسات
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
        # النتائج (تصميم نظيف وموحد)
        cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            session_id INTEGER, 
            keyword TEXT, city TEXT, country TEXT, 
            name TEXT, phone TEXT, website TEXT, 
            email TEXT, address TEXT, whatsapp TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id))''')
        # المستخدمين
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_credits 
            (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
        conn.commit()

    # محاولة نقل "ياسين ومريم" من القاعدة القديمة إن وجدت
    if os.path.exists(OLD_DB):
        try:
            with sqlite3.connect(OLD_DB) as old_conn:
                old_users = pd.read_sql("SELECT * FROM user_credits", old_conn)
                with sqlite3.connect(DB_NAME) as new_conn:
                    for _, row in old_users.iterrows():
                        new_conn.execute("INSERT OR IGNORE INTO user_credits VALUES (?, ?, ?)", 
                                       (row['username'], row['balance'], row['status']))
                    new_conn.commit()
        except: pass

init_db_v9()

# ==============================================================================
# 3. AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except:
    st.error("❌ config.yaml required"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is not True:
    st.warning("🔒 Restricted Access"); st.stop()

# ==============================================================================
# 4. DATABASE OPERATIONS
# ==============================================================================
def create_session(q_text):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (q_text, time.strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        return cur.lastrowid

def save_lead_v9(session_id, d):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""INSERT INTO leads 
                (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, d['Keyword'], d['City'], d['Country'], d['Name'], d['Phone'], 
                 d.get('Website','N/A'), d.get('Email','N/A'), d.get('Address','N/A'), d.get('WhatsApp','N/A')))
            conn.commit()
    except Exception as e: print(f"DB Error: {e}")

def get_credits(user):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance FROM user_credits WHERE username=?", (user,)).fetchone()
        if res: return res[0]
        conn.execute("INSERT INTO user_credits VALUES (?, 100, 'active')", (user,))
        conn.commit()
        return 100

def deduct_credit(user):
    if user != 'admin':
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (user,))
            conn.commit()

# ==============================================================================
# 5. SCRAPER ENGINE
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    # الكشف عن chromium فالسيرفر
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium: opts.binary_location = chromium
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

# ==============================================================================
# 6. UI & LAYOUT
# ==============================================================================
st.markdown("""<style>
    .stButton>button { border-radius: 8px; font-weight: bold; height: 3em; width: 100%; }
    .main { background-color: #0e1117; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("👤 Account")
    user = st.session_state["username"]
    bal = get_credits(user)
    st.metric("Credits Available", "Unlimited" if user == 'admin' else bal)
    
    if user == 'admin':
        with st.expander("🛠 Admin Tools"):
            u_list = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(u_list, hide_index=True)
            target = st.selectbox("Select User", u_list['username'])
            if st.button("Add 100 Credits"):
                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET balance = balance + 100 WHERE username=?", (target,))
                st.rerun()

    st.divider()
    if st.button("🚪 Logout"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- INPUT AREA ---
st.title("🕷️ ChatScrap Pro Elite")
c1, c2, c3, c4 = st.columns([3,3,2,1])
kw_in = c1.text_input("🔍 Keywords (Comma separated)", placeholder="cafe, lawyer")
city_in = c2.text_input("🌍 Cities", placeholder="Agadir, Casablanca")
country_in = c3.selectbox("🏴 Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"])
limit_in = c4.number_input("Limit/City", 1, 1000, 20)

st.divider()
f1, f2, f3, f4 = st.columns(4)
check_phone = f1.checkbox("✅ Must have Phone", True)
check_web = f2.checkbox("🌐 Must have Website", False)
check_email = f3.checkbox("📧 Deep Email Scan", False)
scroll_depth = f4.slider("Scroll Depth", 1, 100, 10)

if st.button("🚀 START EXTRACTION") and kw_in and city_in:
    st.session_state.running = True
    s_id = create_session(f"{kw_in} | {city_in} | {country_in}")
    st.session_state.results_df = []
    
    driver = get_driver()
    try:
        keywords = [k.strip() for k in kw_in.split(',')]
        cities = [c.strip() for c in city_in.split(',')]
        
        for city in cities:
            for kw in keywords:
                if not st.session_state.running: break
                st.toast(f"Searching: {kw} in {city}...")
                
                gl = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                q = quote(f"{kw} in {city} {country_in}")
                driver.get(f"https://www.google.com/maps/search/{q}?hl=en&gl={gl}")
                time.sleep(5)
                
                # Scrolling
                try:
                    pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                    for _ in range(scroll_depth):
                        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                        time.sleep(2)
                except: pass
                
                # Fetching
                items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                count = 0
                for item in items:
                    if count >= limit_in or not st.session_state.running: break
                    if user != 'admin' and get_credits(user) <= 0:
                        st.error("No credits left!"); st.stop()
                    
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
                        
                        # 🔥 PRE-SAVE FILTERS
                        if check_phone and (phone == "N/A" or not phone): continue
                        if check_web and (web == "N/A" or not web): continue
                        
                        # WhatsApp Logic
                        wa = "N/A"
                        clean_p = re.sub(r'\D', '', phone)
                        if any(clean_p.startswith(x) for x in ['2126','2127','06','07']):
                            wa = f"https://wa.me/{clean_p}"

                        data = {"Keyword":kw, "City":city, "Country":country_in, "Name":name, "Phone":phone, "Website":web, "WhatsApp":wa}
                        
                        # الحفظ فوراً
                        save_lead_v9(s_id, data)
                        deduct_credit(user)
                        
                        st.session_state.results_df.append(data)
                        st.dataframe(pd.DataFrame(st.session_state.results_df), use_container_width=True)
                        count += 1
                    except: continue
        st.success("Extraction Completed!")
    finally:
        driver.quit()
        st.session_state.running = False

# ==============================================================================
# 7. THE FIXED ARCHIVE
# ==============================================================================
st.divider()
st.header("📜 Search History & Archives")
search_filter = st.text_input("🔍 Search within archives (City or Keyword)", "")

with sqlite3.connect(DB_NAME) as conn:
    s_query = "SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC"
    sessions = pd.read_sql(s_query, conn, params=(f"%{search_filter}%",))

if not sessions.empty:
    for idx, s in sessions.iterrows():
        with st.expander(f"📦 {s['date']} | {s['query']}"):
            with sqlite3.connect(DB_NAME) as conn:
                leads = pd.read_sql(f"SELECT * FROM leads WHERE session_id = {s['id']}", conn)
                if not leads.empty:
                    # تنظيف العرض
                    leads_clean = leads.drop(columns=['id', 'session_id'])
                    st.dataframe(leads_clean, use_container_width=True)
                    st.download_button("📥 Export CSV", 
                                     leads_clean.to_csv(index=False).encode('utf-8-sig'), 
                                     f"search_{s['id']}.csv", key=f"dl_{s['id']}")
                else:
                    st.warning("No data found for this session (stopped or filtered out).")
else:
    st.info("No archives match your search.")

st.markdown('<div style="text-align:center;color:#666;padding:20px;">Designed by Chatir Elite Pro v9</div>', unsafe_allow_html=True)

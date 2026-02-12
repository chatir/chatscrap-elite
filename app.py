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
# 1. ELITE GLOBAL CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

# Initialize persistent session states
if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status' not in st.session_state: st.session_state.status = "IDLE"
if 's_id' not in st.session_state: st.session_state.s_id = None

# ==============================================================================
# 2. THE DESIGNER'S CSS (PRO UI)
# ==============================================================================
orange_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)"
dark_bg = "#0e1117"

st.markdown(f"""
    <style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, .stApp {{ font-family: 'Inter', sans-serif !important; background-color: {dark_bg}; color: white; }}
    
    /* Uniform Button Design */
    .stButton > button {{
        width: 100% !important;
        height: 45px !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }}
    
    /* Primary Action Button */
    div.stButton > button[kind="primary"] {{
        background: {orange_grad} !important;
        color: white !important;
        box-shadow: 0 4px 15px rgba(255, 69, 0, 0.3) !important;
    }}
    div.stButton > button[kind="primary"]:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(255, 69, 0, 0.5) !important; }}
    
    /* Secondary/Stop Button */
    div.stButton > button[kind="secondary"] {{ background-color: #262730 !important; color: white !important; }}
    
    /* Profile & Metric Styling */
    [data-testid="stMetricValue"] {{ color: #FF8C00 !important; font-weight: 800 !important; }}
    .logo-img {{ width: 260px; filter: drop-shadow(0 0 12px rgba(255,140,0,0.4)); margin-bottom: 20px; }}
    
    /* Progress Bar Customization */
    .stProgress > div > div > div > div {{ background: {orange_grad} !important; }}
    
    /* Sidebar Cleanup */
    section[data-testid="stSidebar"] {{ background-color: #161922 !important; border-right: 1px solid #31333F; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. DATABASE ENGINE (v9 STABLE)
# ==============================================================================
DB_NAME = "chatscrap_elite_pro_v9.db"

def init_db():
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)")
        cursor.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, 
            keyword TEXT, city TEXT, country TEXT, name TEXT, phone TEXT, 
            website TEXT, email TEXT, address TEXT, whatsapp TEXT)""")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')")
        conn.commit()

init_db()

def get_user_data(username):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance, status FROM user_credits WHERE username=?", (username,)).fetchone()
        if res: return res
        conn.execute("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,))
        conn.commit()
        return (100, 'active')

def update_credits(username, amount):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))
        conn.commit()

# ==============================================================================
# 4. AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("config.yaml not found"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass
    if st.session_state["authentication_status"] is not True:
        st.warning("🔒 Please Login"); st.stop()

# ==============================================================================
# 5. SCRAPER CORE (SERVER READY)
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

def fetch_email(driver, url):
    if not url or "google" in url: return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        driver.set_page_load_timeout(8); driver.get(url); time.sleep(1)
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
        valid = [e for e in emails if not e.endswith(('.png','.jpg','.webp'))]
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return valid[0] if valid else "N/A"
    except: 
        if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==============================================================================
# 6. SIDEBAR & ADMIN (NON-INTERRUPTING)
# ==============================================================================
with st.sidebar:
    # Logo
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    st.title("👤 Profile")
    user = st.session_state["username"]
    bal, sts = get_user_data(user)
    
    if sts == 'suspended' and user != 'admin': st.error("ACCOUNT SUSPENDED"); st.stop()
    st.metric("Balance", "💎 Unlimited" if user == 'admin' else f"💎 {bal}")
    
    if user == 'admin':
        with st.expander("🛠️ ADMIN PANEL"):
            all_u = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(all_u, hide_index=True)
            tgt = st.selectbox("Target User", all_u['username'])
            c1, c2 = st.columns(2)
            if c1.button("💰 +100"): update_credits(tgt, 100); st.rerun()
            if c2.button("🗑️ Delete"):
                with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM user_credits WHERE username=?", (tgt,))
                st.rerun()
            
            st.divider()
            new_un = st.text_input("New Username")
            new_pw = st.text_input("New Password", type="password")
            if st.button("Create User"):
                try: hp = stauth.Hasher.hash(new_pw)
                except: hp = stauth.Hasher([new_pw]).generate()[0]
                config['credentials']['usernames'][new_un] = {'name': new_un, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                get_user_data(new_un) # Init credits
                st.success("User Created!"); st.rerun()

    st.divider()
    if st.button("🚪 Sign Out", key="logout"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 7. MAIN ENGINE AREA
# ==============================================================================
st.title("🕷️ ChatScrap Pro Elite")

# Input Section
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
    keywords_in = c1.text_input("🔍 Keywords", placeholder="cafe, restaurant")
    cities_in = c2.text_input("🌍 Cities", placeholder="Agadir, Casablanca")
    country_in = c3.selectbox("🏴 Country", ["Morocco", "France", "USA", "Spain", "UK", "UAE"])
    limit_in = c4.number_input("Limit/City", 1, 1000, 20)

    st.divider()
    f1, f2, f3, f4 = st.columns([1,1,1,1.5])
    w_phone = f1.checkbox("Must Have Phone", True)
    w_web = f2.checkbox("Must Have Website", False)
    w_email = f3.checkbox("Deep Email Scan", False)
    depth_in = f4.slider("Scroll Depth", 1, 100, 10)

    b1, b2 = st.columns(2)
    if b1.button("🚀 START EXTRACTION", type="primary"):
        if keywords_in and cities_in:
            st.session_state.running = True
            st.session_state.results_list = []
            st.session_state.progress = 0
            # Create Session
            with sqlite3.connect(DB_NAME) as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{keywords_in} | {cities_in}", time.strftime("%Y-%m-%d %H:%M")))
                st.session_state.s_id = cur.lastrowid
                conn.commit()
            st.rerun()

    if b2.button("🛑 STOP ENGINE", type="secondary"):
        st.session_state.running = False
        st.rerun()

# ==============================================================================
# 8. BACKGROUND PROCESSING LOOP
# ==============================================================================
tab_live, tab_archive, tab_tools = st.tabs(["⚡ LIVE RESULTS", "📜 ARCHIVES", "🤖 MARKETING"])

with tab_live:
    prog_bar = st.progress(st.session_state.progress)
    status_txt = st.empty()
    table_spot = st.empty()
    
    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list)
        table_spot.dataframe(df_live, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat")})

    if st.session_state.running:
        driver = get_driver()
        try:
            kws = [k.strip() for k in keywords_in.split(',')]
            cts = [c.strip() for c in cities_in.split(',')]
            total_ops = len(kws) * len(cts)
            curr_op = 0

            for city in cts:
                for kw in kws:
                    if not st.session_state.running: break
                    curr_op += 1
                    percent = int((curr_op/total_ops)*100)
                    st.session_state.progress = percent
                    prog_bar.progress(percent)
                    status_txt.markdown(f"**Current Scan:** {kw} in {city}...")
                    
                    gl_code = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                    driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl_code}")
                    time.sleep(4)

                    # Deep Scroll
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                            time.sleep(1.2)
                    except: pass

                    # Extract
                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    v_cnt = 0
                    for item in items:
                        if v_cnt >= limit_in or not st.session_state.running: break
                        try:
                            driver.execute_script("arguments[0].click();", item); time.sleep(2)
                            
                            # Data Points
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            phone = "N/A"
                            try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                            except: pass
                            web = "N/A"
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            addr = "N/A"
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe').text
                            except: pass

                            # Filters
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_web and (web == "N/A" or not web): continue

                            # Smart WhatsApp (No 05)
                            wa = "N/A"
                            cp = re.sub(r'\D', '', phone)
                            if any(cp.startswith(x) for x in ['2126','2127','06','07']) and not (cp.startswith('2125') or cp.startswith('05')):
                                wa = f"https://wa.me/{cp}"

                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email(driver, web)

                            row = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa, "Website":web, "Email":email, "Address":addr}
                            
                            # Atomic Save
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.s_id, kw, city, country_in, name, phone, web, email, addr, wa))
                                if user != 'admin': conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (user,))
                            
                            st.session_state.results_list.append(row)
                            table_spot.dataframe(pd.DataFrame(st.session_state.results_list), use_container_width=True)
                            v_cnt += 1
                        except: continue
            st.success("✅ TASK COMPLETED")
        finally:
            driver.quit()
            st.session_state.running = False
            st.rerun()

# ==============================================================================
# 9. ARCHIVES (STABLE)
# ==============================================================================
with tab_archive:
    st.subheader("📜 Archives")
    search_q = st.text_input("🔍 Search History (City/Keyword)")
    with sqlite3.connect(DB_NAME) as conn:
        sessions = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 20", conn, params=(f"%{search_q}%",))
    
    for _, s in sessions.iterrows():
        with st.expander(f"📦 {s['date']} | {s['query']}"):
            leads = pd.read_sql(f"SELECT * FROM leads WHERE session_id={s['id']}", sqlite3.connect(DB_NAME))
            if not leads.empty:
                df_c = leads.drop(columns=['id', 'session_id'])
                st.dataframe(df_c, use_container_width=True)
                st.download_button("📥 CSV", df_c.to_csv(index=False).encode('utf-8-sig'), f"archive_{s['id']}.csv")
            else: st.warning("No data found.")

with tab_tools:
    st.subheader("🤖 Marketing Kit")
    if st.button("Generate Cold Message"):
        st.code(f"Hi! Found your business in {cities_in}. I noticed your business...")

st.markdown('<div style="text-align:center;color:#666;padding:20px;">Designed by Chatir Elite Pro v12 | Designer Beast</div>', unsafe_allow_html=True)

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
# 1. GLOBAL CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status_msg' not in st.session_state: st.session_state.status_msg = "READY"
if 'current_sid' not in st.session_state: st.session_state.current_sid = None

# ==============================================================================
# 2. DESIGNER ULTIMATE CSS (NO GAPS / SMART PROGRESS)
# ==============================================================================
orange_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [data-testid="stAppViewContainer"] {{ font-family: 'Inter', sans-serif !important; background-color: #0e1117; }}

    /* Center Logo */
    .centered-logo {{ text-align: center; padding: 10px 0 30px 0; }}
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.3)); }}

    /* 🔥 THE GAPS FIX: Force columns to touch */
    [data-testid="column"] {{
        padding-left: 0 !important;
        padding-right: 0 !important;
        margin-left: -1px !important; /* Close the 1px ghost gap */
    }}
    
    .stButton > button {{
        width: 100% !important;
        height: 56px !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        border: none !important;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        transition: 0.3s all ease;
    }}
    
    /* START BUTTON - LEFT ROUNDED */
    div.stButton > button[kind="primary"] {{
        background: {orange_grad} !important;
        color: white !important;
        border-radius: 12px 0 0 12px !important;
    }}
    
    /* STOP BUTTON - RIGHT ROUNDED */
    div.stButton > button[kind="secondary"] {{
        background-color: #1c212d !important;
        color: #ff4b4b !important;
        border: 1px solid #31333f !important;
        border-radius: 0 12px 12px 0 !important;
    }}

    /* 🔥 ANIMATED PROGRESS BAR V2 */
    .prog-container {{ width: 100%; background: #1c212d; border-radius: 50px; padding: 4px; border: 1px solid #31333f; margin: 25px 0; }}
    .prog-bar-fill {{ 
        height: 14px; 
        background: repeating-linear-gradient(45deg, #FF8C00, #FF8C00 12px, #FF4500 12px, #FF4500 24px); 
        border-radius: 20px; 
        transition: width 0.6s ease-in-out; 
        animation: stripes 1.2s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 48px 48px;}} }}

    /* Sidebar & Metrics */
    [data-testid="stMetricValue"] {{ color: #FF8C00 !important; font-weight: 800; }}
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
        st.warning("🔒 Login to Start the Extraction"); st.stop()

# ==============================================================================
# 5. SIDEBAR (ADMIN PANEL)
# ==============================================================================
with st.sidebar:
    st.title("Profile")
    me = st.session_state["username"]
    bal, sts = get_user_data(me)
    
    if sts == 'suspended' and me != 'admin': st.error("Account Suspended"); st.stop()
    st.metric("Elite Balance", "💎 Unlimited" if me == 'admin' else f"💎 {bal}")
    
    if me == 'admin':
        with st.expander("Admin Settings"):
            u_df = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(u_df, hide_index=True)
            target = st.selectbox("Select Target User", u_df['username'])
            
            c_a, c_b, c_c = st.columns(3)
            if c_a.button("💰 +100"): 
                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET balance = balance + 100 WHERE username=?", (target,)); st.rerun()
            if c_b.button("🚫 Status"):
                curr = sqlite3.connect(DB_NAME).execute("SELECT status FROM user_credits WHERE username=?", (target,)).fetchone()[0]
                new_s = 'suspended' if curr == 'active' else 'active'
                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET status=? WHERE username=?", (new_s, target)); st.rerun()
            if c_c.button("🗑️ Del"):
                sqlite3.connect(DB_NAME).execute("DELETE FROM user_credits WHERE username=?", (target,)); st.rerun()

    st.divider()
    if st.button("Sign Out"): authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 6. HEADER LOGO
# ==============================================================================
if os.path.exists("chatscrape.png"):
    with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
    st.markdown(f'<div class="centered-logo"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)

# ==============================================================================
# 7. INPUTS & THE "ZERO GAP" BUTTONS
# ==============================================================================
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1.5])
    kw_in = c1.text_input("Keywords", placeholder="cafe, snak, etc.")
    city_in = c2.text_input("Cities", placeholder="Agadir, Casablanca")
    country_in = c3.selectbox("Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"])
    limit_in = c4.number_input("Limit/City", 1, 1000, 20)

    st.divider()
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1.2, 1.2, 1.5])
    w_phone = f1.checkbox("Phone", True)
    w_web = f2.checkbox("Website", False)
    w_email = f3.checkbox("Deep Email", False)
    w_nosite = f4.checkbox("No Site Only", False)
    depth_in = f5.slider("Scroll Depth", 1, 100, 10)

    st.write("")
    # 🔥 THE TRUE 50/50 NO-GAP BAR
    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("Start Extraction", type="primary"):
            if kw_in and city_in:
                st.session_state.running = True
                st.session_state.results_list = []
                st.session_state.progress = 0 # RESET PROGRESS
                with sqlite3.connect(DB_NAME) as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
                    st.session_state.current_sid = cur.lastrowid
                    conn.commit()
                st.rerun()
    with btn_col2:
        if st.button("Stop Engine", type="secondary"):
            st.session_state.running = False; st.rerun()

# ==============================================================================
# 8. ENGINE & CUSTOM PROGRESS BAR LOGIC
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    path = shutil.which("chromium") or shutil.which("chromium-browser")
    if path: opts.binary_location = path
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

tab_live, tab_archive, tab_tools = st.tabs(["⚡ Live Data", "📜 Archives", "🤖 Marketing"])

with tab_live:
    # 🔥 PROGRESS BAR SPOT (STARTS AT 0)
    prog_spot = st.empty()
    status_ui = st.empty()
    table_ui = st.empty()
    
    # Show initial state if progress is 0 but script is idle
    if not st.session_state.running and st.session_state.progress == 0:
        prog_spot.markdown('<div class="prog-container"><div class="prog-bar-fill" style="width: 0%;"></div></div>', unsafe_allow_html=True)
    elif st.session_state.progress > 0:
        prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)

    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list)
        table_ui.dataframe(df_live, use_container_width=True)

    if st.session_state.running:
        driver = get_driver()
        try:
            kws = [k.strip() for k in kw_in.split(',')]
            cts = [c.strip() for c in city_in.split(',')]
            total = len(kws) * len(cts)
            curr_op = 0

            for city in cts:
                for kw in kws:
                    if not st.session_state.running: break
                    curr_op += 1
                    # 🔥 REAL CALCULATION: Start small and increase
                    st.session_state.progress = int((curr_op / total) * 100)
                    prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)
                    status_ui.markdown(f"**Scanning:** `{kw}` in `{city}`...")
                    
                    gl = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                    driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl}")
                    time.sleep(4)

                    # Pane Scroll
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            if not st.session_state.running: break
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane); time.sleep(1)
                    except: pass

                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    seen = set(); v_cnt = 0
                    for item in items:
                        if v_cnt >= limit_in or not st.session_state.running: break
                        url = item.get_attribute("href")
                        if url in seen: continue
                        seen.add(url)
                        try:
                            driver.execute_script("arguments[0].click();", item); time.sleep(2)
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            phone = "N/A"
                            try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                            except: pass
                            web = "N/A"
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass

                            # Filters
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_web and (web == "N/A" or not web): continue
                            if w_nosite and web != "N/A": continue

                            # WhatsApp Check
                            wa = "N/A"; cp = re.sub(r'\D', '', phone)
                            if any(cp.startswith(x) for x in ['2126','2127','06','07']) and not (cp.startswith('2125') or cp.startswith('05')):
                                wa = f"https://wa.me/{cp}"

                            row = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa, "Website":web}
                            
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, whatsapp)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.current_sid, kw, city, country_in, name, phone, web, wa))
                                if me != 'admin': conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (me,))
                            
                            st.session_state.results_list.append(row)
                            table_ui.dataframe(pd.DataFrame(st.session_state.results_list), use_container_width=True)
                            v_cnt += 1
                        except: continue
            st.success("🏁 Task Completed!")
        finally:
            driver.quit(); st.session_state.running = False; st.rerun()

# ==============================================================================
# 9. ARCHIVE TAB (SEARCH ICON)
# ==============================================================================
with tab_archive:
    st.subheader("Search Archives")
    search_f = st.text_input("🔍 Filter History", placeholder="🔍 Search e.g., 'cafe' or 'agadir'...")
    
    with sqlite3.connect(DB_NAME) as conn:
        df_s = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{search_f}%",))
    
    if not df_s.empty:
        for _, sess in df_s.iterrows():
            with st.expander(f"📦 {sess['date']} | {sess['query']}"):
                with sqlite3.connect(DB_NAME) as conn:
                    df_l = pd.read_sql(f"SELECT * FROM leads WHERE session_id={sess['id']}", conn)
                if not df_l.empty:
                    st.dataframe(df_l.drop(columns=['id', 'session_id']), use_container_width=True)
                    st.download_button("📥 CSV", df_l.to_csv(index=False).encode('utf-8-sig'), f"export_{sess['id']}.csv", key=f"dl_{sess['id']}")
                else: st.warning("Empty result.")
    else: st.info("No matching archives.")

with tab_tools:
    if st.button("Generate Cold Message"):
        st.code(f"Hi! I found your business in {city_in}. I noticed your work...")

st.markdown('<div style="text-align:center;color:#666;padding:30px;">Designed by Chatir Elite Pro - Designer Ultimate</div>', unsafe_allow_html=True)

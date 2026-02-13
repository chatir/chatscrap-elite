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
# 1. GLOBAL CONFIGURATION & STATE (حفاظ تام على المتغيرات)
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'paused' not in st.session_state: st.session_state.paused = False
if 'task_index' not in st.session_state: st.session_state.task_index = 0
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status_msg' not in st.session_state: st.session_state.status_msg = "READY"
if 'current_sid' not in st.session_state: st.session_state.current_sid = None

if 'active_kw' not in st.session_state: st.session_state.active_kw = ""
if 'active_city' not in st.session_state: st.session_state.active_city = ""

# ==============================================================================
# 2. DESIGN SYSTEM (MODERN FLAT ORANGE & CHARCOAL)
# ==============================================================================
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">', unsafe_allow_html=True)

# ألوان من عائلة البرتقالي مع خلفية سوداء فحمية (بدون أزرق)
main_orange = "#FF8C00"
dark_bg = "#0A0A0A"
card_bg = "#1A1A1A"
border_col = "#333333"

if st.session_state.get("authentication_status") is not True:
    # --- FLAT LOGIN PAGE (ORANGE THEME) ---
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    [data-testid="stAppViewContainer"] {{ background-color: {dark_bg} !important; }}
    
    [data-testid="stVerticalBlock"] > div:has(div.stButton) {{
        background-color: {card_bg};
        padding: 50px !important;
        border: 1px solid {main_orange};
        border-radius: 8px;
        max-width: 420px;
        margin: auto;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }}
    
    .stTextInput input {{
        background-color: #222222 !important;
        color: white !important;
        border: 1px solid {border_col} !important;
        border-radius: 6px !important;
    }}
    
    .stButton > button {{
        background-color: {main_orange} !important;
        color: white !important;
        font-weight: 700 !important;
        height: 50px !important;
        border-radius: 6px !important;
        text-transform: uppercase;
        border: none !important;
    }}
    [data-testid="stHeader"], [data-testid="stSidebar"] {{ display: none; }}
    </style>
    """, unsafe_allow_html=True)
else:
    # --- FLAT DASHBOARD STYLE (ORANGE & BLACK) ---
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [data-testid="stAppViewContainer"] {{ 
        font-family: 'Inter', sans-serif !important; 
        background-color: {dark_bg} !important; 
    }}
    .centered-logo {{ text-align: center; padding: 20px 0 40px 0; }}
    .logo-img {{ width: 280px; }}
    
    /* Flat Buttons */
    .stButton > button {{ 
        width: 100% !important; height: 48px !important; font-weight: 700 !important; 
        border: none !important; border-radius: 4px !important; color: white !important; 
    }}
    
    div[data-testid="column"]:nth-of-type(1) .stButton > button {{ background-color: {main_orange} !important; }} /* Start */
    div[data-testid="column"]:nth-of-type(2) .stButton > button {{ background-color: #333333 !important; }} /* Pause */
    div[data-testid="column"]:nth-of-type(3) .stButton > button {{ background-color: #2D5A27 !important; }} /* Continue */
    div[data-testid="column"]:nth-of-type(4) .stButton > button {{ background-color: #A30000 !important; }} /* Stop */
    
    .stButton > button:disabled {{ opacity: 0.2 !important; }}

    /* Fix Progress Bar (Flat Design) */
    .prog-container {{ width: 100%; background: #222222; border-radius: 2px; padding: 0; border: 1px solid {border_col}; margin: 25px 0; height: 12px; overflow: hidden; }}
    .prog-bar-fill {{ height: 100%; background-color: {main_orange}; transition: width 0.5s ease-in-out; }}
    
    [data-testid="stMetricValue"] {{ color: {main_orange} !important; font-weight: 800; }}
    section[data-testid="stSidebar"] {{ background-color: {card_bg} !important; border-right: 1px solid {border_col}; }}
    
    /* WhatsApp Green */
    .wa-link {{ color: #25D366 !important; text-decoration: none !important; font-weight: bold; }}
    
    /* Tabs Flat */
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
    .stTabs [data-baseweb="tab"] {{ background-color: {card_bg}; color: #888; border: 1px solid {border_col}; padding: 10px 25px; border-radius: 4px 4px 0 0; }}
    .stTabs [aria-selected="true"] {{ background-color: {main_orange} !important; color: white !important; border-color: {main_orange} !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. DATABASE (FROM APP 15 - UNTOUCHED)
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
# 4. AUTHENTICATION & LOGIN UI (FIXED LOGO & POSITION)
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("config.yaml missing"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])

if st.session_state.get("authentication_status") is not True:
    # الشعار في صفحة الدخول
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center; padding-top: 100px; padding-bottom: 20px;"><img src="data:image/png;base64,{b64}" style="width:300px;"></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        try: authenticator.login()
        except: pass
        if st.session_state["authentication_status"] is False:
            st.error("Username/password is incorrect")
        if st.session_state["authentication_status"] is None:
            st.info("🔒 Elite Access Required")
        st.stop()

# ==============================================================================
# 5. SIDEBAR & ADMIN (FROM APP 15 - UNTOUCHED)
# ==============================================================================
with st.sidebar:
    st.title("Profile Settings")
    me = st.session_state["username"]
    bal, sts = get_user_data(me)
    if sts == 'suspended' and me != 'admin': st.error("Account Suspended"); st.stop()
    st.metric("Elite Balance", "💎 Unlimited" if me == 'admin' else f"💎 {bal}")
    
    if me == 'admin':
        with st.expander("🛠️ Admin Panel"):
            conn = sqlite3.connect(DB_NAME)
            u_df = pd.read_sql("SELECT * FROM user_credits", conn)
            st.dataframe(u_df, hide_index=True)
            target = st.selectbox("Manage User", u_df['username'])
            c1, c2, c3 = st.columns(3)
            if c1.button("💰 +100"): 
                conn.execute("UPDATE user_credits SET balance = balance + 100 WHERE username=?", (target,))
                conn.commit(); st.rerun()
            if c2.button("🚫 Status"):
                curr = conn.execute("SELECT status FROM user_credits WHERE username=?", (target,)).fetchone()[0]
                new_s = 'suspended' if curr == 'active' else 'active'
                conn.execute("UPDATE user_credits SET status=? WHERE username=?", (new_s, target))
                conn.commit(); st.rerun()
            if c3.button("🗑️ Del"):
                conn.execute("DELETE FROM user_credits WHERE username=?", (target,))
                conn.commit(); st.rerun()
            st.divider()
            st.write("Add New User:")
            nu = st.text_input("New Username", key="new_u")
            np = st.text_input("New Password", type="password", key="new_p")
            if st.button("Create Account"):
                if nu and np:
                    try: hashed_pw = stauth.Hasher.hash(np)
                    except: hashed_pw = stauth.Hasher([np]).generate()[0]
                    config['credentials']['usernames'][nu] = {'name': nu, 'password': hashed_pw, 'email': 'x'}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                    get_user_data(nu); st.success(f"User {nu} Created!"); st.rerun()

    st.divider()
    if st.button("Logout"): authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 6. HEADER LOGO (DASHBOARD)
# ==============================================================================
if os.path.exists("chatscrape.png"):
    with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
    st.markdown(f'<div class="centered-logo"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)

# ==============================================================================
# 7. INPUTS & 4-BUTTON ROW (FROM APP 15 - UNTOUCHED)
# ==============================================================================
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1.5])
    kw_in = c1.text_input("Keywords", placeholder="e.g. hotel, cafe", key="kw_in_key")
    city_in = c2.text_input("Cities", placeholder="e.g. Agadir, Casa", key="city_in_key")
    country_in = c3.selectbox("Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"], key="country_in_key")
    limit_in = c4.number_input("Limit/City", 1, 1000, 20, key="limit_in_key")

    st.divider()
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1, 1.5])
    w_phone = f1.checkbox("Phone Only", True)
    w_web = f2.checkbox("Website", False)
    w_email = f3.checkbox("Deep Email", False)
    w_nosite = f4.checkbox("No Site Only", False)
    depth_in = f5.slider("Scroll Depth", 1, 100, 10)

    st.write("")
    b_start, b_pause, b_cont, b_stop = st.columns(4)
    
    with b_start:
        if st.button("Start Search", disabled=st.session_state.running):
            if kw_in and city_in:
                st.session_state.active_kw = kw_in
                st.session_state.active_city = city_in
                st.session_state.running = True
                st.session_state.paused = False
                st.session_state.results_list = []
                st.session_state.progress = 0
                st.session_state.task_index = 0
                with sqlite3.connect(DB_NAME) as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
                    st.session_state.current_sid = cur.lastrowid
                    conn.commit()
                st.rerun()

    with b_pause:
        if st.button("Pause", disabled=not st.session_state.running or st.session_state.paused):
            st.session_state.paused = True
            st.rerun()

    with b_cont:
        if st.button("Continue", disabled=not st.session_state.running or not st.session_state.paused):
            st.session_state.paused = False
            st.rerun()

    with b_stop:
        if st.button("Stop Search", disabled=not st.session_state.running):
            st.session_state.running = False
            st.session_state.paused = False
            st.rerun()

# ==============================================================================
# 8. ENGINE & LOGIC (KEEPING 100% SAME AS APP 15)
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

def fetch_email_deep(driver, url):
    if not url or "google" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        try:
            driver.set_page_load_timeout(10)
            driver.get(url)
            time.sleep(2)
            page_source = driver.page_source
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_source)
            result = list(set(emails))[0] if emails else "N/A"
        except: result = "N/A"
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return result
    except:
        if len(driver.window_handles) > 1: driver.switch_to.window(driver.window_handles[0])
        return "N/A"

def convert_df(df): return df.to_csv(index=False).encode('utf-8')

tab_live, tab_archive, tab_tools = st.tabs(["⚡ Live Data", "📜 Archives", "🤖 Marketing"])

with tab_live:
    prog_spot = st.empty()
    status_ui = st.empty()
    table_ui = st.empty()
    download_ui = st.empty()
    
    # إصلاح ظهور شريط التقدم
    prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)

    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list)
        table_ui.write(df_live.to_html(escape=False, index=False), unsafe_allow_html=True)
        csv = convert_df(df_live)
        download_ui.download_button(label="⬇️ Download Results CSV", data=csv, file_name="extraction_results.csv", mime="text/csv", key='live_dl')

    if st.session_state.running and not st.session_state.paused:
        active_kws = [k.strip() for k in st.session_state.active_kw.split(',') if k.strip()]
        active_cts = [c.strip() for c in st.session_state.active_city.split(',') if c.strip()]
        all_tasks = [(c, k) for c in active_cts for k in active_kws]
        
        if all_tasks:
            driver = get_driver()
            try:
                total_estimated = len(all_tasks) * limit_in
                for i, (city, kw) in enumerate(all_tasks):
                    if i < st.session_state.task_index: continue
                    if not st.session_state.running: break
                    base_progress = i * limit_in
                    status_ui.markdown(f"**Scanning:** `{kw}` in `{city}`... ({i+1}/{len(all_tasks)})")
                    gl = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                    driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl}")
                    time.sleep(4)
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane); time.sleep(1)
                    except: pass
                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    processed = 0
                    for item in items:
                        if processed >= limit_in or not st.session_state.running: break
                        try:
                            driver.execute_script("arguments[0].click();", item); time.sleep(2)
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            phone = "N/A"
                            try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                            except: pass
                            if any(res['Name'] == name and res['Phone'] == phone for res in st.session_state.results_list): continue
                            
                            st.session_state.progress = min(int(((base_progress + processed + 1) / total_estimated) * 100), 100)
                            prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)
                            
                            raw_web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href") if driver.find_elements(By.CSS_SELECTOR, 'a[data-item-id="authority"]') else "N/A"
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_nosite and raw_web != "N/A": continue
                            
                            wa_link = "N/A"
                            cp = re.sub(r'\D', '', phone)
                            if any(cp.startswith(x) for x in ['2126','2127','06','07']) and not (cp.startswith('2125') or cp.startswith('05')):
                                wa_link = f'<a href="https://wa.me/{cp}" target="_blank" class="wa-link"><i class="fab fa-whatsapp"></i> Chat Now</a>'
                            
                            email_found = fetch_email_deep(driver, raw_web) if w_email and raw_web != "N/A" else "N/A"
                            row = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa_link, "Website":raw_web if w_web else "N/A", "Email":email_found}
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, whatsapp)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.current_sid, kw, city, country_in, name, phone, row["Website"], email_found, wa_link))
                                if me != 'admin': conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (me,))
                                conn.commit()
                            st.session_state.results_list.append(row)
                            table_ui.write(pd.DataFrame(st.session_state.results_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                            processed += 1
                        except Exception: continue
                    st.session_state.task_index += 1
                if st.session_state.task_index >= len(all_tasks) and st.session_state.running:
                    st.success("🏁 Extraction Finished!"); st.session_state.running = False
            finally:
                driver.quit()

# ==============================================================================
# 9. ARCHIVE TAB (FROM APP 15 - UNTOUCHED)
# ==============================================================================
with tab_archive:
    st.subheader("Persistent History")
    search_f = st.text_input("Filter History", placeholder="🔍 Search...", key="archive_search")
    with sqlite3.connect(DB_NAME) as conn:
        df_s = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{search_f}%",))
    if not df_s.empty:
        for _, sess in df_s.iterrows():
            with st.expander(f"📦 {sess['date']} | {sess['query']}"):
                with sqlite3.connect(DB_NAME) as conn:
                    df_l = pd.read_sql(f"SELECT * FROM leads WHERE session_id={sess['id']}", conn)
                if not df_l.empty:
                    st.write(df_l.drop(columns=['id', 'session_id']).to_html(escape=False, index=False), unsafe_allow_html=True)
                    csv_arch = convert_df(df_l)
                    st.download_button(label="⬇️ Download Archive CSV", data=csv_arch, file_name=f"archive_{sess['id']}.csv", mime="text/csv", key=f"btn_arch_{sess['id']}")
                else: st.warning("Empty results.")

# ==============================================================================
# 10. MARKETING TAB (FROM APP 15 - UNTOUCHED)
# ==============================================================================
with tab_tools:
    st.subheader("🤖 Marketing Automation")
    st.info("Marketing tools coming soon in the next update!")

st.markdown(f'<div style="text-align:center;color:#444;padding:30px;font-size:12px;">Designed by Chatir Elite Pro - Architect Edition V64</div>', unsafe_allow_html=True)

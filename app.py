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
# 1. CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'paused' not in st.session_state: st.session_state.paused = False
if 'task_index' not in st.session_state: st.session_state.task_index = 0
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status_msg' not in st.session_state: st.session_state.status_msg = "READY"
if 'current_sid' not in st.session_state: st.session_state.current_sid = None

# ==============================================================================
# 2. CLEAN CSS SYSTEM (NO COMMENTS - DIRECT INJECTION)
# ==============================================================================
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', sans-serif !important;
    background-color: #0e1117;
}

.centered-logo { text-align: center; padding: 20px 0 40px 0; }
.logo-img { width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.3)); }

div[data-testid="stHorizontalBlock"]:has(button) { gap: 5px !important; }
div[data-testid="stHorizontalBlock"]:has(button) div[data-testid="column"] { padding: 0 !important; margin: 0 !important; }

.stButton > button {
    width: 100% !important;
    height: 50px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    border: none !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    transition: all 0.3s ease-in-out;
    border-radius: 8px !important;
    color: white !important;
}

div[data-testid="column"]:nth-of-type(1) .stButton > button {
    background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important;
    box-shadow: 0 4px 15px rgba(255,69,0,0.3) !important;
}

div[data-testid="column"]:nth-of-type(2) .stButton > button {
    background-color: #1F2937 !important;
    border: 1px solid #374151 !important;
    color: #E5E7EB !important;
}

div[data-testid="column"]:nth-of-type(3) .stButton > button {
    background: linear-gradient(135deg, #28a745 0%, #218838 100%) !important;
    color: white !important;
    box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3) !important;
}

div[data-testid="column"]:nth-of-type(4) .stButton > button {
    background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%) !important;
    color: white !important;
    box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4) !important;
}

.stButton > button:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed;
    filter: grayscale(1);
    box-shadow: none !important;
}

.prog-container {
    width: 100%;
    background: #111827;
    border-radius: 50px;
    padding: 4px;
    border: 1px solid #374151;
    margin: 25px 0;
}

.prog-bar-fill {
    height: 16px;
    background: repeating-linear-gradient(45deg, #FF8C00, #FF8C00 12px, #FF4500 12px, #FF4500 24px);
    border-radius: 20px;
    transition: width 0.3s ease-in-out;
    animation: stripes 1s linear infinite;
}

@keyframes stripes { 0% {background-position: 0 0;} 100% {background-position: 48px 48px;} }

[data-testid="stMetricValue"] { color: #FF8C00 !important; font-weight: 800; }
section[data-testid="stSidebar"] { background-color: #161922 !important; border-right: 1px solid #31333F; }

.wa-link {
    color: #25D366 !important;
    text-decoration: none !important;
    font-weight: bold;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}
.wa-link i { font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. DATABASE
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
except: st.error("config.yaml missing"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass
    if st.session_state["authentication_status"] is not True:
        st.warning("🔒 Restricted Access"); st.stop()

# ==============================================================================
# 5. SIDEBAR
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
# 6. HEADER
# ==============================================================================
if os.path.exists("chatscrape.png"):
    with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
    st.markdown(f'<div class="centered-logo"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)

# ==============================================================================
# 7. INPUTS
# ==============================================================================
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1.5])
    kw_in = c1.text_input("Keywords", placeholder="e.g. hotel, cafe")
    city_in = c2.text_input("Cities", placeholder="e.g. Agadir, Casa")
    country_in = c3.selectbox("Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"])
    limit_in = c4.number_input("Limit/City", 1, 1000, 20)

    st.divider()
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1, 1.5])
    w_phone = f1.checkbox("Phone Only", True)
    w_web = f2.checkbox("Website", False)
    w_email = f3.checkbox("Deep Email", False)
    w_nosite = f4.checkbox("No Site Only", False)
    depth_in = f5.slider("Scroll Depth", 1, 100, 10)

    st.write("")
    
    # 4 BUTTONS ROW
    b_start, b_pause, b_cont, b_stop = st.columns(4) 
    
    with b_start:
        if st.button("Start Search", disabled=st.session_state.running):
            if kw_in and city_in:
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
# 8. ENGINE
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
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[0])
        return "N/A"

def convert_df(df):
    return df.to_csv(index=False).encode('utf-8')

tab_live, tab_archive, tab_tools = st.tabs(["⚡ Live Data", "📜 Archives", "🤖 Marketing"])

with tab_live:
    prog_spot = st.empty()
    status_ui = st.empty()
    table_ui = st.empty()
    download_btn_spot = st.empty()
    
    prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)

    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list)
        # 🔥 RESTORE HTML RENDER FOR WHATSAPP ICON
        table_ui.markdown(df_live.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        csv = convert_df(df_live)
        download_btn_spot.download_button(
            label="⬇️ Download CSV",
            data=csv,
            file_name="extraction_results.csv",
            mime="text/csv",
            key='live_dl'
        )

    if st.session_state.running:
        if st.session_state.paused:
            status_ui.warning("⏸️ SEARCH PAUSED. Click 'Continue' to resume.")
        else:
            driver = get_driver()
            try:
                kws = [k.strip() for k in kw_in.split(',')]
                cts = [c.strip() for c in city_in.split(',')]
                all_tasks = [(c, k) for c in cts for k in kws]
                total_estimated = len(all_tasks) * limit_in
                
                # Check if we have tasks
                if len(all_tasks) > 0:
                    for i, (city, kw) in enumerate(all_tasks):
                        if i < st.session_state.task_index: continue
                        
                        if not st.session_state.running: break
                        if st.session_state.paused: 
                            status_ui.warning("⏸️ Paused...")
                            break 
                        
                        base_progress = i * limit_in
                        status_ui.markdown(f"**Scanning:** `{kw}` in `{city}`... ({i+1}/{len(all_tasks)})")
                        
                        gl = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                        driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl}")
                        time.sleep(4)

                        try:
                            pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            for _ in range(depth_in):
                                if not st.session_state.running or st.session_state.paused: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane); time.sleep(1)
                        except: pass

                        if not st.session_state.paused and st.session_state.running:
                            items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                            processed = 0
                            for item in items:
                                if processed >= limit_in or not st.session_state.running or st.session_state.paused: break
                                try:
                                    driver.execute_script("arguments[0].click();", item); time.sleep(2)
                                    
                                    current_real = base_progress + processed + 1
                                    st.session_state.progress = min(int((current_real / total_estimated) * 100), 100)
                                    prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True)
                                    
                                    name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                    phone = "N/A"
                                    try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                                    except: pass
                                    
                                    raw_web = "N/A"
                                    try: raw_web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                    except: pass
                                    display_web = raw_web if w_web else "N/A"

                                    if w_phone and (phone == "N/A" or not phone): continue
                                    if w_nosite and raw_web != "N/A": continue

                                    wa_link = "N/A"
                                    cp = re.sub(r'\D', '', phone)
                                    if any(cp.startswith(x) for x in ['2126','2127','06','07']) and not (cp.startswith('2125') or cp.startswith('05')):
                                        wa_link = f'<a href="https://wa.me/{cp}" target="_blank" class="wa-link"><i class="fab fa-whatsapp"></i> Chat Now</a>'
                                    
                                    email_found = "N/A"
                                    if w_email and raw_web != "N/A":
                                        email_found = fetch_email_deep(driver, raw_web)

                                    row = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa_link, "Website":display_web, "Email":email_found}
                                    
                                    with sqlite3.connect(DB_NAME) as conn:
                                        conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, whatsapp)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.current_sid, kw, city, country_in, name, phone, display_web, email_found, wa_link))
                                        if me != 'admin': conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (me,))
                                        conn.commit()
                                    
                                    st.session_state.results_list.append(row)
                                    
                                    df_live = pd.DataFrame(st.session_state.results_list)
                                    table_ui.markdown(df_live.to_html(escape=False, index=False), unsafe_allow_html=True)
                                    
                                    csv = convert_df(df_live)
                                    download_btn_spot.download_button(
                                        label="⬇️ Download CSV",
                                        data=csv,
                                        file_name="extraction_results.csv",
                                        mime="text/csv",
                                        key=f'live_dl_{len(st.session_state.results_list)}'
                                    )
                                    processed += 1
                                except: continue
                        
                        if not st.session_state.paused and st.session_state.running:
                            st.session_state.task_index += 1

                    # 🔥 FINAL CHECK: Only finish if we actually completed all tasks
                    if not st.session_state.paused and st.session_state.running and st.session_state.task_index >= len(all_tasks):
                        st.success("🏁 Extraction Finished!")
                        st.session_state.running = False
                else:
                    st.warning("⚠️ No tasks to process.")
                    st.session_state.running = False
            finally:
                driver.quit()

# ==============================================================================
# 9. ARCHIVE TAB
# ==============================================================================
with tab_archive:
    st.subheader("Persistent History")
    search_f = st.text_input("Filter History", placeholder="🔍 Search e.g. 'lawyer' or 'tiznit'...")
    
    with sqlite3.connect(DB_NAME) as conn:
        df_s = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{search_f}%",))
    
    if not df_s.empty:
        for _, sess in df_s.iterrows():
            with st.expander(f"📦 {sess['date']} | {sess['query']}"):
                with sqlite3.connect(DB_NAME) as conn:
                    df_l = pd.read_sql(f"SELECT * FROM leads WHERE session_id={sess['id']}", conn)
                if not df_l.empty:
                    # Archives use HTML render for icons
                    st.write(df_l.drop(columns=['id', 'session_id']).to_html(escape=False, index=False), unsafe_allow_html=True)
                    
                    csv_arch = convert_df(df_l)
                    st.download_button(
                        label="⬇️ Download Archive CSV",
                        data=csv_arch,
                        file_name=f"archive_{sess['id']}.csv",
                        mime="text/csv",
                        key=f"btn_arch_{sess['id']}"
                    )
                else: st.warning("Empty results.")

st.markdown('<div style="text-align:center;color:#666;padding:30px;">Designed by Chatir Elite Pro - Architect Edition V46</div>', unsafe_allow_html=True)

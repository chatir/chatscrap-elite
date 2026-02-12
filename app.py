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
# 1. ELITE SYSTEM CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

# ==============================================================================
# 2. DATABASE (NUCLEAR V9 - CLEAN & LINKED)
# ==============================================================================
DB_NAME = "chatscrap_elite_pro_v9.db"
OLD_DB = "scraper_pro_final.db"

def init_db_v9():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, 
            keyword TEXT, city TEXT, country TEXT, name TEXT, phone TEXT, 
            website TEXT, email TEXT, address TEXT, whatsapp TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_credits 
            (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
        conn.commit()

    # محاولة نقل المستخدمين (ياسين ومريم) أوتوماتيكياً
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
# 3. UI STYLING (THE BEAST LOOK)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;700&display=swap');
    html, body, .stApp {{ font-family: 'Segoe UI', sans-serif !important; background-color: #0e1117; }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; }}
    
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 12px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 40px rgba(0,0,0,0.4);
    }}
    @media (max-width: 768px) {{ .mobile-popup {{ display: block; }} }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ 
        height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; transition: width 0.4s ease; animation: stripes 1s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 50px 50px;}} }}
    div.stButton > button[kind="primary"] {{ 
        background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; 
        border: none; font-weight: 700; border-radius: 8px; height: 3.5em; width: 100%;
    }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. SECURITY & AUTH
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
    st.warning("🔒 Restricted Access. Please Login."); st.stop()

# ==============================================================================
# 5. CORE FUNCTIONS
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

def save_lead_atomic(session_id, d):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, d['Keyword'], d['City'], d['Country'], d['Name'], d['Phone'], 
                 d.get('Website','N/A'), d.get('Email','N/A'), d.get('Address','N/A'), d.get('WhatsApp','N/A')))
            conn.commit()
    except Exception as e: print(f"Save Fail: {e}")

# ==============================================================================
# 6. SIDEBAR
# ==============================================================================
with st.sidebar:
    st.title("👤 User Profile")
    curr_user = st.session_state["username"]
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance FROM user_credits WHERE username=?", (curr_user,)).fetchone()
        user_bal = res[0] if res else 100
    
    st.metric("Credits Available", "Unlimited" if curr_user == 'admin' else user_bal)
    
    if curr_user == 'admin':
        with st.expander("🛠 Admin Control"):
            u_df = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(u_df, hide_index=True)
            target = st.selectbox("Select User", u_df['username'])
            if st.button("💰 Add 100 Credits"):
                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET balance = balance + 100 WHERE username=?", (target,))
                st.rerun()

    st.divider()
    if st.button("🚪 Sign Out"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 7. MAIN HEADER & STATUS
# ==============================================================================
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    p_holder = st.empty()
    m_holder = st.empty()

def update_ui(prog, txt):
    st.session_state.progress_val = prog
    st.session_state.status_txt = txt
    p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{txt} {prog}%</div>""", unsafe_allow_html=True)
    if st.session_state.running:
        m_holder.markdown(f"""<div class="mobile-popup"><span style="color:{orange_c};font-weight:bold;">🚀 {txt}</span><br><div style="background:#333;height:6px;border-radius:3px;margin-top:5px;"><div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div></div><small>{prog}%</small></div>""", unsafe_allow_html=True)

if not st.session_state.running: update_ui(0, "SYSTEM READY")

# ==============================================================================
# 8. INPUT AREA
# ==============================================================================
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kw_in = c1.text_input("🔍 Keywords (Multi)", placeholder="cafe, law, etc.")
    city_in = c2.text_input("🌍 Cities (Multi)", placeholder="Agadir, Casablanca")
    country_in = c3.selectbox("🏴 Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"])
    limit_in = c4.number_input("Limit/City", 1, 1000, 20)

    st.divider()
    f1, f2, f3, f4 = st.columns(4)
    w_phone = f1.checkbox("✅ Must have Phone", True)
    w_web = f2.checkbox("🌐 Must have Website", False)
    w_email = f3.checkbox("📧 Deep Email Scan", False)
    depth_in = f4.slider("Scroll Depth", 1, 100, 10)

    st.write("")
    b1, b2 = st.columns(2)
    if b1.button("🚀 START EXTRACTION", type="primary"):
        if kw_in and city_in: st.session_state.running = True; st.session_state.results_df = []; st.rerun()
    if b2.button("🛑 STOP ENGINE", type="secondary"):
        st.session_state.running = False; st.rerun()

# ==============================================================================
# 9. TABS: RESULTS & ARCHIVES
# ==============================================================================
t1, t2, t3 = st.tabs(["⚡ LIVE RESULTS", "📜 SEARCH HISTORY", "🤖 MARKETING KIT"])

with t1:
    spot = st.empty()
    cols = ["Keyword", "City", "Name", "Phone", "WhatsApp", "Website", "Address"]
    
    if st.session_state.results_df:
        df_live = pd.DataFrame(st.session_state.results_df)
        st.download_button("📥 Download CSV", df_live.to_csv(index=False).encode('utf-8-sig'), "leads.csv", use_container_width=True)
        spot.dataframe(df_live, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat")})

    if st.session_state.running:
        driver = get_driver()
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
            s_id = cur.lastrowid
            conn.commit()

        try:
            keywords = [k.strip() for k in kw_in.split(',')]
            cities = [c.strip() for c in city_in.split(',')]
            total_ops = len(keywords) * len(cities)
            curr_op = 0

            for city in cities:
                for kw in keywords:
                    if not st.session_state.running: break
                    curr_op += 1
                    update_ui(int(((curr_op-1)/total_ops)*100), f"SCANNING: {kw} in {city}")
                    
                    gl = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                    driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl}")
                    time.sleep(5)
                    
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                            time.sleep(1.5)
                    except: pass

                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    valid_cnt = 0
                    for item in items:
                        if valid_cnt >= limit_in or not st.session_state.running: break
                        try:
                            driver.execute_script("arguments[0].click();", item); time.sleep(2)
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

                            # 🔥 STRICT FILTERS
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_web and (web == "N/A" or not web): continue

                            # WhatsApp
                            wa = "N/A"
                            clean_p = re.sub(r'\D', '', phone)
                            if any(clean_p.startswith(x) for x in ['2126','2127','06','07']):
                                wa = f"https://wa.me/{clean_p}"

                            data = {"Keyword":kw, "City":city, "Country":country_in, "Name":name, "Phone":phone, "Website":web, "WhatsApp":wa, "Address":addr}
                            
                            # 🔥 ATOMIC SAVE
                            save_lead_atomic(s_id, data)
                            if curr_user != 'admin':
                                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (curr_user,))
                            
                            st.session_state.results_df.append(data)
                            spot.dataframe(pd.DataFrame(st.session_state.results_df), use_container_width=True)
                            valid_cnt += 1
                        except: continue
            update_ui(100, "EXTRACTION COMPLETED ✅")
        finally:
            driver.quit()
            st.session_state.running = False; st.rerun()

with t2:
    st.subheader("📜 Archives")
    search_q = st.text_input("🔍 Filter History (City or Keyword)", "")
    with sqlite3.connect(DB_NAME) as conn:
        sessions = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 20", conn, params=(f"%{search_q}%",))
    
    if not sessions.empty:
        for idx, row in sessions.iterrows():
            with st.expander(f"📦 {row['date']} | {row['query']}"):
                leads = pd.read_sql(f"SELECT * FROM leads WHERE session_id = {row['id']}", sqlite3.connect(DB_NAME))
                if not leads.empty:
                    df_arch = leads.drop(columns=['id', 'session_id'])
                    st.dataframe(df_arch, use_container_width=True)
                    st.download_button("📥 Export CSV", df_arch.to_csv(index=False).encode('utf-8-sig'), f"archive_{row['id']}.csv")
                else:
                    st.warning("Empty result (Interrupted or filtered).")
    else:
        st.info("No matching history found.")

with t3:
    st.subheader("🤖 Marketing Kit")
    if st.button("Generate Script"):
        st.code(f"Hi! Found your business in {city_in}...")

st.markdown('<div style="text-align:center;color:#666;padding:20px;">Designed by Chatir Elite Pro v10 | Full Beast</div>', unsafe_allow_html=True)

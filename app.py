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
# 1. SYSTEM SETUP & STATE
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro Max", layout="wide", page_icon="💎")

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

# ==============================================================================
# 2. DATABASE MANAGEMENT (V9 NUCLEAR SYSTEM)
# ==============================================================================
DB_NAME = "chatscrap_elite_pro_v9.db"
OLD_DB = "scraper_pro_final.db"

def init_db_v11():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Sessions Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
        # Leads Table (The Linked System)
        cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, 
            keyword TEXT, city TEXT, country TEXT, name TEXT, phone TEXT, 
            website TEXT, email TEXT, address TEXT, whatsapp TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id))''')
        # Users Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_credits 
            (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
        conn.commit()

    # Migration from OLD DB if exists
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

init_db_v11()

# --- DB HELPERS ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()
        return True

def manage_user_v11(action, username, amount=0):
    if action == "add":
        run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))
    elif action == "delete":
        run_query("DELETE FROM user_credits WHERE username=?", (username,))
    elif action == "toggle":
        res = run_query("SELECT status FROM user_credits WHERE username=?", (username,), True)
        if res:
            new_s = 'suspended' if res[0][0] == 'active' else 'active'
            run_query("UPDATE user_credits SET status=? WHERE username=?", (new_s, username))

# ==============================================================================
# 3. UI STYLING (THE FULL DESIGN)
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
# 4. AUTHENTICATION & SECURITY
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except Exception as e:
    st.error(f"❌ config.yaml is missing! Error: {e}"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is not True:
    st.warning("🔒 Restricted Access. Please Login."); st.stop()

# ==============================================================================
# 5. SCRAPER ENGINE (THE CORE BEAST)
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    # Server Detection
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium: opts.binary_location = chromium
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        try:
            driver.set_page_load_timeout(10); driver.get(url); time.sleep(1.5)
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
            valid = [e for e in emails if not e.endswith(('.png','.jpg','.gif','.webp'))]
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return valid[0] if valid else "N/A"
        except: driver.close(); driver.switch_to.window(driver.window_handles[0]); return "N/A"
    except: return "N/A"

# ==============================================================================
# 6. SIDEBAR & USER CONTROL
# ==============================================================================
with st.sidebar:
    st.title("👤 User Control")
    curr_user = st.session_state["username"]
    
    # Credits Retrieval
    user_data = run_query("SELECT balance, status FROM user_credits WHERE username=?", (curr_user,), True)
    if not user_data:
        run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (curr_user,))
        bal, sts = 100, 'active'
    else:
        bal, sts = user_data[0]
    
    if sts == 'suspended' and curr_user != 'admin': st.error("🚫 ACCOUNT SUSPENDED"); st.stop()
    
    st.metric("Your Balance", "💎 Unlimited" if curr_user == 'admin' else f"💎 {bal}")
    
    # 🔥 FULL ADMIN PANEL RESTORED
    if curr_user == 'admin':
        with st.expander("🛠️ SYSTEM ADMIN"):
            all_u = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(all_u, hide_index=True)
            
            st.divider()
            target = st.selectbox("Select User", [u for u in all_u['username'] if u != 'admin'])
            c1, c2, c3 = st.columns(3)
            if c1.button("💰 +100"): manage_user_v11("add", target, 100); st.rerun()
            if c2.button("🚫 Status"): manage_user_v11("toggle", target); st.rerun()
            if c3.button("🗑️ Del"): manage_user_v11("delete", target); st.rerun()
            
            st.divider()
            st.write("Add New User:")
            nu = st.text_input("New Username")
            np = st.text_input("New Password", type="password")
            if st.button("Create User"):
                try: hp = stauth.Hasher.hash(np)
                except: hp = stauth.Hasher([np]).generate()[0]
                config['credentials']['usernames'][nu] = {'name': nu, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (nu,))
                st.success(f"User {nu} Created!"); st.rerun()

    st.divider()
    if st.button("🚪 Logout"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 7. MAIN INTERFACE
# ==============================================================================
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    p_holder = st.empty()
    m_holder = st.empty()

def update_ui_v11(prog, txt):
    st.session_state.progress_val = prog
    st.session_state.status_txt = txt
    p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{txt} {prog}%</div>""", unsafe_allow_html=True)
    if st.session_state.running:
        m_holder.markdown(f"""<div class="mobile-popup"><span style="color:{orange_c};font-weight:bold;">🚀 {txt}</span><br><div style="background:#333;height:6px;border-radius:3px;margin-top:5px;"><div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div></div><small>{prog}%</small></div>""", unsafe_allow_html=True)

if not st.session_state.running: update_ui_v11(0, "SYSTEM READY")

# --- CONTROL PANEL ---
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kw_in = c1.text_input("🔍 Keywords (comma separated)", placeholder="cafe, snak")
    city_in = c2.text_input("🌍 Cities (comma separated)", placeholder="Agadir, Casa")
    country_in = c3.selectbox("🏴 Country", ["Morocco", "France", "USA", "Spain", "Germany", "UAE", "UK"])
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
# 8. SCRAPING ENGINE & LIVE RESULTS
# ==============================================================================
t1, t2, t3 = st.tabs(["⚡ LIVE RESULTS", "📜 SEARCH HISTORY", "🤖 MARKETING KIT"])

with t1:
    spot = st.empty()
    if st.session_state.results_df:
        live_df = pd.DataFrame(st.session_state.results_df)
        st.download_button("📥 Export CSV", live_df.to_csv(index=False).encode('utf-8-sig'), "leads.csv", use_container_width=True)
        spot.dataframe(live_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat")})

    if st.session_state.running:
        driver = get_driver()
        # Session Creation
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in} | {country_in}", time.strftime("%Y-%m-%d %H:%M")))
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
                    update_ui_v11(int(((curr_op-1)/total_ops)*100), f"SCANNING: {kw} in {city}")
                    
                    gl_map = {"Morocco": "ma", "France": "fr", "USA": "us", "Spain": "es", "Germany": "de", "UAE": "ae", "UK": "gb"}
                    gl_code = gl_map.get(country_in, "ma")
                    
                    url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}+{quote(country_in)}?hl=en&gl={gl_code}"
                    driver.get(url); time.sleep(5)
                    
                    # Accept cookies if any
                    try: driver.find_element(By.XPATH, "//button[contains(., 'Accept all')]").click(); time.sleep(1)
                    except: pass

                    # Scroll
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                            time.sleep(1.5)
                    except: pass

                    # Scrape items
                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    seen = set(); valid_cnt = 0
                    for item in items:
                        if valid_cnt >= limit_in or not st.session_state.running: break
                        href = item.get_attribute("href")
                        if href in seen: continue
                        seen.add(href)
                        
                        try:
                            driver.execute_script("arguments[0].click();", item); time.sleep(2.2)
                            name = "N/A"; phone = "N/A"; web = "N/A"; addr = "N/A"
                            try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            except: pass
                            try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone: ", "")
                            except: pass
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe').text
                            except: pass

                            # 🔥 STRICT FILTERS
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_web and (web == "N/A" or not web): continue

                            # WhatsApp Check (Smart Filter 05)
                            wa = "N/A"
                            clean_p = re.sub(r'\D', '', phone)
                            is_mobile = any(clean_p.startswith(x) for x in ['2126','2127','06','07'])
                            is_fixe = clean_p.startswith('2125') or (clean_p.startswith('05') and len(clean_p) <= 10)
                            if is_mobile and not is_fixe:
                                wa = f"https://wa.me/{clean_p}"

                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email_deep(driver, web)

                            row = {"Keyword":kw, "City":city, "Country":country_in, "Name":name, "Phone":phone, "Website":web, "WhatsApp":wa, "Email":email, "Address":addr}
                            
                            # 🔥 ATOMIC DB SAVE
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (s_id, kw, city, country_in, name, phone, web, email, addr, wa))
                            
                            if curr_user != 'admin':
                                sqlite3.connect(DB_NAME).execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (curr_user,))
                            
                            st.session_state.results_df.append(row)
                            spot.dataframe(pd.DataFrame(st.session_state.results_df), use_container_width=True)
                            valid_cnt += 1
                        except: continue
            update_ui_v11(100, "EXTRACTION COMPLETED ✅")
        finally:
            driver.quit()
            st.session_state.running = False; st.rerun()

# ==============================================================================
# 9. ARCHIVES (PRO SEARCH SYSTEM)
# ==============================================================================
with t2:
    st.subheader("📜 Search Archives & Exports")
    q_search = st.text_input("🔍 Filter History (City or Keyword)", placeholder="Search Agadir...")
    
    with sqlite3.connect(DB_NAME) as conn:
        sessions = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{q_search}%",))
    
    if not sessions.empty:
        for _, s in sessions.iterrows():
            with st.expander(f"📦 {s['date']} | {s['query']}"):
                leads = pd.read_sql(f"SELECT * FROM leads WHERE session_id = {s['id']}", sqlite3.connect(DB_NAME))
                if not leads.empty:
                    df_final = leads.drop(columns=['id', 'session_id'])
                    st.dataframe(df_final, use_container_width=True)
                    st.download_button("📥 Export CSV", df_final.to_csv(index=False).encode('utf-8-sig'), f"archive_{s['id']}.csv")
                else:
                    st.warning("Empty Result (Stopped or Filtered).")
    else: st.info("No archives found.")

# ==============================================================================
# 10. MARKETING KIT
# ==============================================================================
with t3:
    st.subheader("🤖 Marketing Script Generator")
    if st.button("Generate Cold Message"):
        st.code(f"Hi! Found your business in {city_in}. I noticed your business...")

st.markdown('<div style="text-align:center;color:#666;padding:20px;">Designed by Chatir Elite Pro v11 | FULL BEAST</div>', unsafe_allow_html=True)

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
# 1. GLOBAL SYSTEM & STATE CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro Supreme", layout="wide", page_icon="💎")

# تهيئة المتغيرات لضمان عدم ضياع البحث عند التفاعل مع الواجهة
if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status_msg' not in st.session_state: st.session_state.status_msg = "SYSTEM READY"
if 'current_sid' not in st.session_state: st.session_state.current_sid = None

# ==============================================================================
# 2. DESIGN SYSTEM (PRO CSS)
# ==============================================================================
main_orange = "#FF8C00"
grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    /* الأساسيات */
    html, body, [data-testid="stAppViewContainer"] {{
        font-family: 'Inter', sans-serif !important;
        background-color: #0e1117;
        color: #FFFFFF;
    }}

    /* توحيد الأزرار */
    .stButton > button {{
        width: 100% !important;
        height: 48px !important;
        border-radius: 10px !important;
        border: none !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
    }}
    
    div.stButton > button[kind="primary"] {{
        background: {grad} !important;
        color: white !important;
        box-shadow: 0 4px 14px 0 rgba(255, 140, 0, 0.39) !important;
    }}
    
    div.stButton > button[kind="secondary"] {{
        background-color: #262730 !important;
        color: #fafafa !important;
    }}

    /* تنسيق الصور واللوقو */
    .logo-container {{ text-align: center; padding: 20px; }}
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)); }}

    /* البطاقات والجداول */
    [data-testid="stMetricValue"] {{ color: {main_orange} !important; font-weight: 800; }}
    .stDataFrame {{ border: 1px solid #31333F; border-radius: 10px; overflow: hidden; }}
    
    /* شريط التقدم */
    .stProgress > div > div > div > div {{ background: {grad} !important; }}
    
    /* شاشة الموبايل المنبثقة */
    .mobile-status {{
        display: none; position: fixed; top: 10px; right: 10px; left: 10px;
        background: rgba(14, 17, 23, 0.9); border: 1px solid {main_orange};
        padding: 15px; border-radius: 15px; z-index: 9999; text-align: center;
    }}
    @media (max-width: 768px) {{ .mobile-status {{ display: block; }} }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. DATABASE ENGINE (NUCLEAR PERSISTENCE)
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

def get_user(username):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance, status FROM user_credits WHERE username=?", (username,)).fetchone()
        if res: return res
        conn.execute("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,))
        conn.commit()
        return (100, 'active')

def manage_credits(username, amount):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))
        conn.commit()

def toggle_user_status(username):
    with sqlite3.connect(DB_NAME) as conn:
        curr = conn.execute("SELECT status FROM user_credits WHERE username=?", (username,)).fetchone()[0]
        new_s = 'suspended' if curr == 'active' else 'active'
        conn.execute("UPDATE user_credits SET status=? WHERE username=?", (new_s, username))
        conn.commit()

# ==============================================================================
# 4. AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("❌ config.yaml is missing"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass
    if st.session_state["authentication_status"] is not True:
        st.warning("🔒 Login Required"); st.stop()

# ==============================================================================
# 5. SIDEBAR & ADMIN PANEL (FULL CONTROL)
# ==============================================================================
with st.sidebar:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    st.title("👤 Account Settings")
    me = st.session_state["username"]
    my_bal, my_sts = get_user(me)
    
    if my_sts == 'suspended' and me != 'admin':
        st.error("🚫 ACCOUNT SUSPENDED"); st.stop()
        
    st.metric("Your Balance", "💎 Unlimited" if me == 'admin' else f"💎 {my_bal}")
    
    if me == 'admin':
        with st.expander("🛠️ ADMIN CONTROL PANEL"):
            users_df = pd.read_sql("SELECT * FROM user_credits", sqlite3.connect(DB_NAME))
            st.dataframe(users_df, hide_index=True)
            
            st.write("Manage Target User:")
            target = st.selectbox("Select User", users_df['username'])
            
            col_a, col_b, col_c = st.columns(3)
            if col_a.button("💰 +100"): manage_credits(target, 100); st.rerun()
            if col_b.button("🚫 Toggle"): toggle_user_status(target); st.rerun()
            if col_c.button("🗑️ Del"):
                with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM user_credits WHERE username=?", (target,))
                st.rerun()
            
            st.divider()
            st.write("Add New Member:")
            new_u = st.text_input("Username", key="nu")
            new_p = st.text_input("Password", type="password", key="np")
            if st.button("Create User Account"):
                try: hp = stauth.Hasher.hash(new_p)
                except: hp = stauth.Hasher([new_p]).generate()[0]
                config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                get_user(new_u)
                st.success("User created!"); st.rerun()

    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 6. SCRAPER CORE (THE BEAST)
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    # التوافق مع السيرفر
    path = shutil.which("chromium") or shutil.which("chromium-browser")
    if path: opts.binary_location = path
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email(driver, url):
    if not url or "google" in url: return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        driver.set_page_load_timeout(8); driver.get(url); time.sleep(1)
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return list(set(emails))[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==============================================================================
# 7. MAIN INTERFACE & CONTROL
# ==============================================================================
st.title("🕷️ ChatScrap Elite Pro Supreme")

with st.container():
    col1, col2, col3, col4 = st.columns([3, 3, 2, 1])
    keywords_raw = col1.text_input("🔍 Keywords", placeholder="cafe, hotel, snak")
    cities_raw = col2.text_input("🌍 Cities", placeholder="Agadir, Casablanca")
    country_in = col3.selectbox("🏴 Target Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"])
    limit_in = col4.number_input("Limit/City", 1, 1000, 20)

    st.divider()
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1.5])
    w_phone = f1.checkbox("✅ Must have Phone", True)
    w_web = f2.checkbox("🌐 Must have Website", False)
    w_email = f3.checkbox("📧 Deep Email Scan", False)
    scroll_depth = f4.slider("Scroll Depth (More = More results)", 1, 100, 10)

    st.write("")
    btn_start, btn_stop = st.columns(2)
    
    if btn_start.button("🚀 START EXTRACTION", type="primary"):
        if keywords_raw and cities_raw:
            st.session_state.running = True
            st.session_state.results_list = []
            st.session_state.progress = 0
            # إنشاء جلسة جديدة وحفظ الـ ID فوراً
            with sqlite3.connect(DB_NAME) as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{keywords_raw} | {cities_raw}", time.strftime("%Y-%m-%d %H:%M")))
                st.session_state.current_sid = cur.lastrowid
                conn.commit()
            st.rerun()

    if btn_stop.button("🛑 STOP ENGINE", type="secondary"):
        st.session_state.running = False
        st.rerun()

# ==============================================================================
# 8. TABS (LIVE / ARCHIVES / TOOLS)
# ==============================================================================
tab_live, tab_archive, tab_tools = st.tabs(["⚡ LIVE RESULTS", "📜 ARCHIVES & HISTORY", "🤖 MARKETING KIT"])

with tab_live:
    if st.session_state.running:
        st.markdown(f'<div class="mobile-status">🚀 Scanning: {st.session_state.status_msg} ({st.session_state.progress}%)</div>', unsafe_allow_html=True)
    
    prog_ui = st.progress(st.session_state.progress)
    status_ui = st.empty()
    table_ui = st.empty()
    
    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list)
        table_ui.dataframe(df_live, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat")})

    if st.session_state.running:
        driver = get_driver()
        try:
            kws = [k.strip() for k in keywords_raw.split(',')]
            cts = [c.strip() for c in cities_raw.split(',')]
            total = len(kws) * len(cts)
            count_op = 0

            for city in cts:
                for kw in kws:
                    if not st.session_state.running: break
                    count_op += 1
                    pct = int((count_op / total) * 100)
                    st.session_state.progress = pct
                    st.session_state.status_msg = f"{kw} in {city}"
                    prog_ui.progress(pct)
                    status_ui.markdown(f"**Current Scanning:** `{kw}` in `{city}`...")
                    
                    gl_code = {"Morocco":"ma", "France":"fr", "USA":"us"}.get(country_in, "ma")
                    driver.get(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl={gl_code}")
                    time.sleep(4)

                    # Deep Scroll
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(scroll_depth):
                            if not st.session_state.running: break
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", pane)
                            time.sleep(1.2)
                    except: pass

                    # Extract Results
                    items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    seen_urls = set(); processed_count = 0
                    
                    for item in items:
                        if processed_count >= limit_in or not st.session_state.running: break
                        url = item.get_attribute("href")
                        if url in seen_urls: continue
                        seen_urls.add(url)
                        
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

                            # 🔥 APPLY FILTERS BEFORE SAVING
                            if w_phone and (phone == "N/A" or not phone): continue
                            if w_web and (web == "N/A" or not web): continue

                            # WhatsApp Pro (No 05 Fixe)
                            wa = "N/A"
                            clean_p = re.sub(r'\D', '', phone)
                            if any(clean_p.startswith(x) for x in ['2126','2127','06','07']) and not (clean_p.startswith('2125') or clean_p.startswith('05')):
                                wa = f"https://wa.me/{clean_p}"

                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email(driver, web)

                            row_data = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa, "Website":web, "Email":email, "Address":addr}
                            
                            # 🔥 ATOMIC SAVE TO DB
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, address, whatsapp)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.current_sid, kw, city, country_in, name, phone, web, email, addr, wa))
                                if me != 'admin':
                                    conn.execute("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (me,))
                            
                            st.session_state.results_list.append(row_data)
                            table_ui.dataframe(pd.DataFrame(st.session_state.results_list), use_container_width=True)
                            processed_count += 1
                        except: continue
            st.success("🏁 Extraction Successfully Finished!")
        finally:
            driver.quit()
            st.session_state.running = False
            st.rerun()

# ==============================================================================
# 9. PERSISTENT ARCHIVE SYSTEM
# ==============================================================================
with tab_archive:
    st.subheader("📜 Persistent History")
    search_filter = st.text_input("🔍 Search Archives by Keyword/City", "")
    
    with sqlite3.connect(DB_NAME) as conn:
        sessions_df = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{search_filter}%",))
    
    if sessions_df.empty:
        st.info("No records found.")
    else:
        for _, sess in sessions_df.iterrows():
            with st.expander(f"📦 {sess['date']} | {sess['query']}"):
                with sqlite3.connect(DB_NAME) as conn:
                    leads_df = pd.read_sql(f"SELECT * FROM leads WHERE session_id={sess['id']}", conn)
                
                if not leads_df.empty:
                    final_arch = leads_df.drop(columns=['id', 'session_id'])
                    st.dataframe(final_arch, use_container_width=True)
                    st.download_button(f"📥 Download CSV #{sess['id']}", final_arch.to_csv(index=False).encode('utf-8-sig'), f"archive_{sess['id']}.csv")
                else:
                    st.warning("No leads found for this session (Possibly interrupted or filtered).")

with tab_tools:
    st.subheader("🤖 Smart Marketing Tools")
    if st.button("Generate Cold WhatsApp Message"):
        st.code(f"Hello! I found your business in {cities_raw}. I'm impressed with your work at...")

st.markdown('<div style="text-align:center;color:#666;padding:30px;">Designed by Chatir Elite Pro Supreme | THE BEAST V13</div>', unsafe_allow_html=True)

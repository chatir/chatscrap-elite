import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
import yaml
import gspread
from google.oauth2.service_account import Credentials
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. إعدادات "الوحش" (BEAST SETUP)
# ==============================================================================
st.set_page_config(page_title="ChatScrap The Beast", layout="wide", page_icon="🕷️")

# تهيئة المتغيرات (Persistence)
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'logs' not in st.session_state: st.session_state.logs = []

# ==============================================================================
# 2. الأمان والمصادقة (SECURITY)
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ Critical: 'config.yaml' مفقود!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False: st.error('❌ Login Failed'); st.stop()
elif st.session_state["authentication_status"] is None: st.warning('🔒 System Locked'); st.stop()

# ==============================================================================
# 3. قاعدة البيانات والربط (DB & SYNC)
# ==============================================================================
def run_query(query, params=(), is_select=False):
    try:
        with sqlite3.connect('scraper_beast.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except: return [] if is_select else False

def init_db():
    tables = [
        '''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''',
        '''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, keyword TEXT, city TEXT, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''',
        '''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')'''
    ]
    for t in tables: run_query(t)

init_db()

def get_user_data(u):
    r = run_query("SELECT balance, status FROM user_credits WHERE username=?", (u,), True)
    if r: return r[0]
    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (u,))
    return (100, 'active')

def deduct(u):
    if u != "admin": run_query("UPDATE user_credits SET balance=balance-1 WHERE username=?", (u,))

def add_credits(u, amt):
    run_query("UPDATE user_credits SET balance=balance+? WHERE username=?", (amt, u))

def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        st.toast("⚠️ Google Sheet Secrets Missing!", icon="❌"); return False
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(url)
        ws = sh.get_worksheet(0)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
        return True
    except Exception as e:
        st.error(f"Sync Error: {e}"); return False

# ==============================================================================
# 4. المحرك الهجين (HYBRID SCRAPER ENGINE)
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new") # استخدام النسخة الجديدة من Headless
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    # User Agent عادي لتفادي البلوك
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    """استخراج الإيميل بالدخول للموقع"""
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        try:
            driver.set_page_load_timeout(10)
            driver.get(url); time.sleep(1.5)
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
            valid = [e for e in emails if not e.endswith(('.png','.jpg','.gif'))]
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return valid[0] if valid else "N/A"
        except:
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return "N/A"
    except: return "N/A"

# ==============================================================================
# 5. التصميم المتحرك (ELITE UI & ANIMATION)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div {{ color: #FFFFFF !important; font-family: 'Segoe UI'; }}
    
    /* 🔥 MOBILE POPUP (يظهر فقط في الموبايل) */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 10px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }}
    @media (max-width: 768px) {{
        .mobile-popup {{ display: block; }}
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
    }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* 🔥 ANIMATED STRIPES (الحركة رجعات) */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ 
        height: 14px; 
        background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; transition: width 0.4s ease; animation: stripes 1s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 50px 50px;}} }}
    
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. منطق التطبيق (APP LOGIC)
# ==============================================================================
user = st.session_state["username"]
bal, status = get_user_data(user)
is_admin = user == "admin"

if status == 'suspended' and not is_admin: st.error("🚫 SUSPENDED"); st.stop()

# --- SIDEBAR (ADMIN & PROFILE) ---
with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{bal}**")
    
    st.divider()
    
    # Admin Panel (Protected in Expander)
    if is_admin:
        with st.expander("🛠️ ADMIN PANEL"):
            data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(data, columns=["User", "Bal", "Sts"]), hide_index=True)
            
            tgt = st.selectbox("Select User", [u[0] for u in data if u[0]!='admin'])
            if st.button("💰 +100"): 
                add_credits(tgt, 100); st.rerun()
            
            new_u = st.text_input("User")
            new_p = st.text_input("Pass", type="password")
            if st.button("Add"):
                try: hp = stauth.Hasher.hash(new_p)
                except: hp = stauth.Hasher([new_p]).generate()[0]
                config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, 5, 'active')", (new_u,))
                st.success("Added!"); st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- MAIN UI ---
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    # Placeholders for Dynamic Updates (No Rerun)
    p_holder = st.empty()
    m_holder = st.empty()

def update_ui(prog, txt):
    st.session_state.progress_val = prog
    st.session_state.status_txt = txt
    
    # Desktop
    p_holder.markdown(f"""
        <div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div>
        <div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{txt} {prog}%</div>
    """, unsafe_allow_html=True)
    
    # Mobile
    if st.session_state.running:
        m_holder.markdown(f"""
            <div class="mobile-popup">
                <span style="color:{orange_c};font-weight:bold;">🚀 {txt}</span><br>
                <div style="background:#333;height:6px;border-radius:3px;margin-top:5px;">
                    <div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div>
                </div>
                <small>{prog}%</small>
            </div>
        """, unsafe_allow_html=True)

# Restore UI State
if st.session_state.running:
    update_ui(st.session_state.progress_val, st.session_state.status_txt)
else:
    update_ui(0, "SYSTEM READY")

# --- INPUTS ---
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kws_in = c1.text_input("🔍 Keywords (Multi: cafe, hotel)", placeholder="Ex: cafe, restaurant")
    city_in = c2.text_input("🌍 Cities (Multi: Agadir, Casa)", placeholder="Ex: Agadir, Inezgane")
    limit_in = c3.number_input("Target/City", 1, 5000, 20)
    depth_in = c4.number_input("Scroll Depth", 1, 500, 10)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ **STRICT FILTERS (سيتم تجاهل النتائج التي لا تطابق):**")
        f = st.columns(4)
        w_phone = f[0].checkbox("Must have Phone", True)
        w_web = f[1].checkbox("Must have Website", True)
        w_email = f[2].checkbox("Extract Email (Deep)", False)
        w_nosite = f[3].checkbox("No Website Only", False)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        start = b1.button("START ENGINE", type="primary", use_container_width=True)
        stop = b2.button("STOP", type="secondary", use_container_width=True)

if stop:
    st.session_state.running = False; st.rerun()

# --- TABS ---
t1, t2, t3 = st.tabs(["⚡ RESULTS", "📜 ARCHIVE", "🤖 MARKETING KIT"])

# --- TAB 1: SCRAPER ---
with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        st.divider()
        c_ex1, c_ex2 = st.columns([3, 1])
        gs_url = c_ex1.text_input("Google Sheet URL")
        if c_ex2.button("🚀 Sync"):
            if sync_to_gsheet(st.session_state.results_df, gs_url): st.success("Synced!")
            
        st.download_button("📥 CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "leads.csv", use_container_width=True)
        spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    # 🔥🔥🔥 THE BEAST ENGINE 🔥🔥🔥
    if start and kws_in and city_in:
        st.session_state.running = True
        st.session_state.results_df = None
        all_leads = []
        
        # Split Inputs
        kw_list = [k.strip() for k in kws_in.split(',') if k.strip()]
        ct_list = [c.strip() for c in city_in.split(',') if c.strip()]
        total_ops = len(kw_list) * len(ct_list)
        curr_op = 0
        
        # Log Session
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kws_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
        try: s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        except: s_id = 1

        driver = get_driver()
        if driver:
            try:
                # 🔄 DOUBLE LOOP (Cities -> Keywords)
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        curr_op += 1
                        
                        update_ui(int(((curr_op-1)/total_ops)*100), f"SCANNING: {kw} in {city} ({curr_op}/{total_ops})")

                        # 1. Navigation (English enforced)
                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                        driver.get(url); time.sleep(4)

                        # 2. Bypass Cookies
                        try: driver.find_element(By.XPATH, "//button[contains(., 'Accept all')]").click(); time.sleep(2)
                        except: pass

                        # 3. Robust Scroll
                        try:
                            feed = None
                            try: feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            except: feed = driver.find_element(By.TAG_NAME, 'body')
                            
                            for i in range(depth_in):
                                if not st.session_state.running: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                feed.send_keys(Keys.END)
                                time.sleep(1.5)
                        except: pass
                        
                        # 4. Hybrid Extraction (XPATH + Class) - The "Beast" logic
                        # Find ANY link that looks like a place
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        seen = set(); unique = []
                        for e in elements:
                            h = e.get_attribute("href")
                            if h and h not in seen: seen.add(h); unique.append(e)
                        
                        valid_count = 0 # Count strict matches
                        
                        for idx, el in enumerate(unique):
                            if not st.session_state.running: break
                            if valid_count >= limit_in: break
                            if not is_admin and get_user_data(user)[0] <= 0: 
                                st.error("No Credits!"); st.session_state.running = False; break
                            
                            try:
                                # Click for details (Essential for Phone/Web)
                                driver.execute_script("arguments[0].click();", el)
                                time.sleep(1.5)
                                
                                # Extract
                                name = "N/A"; phone = "N/A"; web = "N/A"; addr = "N/A"
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = "Unknown"
                                
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: pass
                                
                                try: 
                                    p = driver.find_element(By.CSS_SELECTOR, '[data-item-id^="phone:tel:"]')
                                    phone = p.text
                                except: pass
                                
                                try:
                                    w = driver.find_element(By.CSS_SELECTOR, '[data-item-id="authority"]')
                                    web = w.get_attribute("href")
                                except: pass
                                
                                # 🔥 STRICT FILTER CHECKPOINT 🔥
                                if w_phone and (phone == "N/A" or phone == ""): continue
                                if w_web and (web == "N/A" or web == ""): continue
                                if w_nosite and web != "N/A": continue
                                
                                # Email (Deep)
                                email = "N/A"
                                if w_email and web != "N/A":
                                    email = fetch_email_deep(driver, web)
                                
                                # Format WhatsApp
                                wa = f"https://wa.me/{re.sub(r'[^\d]', '', phone)}" if phone != "N/A" else "N/A"
                                
                                row = {
                                    "Keyword": kw, "City": city, "Name": name, 
                                    "Phone": phone, "WhatsApp": wa, "Website": web, 
                                    "Email": email, "Address": addr
                                }
                                all_leads.append(row)
                                valid_count += 1
                                
                                # Update UI & DB
                                if not is_admin: deduct(user)
                                st.session_state.results_df = pd.DataFrame(all_leads)
                                spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                run_query("INSERT INTO leads (session_id, keyword, city, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (s_id, kw, city, name, phone, web, addr, wa, email))
                                
                            except: continue
                
                update_ui(100, "COMPLETED ✅")
                st.success(f"Finished! Collected {len(all_leads)} valid leads.")
            
            finally:
                driver.quit()
                st.session_state.running = False
                m_holder.empty(); st.rerun()

# --- TAB 2: ARCHIVE ---
with t2:
    st.subheader("📜 Search History")
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 20", is_select=True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT keyword, city, name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", is_select=True)
                df_h = pd.DataFrame(d, columns=["KW", "City", "Name", "Phone", "WA", "Web", "Email", "Addr"])
                st.dataframe(df_h, use_container_width=True)
                st.download_button("Export CSV", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{s[0]}.csv")
    except: pass

# --- TAB 3: MARKETING ---
with t3:
    st.subheader("🤖 Outreach Generator")
    srv = st.selectbox("Service", ["Web Design", "SEO", "Ads"])
    if st.button("Generate Script"):
        st.code(f"Hi! I found your business via {kws_in} in {city_in}. I noticed...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

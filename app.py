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
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. BASIC SETUP (NO COMPLICATED STATE)
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="🕷️")

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'logs' not in st.session_state: st.session_state.logs = []

# ==============================================================================
# 2. AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("❌ config.yaml missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False: st.error('❌ Login Failed'); st.stop()
elif st.session_state["authentication_status"] is None: st.warning('🔒 Login Required'); st.stop()

# ==============================================================================
# 3. DATABASE & SYNC
# ==============================================================================
def run_query(query, params=(), is_select=False):
    try:
        with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except: return [] if is_select else False

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
    try: run_query("SELECT status FROM user_credits LIMIT 1")
    except: run_query("ALTER TABLE user_credits ADD COLUMN status TEXT DEFAULT 'active'")
    try: run_query("SELECT email FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN email TEXT")

init_db()

def get_user_data(u):
    r = run_query("SELECT balance, status FROM user_credits WHERE username=?", (u,), True)
    if r: return r[0]
    run_query("INSERT INTO user_credits VALUES (?, 10, 'active')", (u,))
    return (10, 'active')

def deduct(u):
    if u != "admin": run_query("UPDATE user_credits SET balance=balance-1 WHERE username=?", (u,))

def add_credits(u, amt):
    run_query("UPDATE user_credits SET balance=balance+? WHERE username=?", (amt, u))

def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        st.error("⚠️ Secrets missing for Google Sheets"); return False
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
# 4. ROBUST ENGINE (THE FIX)
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    # Basic User Agent - Sometimes simpler is better to avoid complex fingerprinting flags
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email(driver, url):
    if not url or "google" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        driver.get(url); time.sleep(2)
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==============================================================================
# 5. ORANGE ELITE DESIGN RESTORED
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3 {{ color: #FFFFFF !important; font-family: 'Segoe UI'; }}
    
    /* 🔥 MOBILE POPUP RESTORED */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 10px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
    }}
    @media (max-width: 768px) {{
        .mobile-popup {{ display: block; }}
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
    }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* ANIMATED STRIPES */
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
# 6. APP LOGIC
# ==============================================================================
user = st.session_state["username"]
bal, status = get_user_data(user)
is_admin = user == "admin"

if status == 'suspended' and not is_admin: st.error("🚫 SUSPENDED"); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{bal}**")
    
    st.divider()
    
    # ADMIN
    if is_admin:
        with st.expander("🛠️ ADMIN PANEL"):
            data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(data, columns=["User", "Bal", "Sts"]), hide_index=True)
            
            tgt = st.selectbox("Target", [u[0] for u in data if u[0]!='admin'])
            if st.button("💰 +100"): 
                add_credits(tgt, 100); st.rerun()
            
            new_u = st.text_input("New User")
            new_p = st.text_input("Pass", type="password")
            if st.button("Add"):
                try: hp = stauth.Hasher.hash(new_p)
                except: hp = stauth.Hasher([new_p]).generate()[0]
                config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, 5, 'active')", (new_u,))
                st.success("OK"); st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- CONTENT ---
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    p_holder = st.empty() # Desktop Bar
    m_holder = st.empty() # Mobile Popup

# INPUTS
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kws = c1.text_input("🔍 Keywords (Ex: cafe, hotel)")
    cts = c2.text_input("🌍 Cities (Ex: Agadir, Casa)")
    limit = c3.number_input("Target", 1, 5000, 20)
    depth = c4.number_input("Depth", 5, 500, 10)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ Filters:")
        f = st.columns(4)
        w_phone = f[0].checkbox("Phone", True)
        w_web = f[1].checkbox("Web", True)
        w_email = f[2].checkbox("Email", False)
        w_nosite = f[3].checkbox("No Website", False)
        w_strict = st.checkbox("Strict City", True)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        start_btn = b1.button("START ENGINE", type="primary")
        stop_btn = b2.button("STOP", type="secondary")

if stop_btn:
    st.session_state.running = False
    st.rerun()

# TABS
t1, t2, t3 = st.tabs(["⚡ RESULTS", "📜 ARCHIVE", "🤖 MARKETING"])

with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        st.divider()
        col_e1, col_e2 = st.columns([3, 1])
        gs_url = col_e1.text_input("Google Sheet URL")
        if col_e2.button("🚀 Sync"):
            if sync_to_gsheet(st.session_state.results_df, gs_url): st.success("Synced!")
            
        st.download_button("📥 CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "leads.csv")
        spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    # ==========================
    # 🔥 THE FIXED ENGINE LOGIC
    # ==========================
    if start_btn and kws and cts:
        st.session_state.running = True
        st.session_state.results_df = None
        
        all_res = []
        kw_list = [k.strip() for k in kws.split(',') if k.strip()]
        ct_list = [c.strip() for c in cts.split(',') if c.strip()]
        total_ops = len(kw_list) * len(ct_list)
        curr_op = 0
        
        # Insert Session
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kws}", time.strftime("%Y-%m-%d %H:%M")))
        try: s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        except: s_id = 1

        driver = get_driver()
        if driver:
            try:
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        curr_op += 1
                        
                        # UPDATE UI (NO RERUN)
                        prog = int(((curr_op-1)/total_ops)*100)
                        msg = f"SCANNING: {kw} in {city} ({curr_op}/{total_ops})"
                        
                        # Desktop UI
                        p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{msg} {prog}%</div>""", unsafe_allow_html=True)
                        # Mobile UI
                        m_holder.markdown(f"""<div class="mobile-popup"><span style="color:{orange_c};font-weight:bold;">🚀 {msg}</span><br><div style="background:#333;height:6px;border-radius:3px;margin-top:5px;"><div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div></div><small>{prog}%</small></div>""", unsafe_allow_html=True)

                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                        driver.get(url); time.sleep(5)

                        # 🔥 BYPASS COOKIES
                        try:
                            driver.find_element(By.XPATH, "//button[contains(text(), 'Accept all')]").click()
                            time.sleep(2)
                        except: pass

                        # 🔥 SCROLL LOGIC (Fallback to Body if Feed fails)
                        try:
                            feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        except:
                            # Fallback: Just scroll the body if feed isn't explicitly found
                            feed = driver.find_element(By.TAG_NAME, "body")
                        
                        for i in range(depth):
                            if not st.session_state.running: break
                            # Scroll Down
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            if feed.tag_name == 'div':
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                            else:
                                feed.send_keys(Keys.END)
                            time.sleep(1.5)

                        # 🔥 EXTRACTION (XPATH contains Maps Place)
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        
                        # Deduplicate
                        unique_els = []
                        seen_urls = set()
                        for el in elements:
                            h = el.get_attribute("href")
                            if h and h not in seen_urls:
                                seen_urls.add(h)
                                unique_els.append(el)
                        
                        # Process Targets
                        for idx, el in enumerate(unique_els[:limit]):
                            if not st.session_state.running: break
                            if not is_admin and get_user_data(user)[0] <= 0: break
                            
                            try:
                                link = el.get_attribute("href")
                                driver.get(link); time.sleep(2)
                                
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = "Unknown"
                                
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: addr = ""
                                
                                if w_strict and city.lower() not in addr.lower(): continue
                                
                                web = "N/A"
                                try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                if w_nosite and web != "N/A": continue
                                
                                email = "N/A"
                                if w_email and web != "N/A": email = fetch_email(driver, web)
                                
                                phone = "N/A"; wa_link = None
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                                except: pass
                                
                                if w_phone and phone == "N/A": continue
                                if w_web and web == "N/A": continue
                                
                                row = {"Keyword": kw, "City": city, "Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Email": email, "Address": addr}
                                all_res.append(row)
                                
                                if not is_admin: deduct(user)
                                st.session_state.results_df = pd.DataFrame(all_res)
                                spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, phone, web, addr, wa_link, email))
                            except: continue
                
                # FINAL UPDATE
                p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:100%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>COMPLETED 100%</div>""", unsafe_allow_html=True)
                m_holder.empty()
                st.session_state.running = False
                
            finally: driver.quit()

with t2:
    st.subheader("📜 History")
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 20", is_select=True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", is_select=True)
                df_h = pd.DataFrame(d, columns=["Name", "Phone", "WA", "Web", "Email", "Addr"])
                st.dataframe(df_h, use_container_width=True)
                st.download_button("Export", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{s[0]}.csv")
    except: pass

with t3:
    st.subheader("🤖 Outreach")
    if st.button("Generate Script"):
        st.code(f"Hi! Found your business via {kws}...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

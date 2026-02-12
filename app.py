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
# 1. SYSTEM INITIALIZATION & PERSISTENCE
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Beast", layout="wide", page_icon="🕷️")

# Memory management to avoid data loss
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

# ==============================================================================
# 2. SECURITY & AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except:
    st.error("❌ config.yaml is missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass
if st.session_state["authentication_status"] is not True: st.stop()

# ==============================================================================
# 3. ROBUST DATABASE & SYNC
# ==============================================================================
def run_query(query, params=(), is_select=False):
    try:
        with sqlite3.connect('beast_ultimate.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except: return [] if is_select else False

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, keyword TEXT, city TEXT, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
    run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')

init_db()

def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,))
    return (100, 'active')

def deduct_credit(username):
    if username != "admin": run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        st.toast("⚠️ Secrets for GCP not found!", icon="❌"); return False
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
# 4. BEAST ENGINE CORE
# ==============================================================================
def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        try:
            driver.set_page_load_timeout(10); driver.get(url); time.sleep(1.5)
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
            valid = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif', '.svg', '.webp'))]
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return valid[0] if valid else "N/A"
        except: driver.close(); driver.switch_to.window(driver.window_handles[0]); return "N/A"
    except: return "N/A"

# ==============================================================================
# 5. UI STYLING (CALIBRI & ELITE THEME)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI&family=Open+Sans:wght@400;600;800&display=swap');
    
    /* Clean Typography - Calibri Style */
    html, body, .stApp {{ 
        font-family: 'Open Sans', 'Segoe UI', Tahoma, sans-serif !important; 
        background-color: #0f111a; 
    }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; }}
    
    /* Mobile Floating Bar */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 10px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 40px rgba(0,0,0,0.4);
        backdrop-filter: blur(10px);
    }}
    @media (max-width: 768px) {{ .mobile-popup {{ display: block; }} }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* Animated Progress Stripes */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ 
        height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; transition: width 0.4s ease; animation: stripes 1s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 50px 50px;}} }}
    
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; font-weight: 800 !important; }}
    </style>
""", unsafe_allow_html=True)

# --- APP LOGIC ---
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: Unlimited ♾️")
    else: st.warning(f"💎 Credits: {user_bal}")
    
    if is_admin:
        with st.expander("🛠️ ADMIN PANEL"):
            users = run_query("SELECT username, balance FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(users, columns=["User", "Bal"]), hide_index=True)
            target = st.selectbox("Target User", [u[0] for u in users if u[0]!='admin'])
            if st.button("💰 Add 100 Cr"):
                run_query("UPDATE user_credits SET balance=balance+100 WHERE username=?", (target,))
                st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- HEADER AREA ---
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

# --- CONTROL CENTER ---
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kw_in = c1.text_input("🔍 Keywords (Multi: cafe, snack)", placeholder="Ex: cafe, hotel")
    city_in = c2.text_input("🌍 Cities (Multi: Agadir, Casa)", placeholder="Ex: Agadir, Marrakech")
    limit_in = c3.number_input("Limit/City", 1, 5000, 20)
    depth_in = c4.number_input("Scroll Depth", 1, 500, 10)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ **STRICT BEAST FILTERS:**")
        f = st.columns(4)
        w_phone = f[0].checkbox("Must Have Phone", True)
        w_web = f[1].checkbox("Must Have Website", False)
        w_email = f[2].checkbox("Extract Email (Deep)", False)
        w_nosite = f[3].checkbox("No Website Only", False)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("START ENGINE", type="primary", use_container_width=True):
            if kw_in and city_in: st.session_state.running = True; st.session_state.results_df = None; st.rerun()
        if b2.button("STOP", type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

# --- LIVE RESULTS TAB ---
t1, t2, t3 = st.tabs(["⚡ LIVE ENGINE", "📜 HISTORY", "🤖 MARKETING"])

with t1:
    live_placeholder = st.empty()
    if st.session_state.results_df is not None:
        # 🔥 Dynamic Column Visibility Logic
        visible_cols = ["Keyword", "City", "Name", "Phone", "WhatsApp", "Address"]
        if w_web: visible_cols.append("Website")
        if w_email: visible_cols.append("Email")
        
        st.download_button("📥 Export CSV", st.session_state.results_df[visible_cols].to_csv(index=False).encode('utf-8-sig'), "beast_leads.csv", use_container_width=True)
        live_placeholder.dataframe(st.session_state.results_df[visible_cols], use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat Now")})

    if st.session_state.running:
        all_res = []
        kws = [k.strip() for k in kw_in.split(',') if k.strip()]
        cts = [c.strip() for c in city_in.split(',') if c.strip()]
        total_ops = len(kws) * len(cts)
        curr_op = 0
        
        # Session logging
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
        try: s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        except: s_id = 1

        driver = get_driver()
        try:
            for city in cts:
                for kw in kws:
                    if not st.session_state.running: break
                    curr_op += 1
                    update_ui(int(((curr_op-1)/total_ops)*100), f"SCANNING: {kw} in {city}")

                    url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                    driver.get(url); time.sleep(5)
                    try: driver.find_element(By.XPATH, "//button[contains(., 'Accept all')]").click(); time.sleep(2)
                    except: pass

                    # Scroll
                    try:
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(depth_in):
                            if not st.session_state.running: break
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                            time.sleep(1.5)
                    except: pass
                    
                    elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                    seen = set(); unique = []
                    for e in elements:
                        h = e.get_attribute("href")
                        if h and h not in seen: seen.add(h); unique.append(e)
                    
                    valid_city_count = 0
                    for el in unique:
                        if not st.session_state.running or valid_city_count >= limit_in: break
                        if not is_admin and get_user_data(current_user)[0] <= 0: break
                        
                        try:
                            # Use JS Click for stability
                            driver.execute_script("arguments[0].click();", el); time.sleep(1.8)
                            
                            # Extraction
                            name = "N/A"; phone = "N/A"; web = "N/A"; addr = "N/A"
                            try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            except: pass
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                            except: pass
                            try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone:", "").strip()
                            except: pass
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass

                            # 🔥 WHATSAPP LOGIC (No 05 numbers)
                            wa_link = None
                            wa_num = re.sub(r'[^\d]', '', phone)
                            # Detect Mobile Only (06 or 07)
                            is_mobile = any(wa_num.startswith(p) for p in ['2126', '2127', '06', '07'])
                            is_fixe = wa_num.startswith('2125') or (wa_num.startswith('05') and len(wa_num) <= 10)
                            
                            if is_mobile and not is_fixe:
                                wa_link = f"https://wa.me/{wa_num}"

                            # 🔥 STRICT FILTERS
                            if w_phone and (phone == "N/A" or phone == ""): continue
                            if w_web and (web == "N/A" or web == ""): continue
                            if w_nosite and web != "N/A": continue
                            
                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email_deep(driver, web)

                            # Save & Update
                            row = {"Keyword": kw, "City": city, "Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Email": email, "Address": addr}
                            all_res.append(row); valid_city_count += 1
                            
                            if not is_admin: deduct_credit(current_user)
                            st.session_state.results_df = pd.DataFrame(all_res)
                            
                            # 🔥 LIVE STREAM UPDATE
                            curr_cols = ["Keyword", "City", "Name", "Phone", "WhatsApp", "Address"]
                            if w_web: curr_cols.append("Website")
                            if w_email: curr_cols.append("Email")
                            
                            live_placeholder.dataframe(st.session_state.results_df[curr_cols], use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat Now")})
                            run_query("INSERT INTO leads (session_id, keyword, city, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (s_id, kw, city, name, phone, web, addr, wa_link, email))
                        except: continue
            update_ui(100, "MISSION ACCOMPLISHED ✅")
        finally: driver.quit(); st.session_state.running = False; st.rerun()

with t2:
    try:
        h_data = run_query("SELECT keyword, city, name, phone, whatsapp, website, email FROM leads ORDER BY id DESC LIMIT 100", is_select=True)
        st.dataframe(pd.DataFrame(h_data, columns=["KW", "City", "Name", "Phone", "WA", "Web", "Email"]), use_container_width=True)
    except: pass

with t3:
    st.subheader("🤖 Smart Outreach Generator")
    if st.button("Generate Script"):
        st.code(f"Hi, I found your business in {city_in} while searching for {kw_in}...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Elite Scraping Mastery 2026</div>', unsafe_allow_html=True)

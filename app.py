import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. SYSTEM CONFIGURATION & SESSION STATE (THE BRAIN)
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="🕷️")

# Initialize Session State (To ensure NO DATA LOSS)
defaults = {
    'results_df': None, 'running': False, 'progress_val': 0, 'status_txt': "READY",
    'p_kw': "", 'p_city': "", 'p_limit': 20, 'p_depth': 10,
    'current_log': []
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# 2. SECURITY & AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ Critical Error: 'config.yaml' file is missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Login Check
if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False:
    st.error('❌ Access Denied: Username/password incorrect'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('🔒 Secure System: Please Login'); st.stop()

# ==============================================================================
# 3. DATABASE MANAGEMENT (ROBUST SQLITE)
# ==============================================================================
def run_query(query, params=(), is_select=False):
    """Executes SQL queries safely with auto-commit"""
    try:
        with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except Exception as e:
        return [] if is_select else False

def init_db():
    """Initializes Database Tables if not exist"""
    tables = [
        '''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''',
        '''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''',
        '''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')'''
    ]
    for t in tables: run_query(t)
    
    # Migrations (Add columns if missing from old versions)
    try: run_query("SELECT email FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN email TEXT")

init_db()

def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, 10, 'active')", (username,))
    return (10, 'active')

def deduct_credit(username):
    if username != "admin": 
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def add_credits(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

# ==============================================================================
# 4. SCRAPING CORE (THE BEAST ENGINE)
# ==============================================================================
def get_driver_beast():
    """Configures Chrome Driver with Anti-Detection headers"""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled") # Hide Selenium
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    """Scans website heavily for emails"""
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        # Open new tab to keep main search intact
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        time.sleep(2)
        
        # Method 1: Regex on page source
        page_text = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_text)
        
        # Method 2: Check 'mailto' links if regex fails
        if not emails:
            mailtos = driver.find_elements(By.XPATH, '//a[starts-with(@href, "mailto:")]')
            for m in mailtos:
                emails.append(m.get_attribute("href").replace("mailto:", ""))
        
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        
        return emails[0] if emails else "N/A"
    except:
        # Emergency Cleanup
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==============================================================================
# 5. UI STYLING (ORANGE ELITE & MOBILE OPTIMIZED)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    /* Global Theme */
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* 🔥 Mobile Popup (Floating Status) */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 12px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 30px rgba(255, 140, 0, 0.2);
    }}
    @media (max-width: 768px) {{
        .mobile-popup {{ display: block; }}
        /* Force 2x2 Grid for Filters on Mobile */
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
    }}
    
    /* Branding */
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* Progress Bar */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; }}
    
    /* Buttons */
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; color: white !important; font-weight: 900 !important; font-size: 16px; padding: 10px; }}
    div.stButton > button[kind="secondary"] {{ border: 1px solid #FF4500 !important; color: #FF4500 !important; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. APP LOGIC & LAYOUT
# ==============================================================================
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

if user_st == 'suspended' and not is_admin: st.error("🚫 ACCESS SUSPENDED"); st.stop()

# --- SIDEBAR (USER PROFILE & ADMIN ACTIONS) ---
with st.sidebar:
    st.title("👤 User Profile")
    st.write(f"Logged as: **{st.session_state['name']}**")
    
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{user_bal}**")
    
    st.divider()
    
    # 🔥 ADMIN PANEL (Inside Expander = NO RESET)
    if is_admin:
        with st.expander("🛠️ ADMIN DASHBOARD (Manage)"):
            # Table
            u_data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(u_data, columns=["User", "Credits", "Status"]), hide_index=True)
            
            # Action Area
            st.markdown("---")
            tgt_usr = st.selectbox("Select Target", [u[0] for u in u_data if u[0]!='admin'])
            
            c_a, c_b = st.columns(2)
            if c_a.button("💰 +100"):
                add_credits(tgt_usr, 100); st.rerun()
            if c_b.button("🔄 Status"):
                curr = next((u[2] for u in u_data if u[0]==tgt_usr), 'active')
                new_s = 'suspended' if curr=='active' else 'active'
                run_query("UPDATE user_credits SET status=? WHERE username=?", (new_s, tgt_usr))
                st.rerun()
                
            # Create User
            st.markdown("---")
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password", type="password")
            if st.button("➕ Create User"):
                if new_u and new_p:
                    try: hp = stauth.Hasher.hash(new_p)
                    except: hp = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                    run_query("INSERT INTO user_credits VALUES (?, 5, 'active')", (new_u,))
                    st.success("Created!"); time.sleep(1); st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- MAIN CONTENT AREA ---

# Mobile Floating Status
if st.session_state.running:
    st.markdown(f"""
        <div class="mobile-popup">
            <span style="color:{orange_c};font-weight:bold;">🚀 {st.session_state.status_txt}</span><br>
            <div style="background:#333;height:6px;border-radius:3px;margin-top:5px;">
                <div style="background:{orange_c};width:{st.session_state.progress_val}%;height:100%;border-radius:3px;"></div>
            </div>
            <small>{st.session_state.progress_val}% Completed</small>
        </div>
    """, unsafe_allow_html=True)

# Header & Logo
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    # Desktop Progress Bar
    p_holder = st.empty()
    p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{st.session_state.progress_val}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{st.session_state.status_txt} {st.session_state.progress_val}%</div>""", unsafe_allow_html=True)

# INPUT SECTION
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    # 🔥 Multi-Input Support
    st.session_state.p_kw = c1.text_input("🔍 Keywords (Multi: cafe, hotel)", st.session_state.p_kw, placeholder="Ex: cafe, restaurant")
    st.session_state.p_city = c2.text_input("🌍 Cities (Multi: Agadir, Casa)", st.session_state.p_city, placeholder="Ex: Agadir, Inezgane")
    st.session_state.p_limit = c3.number_input("Target", 1, 5000, st.session_state.p_limit)
    st.session_state.p_depth = c4.number_input("Depth", 5, 500, st.session_state.p_depth)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ Advanced Filters:")
        f = st.columns(4) # Will wrap to 2x2 on mobile
        w_phone = f[0].checkbox("Has Phone", True)
        w_web = f[1].checkbox("Has Website", True)
        w_email = f[2].checkbox("Has Email (Deep)", False)
        w_nosite = f[3].checkbox("No Website Only", False)
        w_strict = st.checkbox("Strict City Matching", True)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("START ENGINE", type="primary", use_container_width=True):
            if st.session_state.p_kw and st.session_state.p_city:
                st.session_state.running = True; st.session_state.results_df = None; st.rerun()
            else: st.error("Please enter keywords and city!")
        
        if b2.button("STOP", type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

# RESULTS TABS
t1, t2, t3 = st.tabs(["⚡ LIVE RESULTS", "📜 HISTORY ARCHIVE", "🤖 MARKETING KIT"])

# --- TAB 1: LIVE ENGINE ---
with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        st.download_button("📥 Download CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "leads_data.csv")
        spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    # 🔥 ENGINE LOGIC
    if st.session_state.running:
        all_res = []
        kw_list = [k.strip() for k in st.session_state.p_kw.split(',') if k.strip()]
        ct_list = [c.strip() for c in st.session_state.p_city.split(',') if c.strip()]
        
        total_tasks = len(kw_list) * len(ct_list)
        current_task = 0
        
        # Log Session
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{st.session_state.p_kw} in {st.session_state.p_city}", time.strftime("%Y-%m-%d %H:%M")))
        try:
            # Safe ID retrieval
            s_data = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)
            s_id = s_data[0][0] if s_data else 1
        except: s_id = 1

        driver = get_driver_beast()
        if driver:
            try:
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        current_task += 1
                        
                        st.session_state.status_txt = f"SCANNING: {kw} in {city} ({current_task}/{total_tasks})"
                        st.session_state.progress_val = int(((current_task-1)/total_tasks)*100)
                        st.rerun()

                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}"
                        driver.get(url); time.sleep(4)

                        # 🔥 FIX 0% STUCK (XPATH SELECTOR)
                        try:
                            # Scroll container
                            try: feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            except: feed = driver.find_element(By.TAG_NAME, 'body')
                            
                            for i in range(st.session_state.p_depth):
                                if not st.session_state.running: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                time.sleep(1)
                        except: pass
                        
                        # Find Elements (Robust XPATH)
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        # Deduplicate
                        seen = set(); unique = []
                        for e in elements:
                            h = e.get_attribute("href")
                            if h and h not in seen:
                                seen.add(h); unique.append(e)
                        
                        # Process Targets
                        targets = unique[:st.session_state.p_limit]
                        
                        for idx, el in enumerate(targets):
                            if not st.session_state.running: break
                            if not is_admin and get_user_data(current_user)[0] <= 0: break
                            
                            try:
                                link = el.get_attribute("href")
                                driver.get(link); time.sleep(1.5)
                                
                                # Extract Fields
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = "Unknown"
                                
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: addr = ""
                                
                                # Strict Match
                                if w_strict and city.lower() not in addr.lower(): continue
                                
                                web = "N/A"
                                try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                if w_nosite and web != "N/A": continue
                                
                                # Email Deep Scan
                                email = "N/A"
                                if w_email and web != "N/A": email = fetch_email_deep(driver, web)
                                
                                # Phone & WhatsApp
                                phone = "N/A"; wa_link = None
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                                except: pass
                                
                                # Apply Filters
                                if w_phone and phone == "N/A": continue
                                if w_web and web == "N/A": continue
                                
                                row = {"Keyword": kw, "City": city, "Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Email": email, "Address": addr}
                                all_res.append(row)
                                
                                # Update UI & DB
                                if not is_admin: deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(all_res)
                                spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, phone, web, addr, wa_link, email))
                                
                            except: continue
                
                st.session_state.status_txt = "COMPLETED"; st.session_state.progress_val = 100
            
            finally: driver.quit(); st.session_state.running = False; st.rerun()

# --- TAB 2: ARCHIVE ---
with t2:
    st.subheader("📜 Previous Searches")
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 20", is_select=True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", is_select=True)
                df_h = pd.DataFrame(d, columns=["Name", "Phone", "WA", "Web", "Email", "Address"])
                st.dataframe(df_h, use_container_width=True)
                st.download_button("Export This", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{s[0]}.csv")
    except: st.info("No history yet.")

# --- TAB 3: MARKETING KIT ---
with t3:
    st.subheader("🤖 Outreach Generator")
    srv = st.selectbox("Service", ["Web Design", "SEO", "Ads Management"])
    if st.button("Generate Script"):
        st.code(f"Subject: Fixing your website presence in {st.session_state.p_city}...\n\nHi!\nI saw your business while searching for {st.session_state.p_kw}...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

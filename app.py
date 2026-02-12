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

# ==========================================
# 1. SETUP & PERSISTENCE
# ==========================================
st.set_page_config(page_title="ChatScrap Elite", layout="wide", page_icon="🕷️")

# Initialize Session State
keys = ['results_df', 'running', 'progress_val', 'status_txt', 'current_log']
for k in keys:
    if k not in st.session_state:
        st.session_state[k] = None if k == 'results_df' else (0 if k == 'progress_val' else "")

# Persistent Inputs
if 'p_kw' not in st.session_state: st.session_state.p_kw = ""
if 'p_city' not in st.session_state: st.session_state.p_city = ""
if 'p_limit' not in st.session_state: st.session_state.p_limit = 20
if 'p_depth' not in st.session_state: st.session_state.p_depth = 10

# ==========================================
# 2. AUTHENTICATION
# ==========================================
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

# ==========================================
# 3. DATABASE & DRIVER
# ==========================================
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

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
    run_query("INSERT INTO user_credits VALUES (?, 5, 'active')", (u,))
    return (5, 'active')

def deduct(u):
    if u != "admin": run_query("UPDATE user_credits SET balance=balance-1 WHERE username=?", (u,))

def get_driver():
    opts = Options()
    opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    # 🔥 Anti-Detection User Agent
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email(driver, url):
    if not url or "google" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        driver.get(url); time.sleep(2)
        # Regex for email
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==========================================
# 4. CSS (MOBILE POPUP & ORANGE THEME)
# ==========================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* 🔥 MOBILE POPUP */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(26, 31, 46, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 10px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
    }}
    @media (max-width: 768px) {{
        .mobile-popup {{ display: block; }}
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
    }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 10px rgba(255,140,0,0.6)) saturate(180%); margin-bottom: 25px; }}
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ height: 14px; background: {orange_c}; border-radius: 20px; transition: width 0.4s ease; }}
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; color: white !important; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 5. SIDEBAR & ADMIN
# ==========================================
user = st.session_state["username"]
bal, status = get_user_data(user)
is_admin = user == "admin"

if status == 'suspended' and not is_admin: st.error("🚫 SUSPENDED"); st.stop()

with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{bal}**")
    
    st.divider()
    
    # 🔥 ADMIN EXPANDER (PREVENTS RESET)
    if is_admin:
        with st.expander("🛠️ ADMIN PANEL"):
            data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            df_u = pd.DataFrame(data, columns=["User", "Bal", "Sts"])
            st.dataframe(df_u, hide_index=True)
            
            c1, c2 = st.columns(2)
            tgt = c1.selectbox("User", df_u['User'])
            if c2.button("💰 +100"):
                run_query("UPDATE user_credits SET balance=balance+100 WHERE username=?", (tgt,))
                st.rerun()
            
            # Create User
            new_u = st.text_input("New User")
            new_p = st.text_input("Pass", type="password")
            if st.button("Add User"):
                try: hp = stauth.Hasher.hash(new_p)
                except: hp = stauth.Hasher([new_p]).generate()[0]
                config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, 5, 'active')", (new_u,))
                st.success("Created!"); time.sleep(1); st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==========================================
# 6. MAIN ENGINE
# ==========================================
# Mobile Popup
if st.session_state.running:
    st.markdown(f"""
        <div class="mobile-popup">
            <span style="color:{orange_c};font-weight:bold;">{st.session_state.status_txt}</span><br>
            <div style="background:#333;height:6px;border-radius:3px;margin-top:5px;">
                <div style="background:{orange_c};width:{st.session_state.progress_val}%;height:100%;border-radius:3px;"></div>
            </div>
            <small>{st.session_state.progress_val}%</small>
        </div>
    """, unsafe_allow_html=True)

cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    p_holder = st.empty()
    p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{st.session_state.progress_val}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;'>{st.session_state.status_txt} {st.session_state.progress_val}%</div>""", unsafe_allow_html=True)

# INPUTS
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    # 🔥 Multi Input Logic
    st.session_state.p_kw = c1.text_input("🔍 Keywords (Comma separated)", st.session_state.p_kw, placeholder="Ex: cafe, snack, restaurant")
    st.session_state.p_city = c2.text_input("🌍 Cities (Comma separated)", st.session_state.p_city, placeholder="Ex: Agadir, Inezgane")
    st.session_state.p_limit = c3.number_input("Target/City", 1, 5000, st.session_state.p_limit)
    st.session_state.p_depth = c4.number_input("Depth", 5, 500, st.session_state.p_depth)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ Filters:")
        f = st.columns(4)
        w_ph = f[0].checkbox("Phone", True)
        w_wb = f[1].checkbox("Web", True)
        w_em = f[2].checkbox("Email (Deep)", False)
        w_ns = f[3].checkbox("No Website", False)
        w_st = st.checkbox("Strict City Match", True)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("START ENGINE", type="primary", use_container_width=True):
            if st.session_state.p_kw and st.session_state.p_city:
                st.session_state.running = True; st.session_state.results_df = None; st.rerun()
        if b2.button("STOP", type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

# TABS
t1, t2, t3 = st.tabs(["⚡ RESULTS", "📜 ARCHIVE", "🤖 MARKETING"])

with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        st.download_button("📥 CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "leads.csv")
        spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    # 🔥 ENGINE LOGIC (MULTI CITY + MULTI KEYWORD)
    if st.session_state.running:
        all_res = []
        kw_list = [k.strip() for k in st.session_state.p_kw.split(',') if k.strip()]
        ct_list = [c.strip() for c in st.session_state.p_city.split(',') if c.strip()]
        
        total_tasks = len(kw_list) * len(ct_list)
        current_task = 0
        
        # Log Session
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{st.session_state.p_kw} in {st.session_state.p_city}", time.strftime("%Y-%m-%d %H:%M")))
        s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]

        driver = get_driver()
        if driver:
            try:
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        current_task += 1
                        
                        # Update Status
                        st.session_state.status_txt = f"SEARCHING: {kw} in {city} ({current_task}/{total_tasks})"
                        st.session_state.progress_val = int(((current_task-1) / total_tasks) * 100)
                        st.rerun()

                        # Search URL
                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}"
                        driver.get(url); time.sleep(4)

                        # 🔥 FIX 0% STUCK: Robust Scrolling
                        try:
                            # Try finding feed, if fails, assume body (fallback)
                            try: feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            except: feed = driver.find_element(By.TAG_NAME, 'body')
                                
                            for i in range(st.session_state.p_depth):
                                if not st.session_state.running: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                time.sleep(1)
                        except: pass # Move to extraction if scroll fails
                        
                        # 🔥 FIX 0% STUCK: Robust Selection (XPATH)
                        # Finds ANY link that looks like a place listing
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        # Deduplicate by href
                        seen_urls = set()
                        unique_elements = []
                        for el in elements:
                            h = el.get_attribute("href")
                            if h and h not in seen_urls:
                                seen_urls.add(h)
                                unique_elements.append(el)

                        # Limit per keyword/city
                        targets = unique_elements[:st.session_state.p_limit]

                        for idx, el in enumerate(targets):
                            if not st.session_state.running: break
                            if not is_admin and get_user_data(user)[0] <= 0: break

                            try:
                                link = el.get_attribute("href")
                                driver.get(link); time.sleep(1.5)

                                # Extract Data
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = "Unknown"

                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: addr = ""
                                
                                # Strict Mode Check
                                if w_st and city.lower() not in addr.lower(): continue

                                web = "N/A"
                                try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                if w_ns and web != "N/A": continue

                                email = "N/A"
                                if w_em and web != "N/A": email = fetch_email(driver, web)

                                phone = "N/A"; wa_link = None
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                                except: pass

                                # Apply Filters
                                if w_ph and phone == "N/A": continue
                                if w_wb and web == "N/A": continue

                                row = {
                                    "Keyword": kw, "City": city, "Name": name, 
                                    "Phone": phone, "WhatsApp": wa_link, 
                                    "Website": web, "Email": email, "Address": addr
                                }
                                all_res.append(row)

                                # Live Update
                                st.session_state.results_df = pd.DataFrame(all_res)
                                spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                
                                # Save
                                if not is_admin: deduct(user)
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, phone, web, addr, wa_link, email))
                                
                            except: continue

                st.session_state.status_txt = "COMPLETED"; st.session_state.progress_val = 100
            finally: driver.quit(); st.session_state.running = False; st.rerun()

with t2:
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 15", True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", True)
                st.dataframe(pd.DataFrame(d, columns=["Name", "Phone", "WA", "Web", "Email", "Addr"]), use_container_width=True)
    except: pass

with t3:
    st.subheader("🤖 Marketing")
    if st.button("Generate Script"):
        st.code(f"Hi! I found your business in {st.session_state.p_city}...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

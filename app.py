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

# Initialize Session State (To prevent Resets)
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "READY"
# Inputs persistence
if 'p_keywords' not in st.session_state: st.session_state.p_keywords = ""
if 'p_city' not in st.session_state: st.session_state.p_city = ""
if 'p_limit' not in st.session_state: st.session_state.p_limit = 20
if 'p_depth' not in st.session_state: st.session_state.p_depth = 10

# ==========================================
# 2. AUTHENTICATION
# ==========================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ config.yaml missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False:
    st.error('❌ Login Failed'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('🔒 Please Login'); st.stop()

# ==========================================
# 3. DATABASE & FUNCTIONS
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

def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, ?, ?)", (username, 5, 'active')) 
    return (5, 'active')

def deduct_credit(username):
    if username != "admin": 
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def add_credits(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

def get_driver_fresh():
    opts = Options()
    opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    if not url or url == "N/A" or "google" in url: return "N/A"
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

# ==========================================
# 4. CSS (MOBILE POPUP & ORANGE ELITE)
# ==========================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* 🔥 Mobile Popup Progress */
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
    .progress-container {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; }}
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; color: white !important; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 5. SIDEBAR (USER + ADMIN EXPANDER)
# ==========================================
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

if user_st == 'suspended' and not is_admin: st.error("🚫 SUSPENDED"); st.stop()

with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{user_bal}**")
    
    st.divider()
    
    # 🔥 ADMIN PANEL (Inside Expander to prevent Reset)
    if is_admin:
        with st.expander("🛠️ ADMIN PANEL (Manage)"):
            users_sql = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(users_sql, columns=["User", "Bal", "Status"]), hide_index=True)
            
            # Quick Actions
            c1, c2 = st.columns(2)
            with c1:
                new_u = st.text_input("New User")
                new_p = st.text_input("Pass", type="password")
                if st.button("Add"):
                    if new_u and new_p:
                        try: hp = stauth.Hasher.hash(new_p)
                        except: hp = stauth.Hasher([new_p]).generate()[0]
                        config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                        with open('config.yaml', 'w') as f: yaml.dump(config, f)
                        run_query("INSERT INTO user_credits VALUES (?, ?, ?)", (new_u, 5, 'active'))
                        st.rerun()
            
            with c2:
                all_users = [r[0] for r in users_sql if r[0] != 'admin']
                if all_users:
                    tgt = st.selectbox("Target", all_users)
                    if st.button("💰 +100 Cr"):
                        add_credits(tgt, 100); st.rerun()
                    if st.button("🗑️ Delete"):
                        run_query("DELETE FROM user_credits WHERE username=?", (tgt,)); st.rerun()

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
            <span style="color:{orange_c};font-weight:bold;">🚀 {st.session_state.status_txt}</span><br>
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
    p_holder.markdown(f"""<div class="progress-container"><div class="progress-fill" style="width:{st.session_state.progress_val}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;'>{st.session_state.status_txt} {st.session_state.progress_val}%</div>""", unsafe_allow_html=True)

# INPUTS
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    # 🔥 Multi-Language Input Logic
    st.session_state.p_keywords = c1.text_input("🔍 Keywords (Multi-Lang, comma separated)", st.session_state.p_keywords, placeholder="Ex: Coffee, Café, مقهى")
    st.session_state.p_city = c2.text_input("🌍 Target City", st.session_state.p_city)
    st.session_state.p_limit = c3.number_input("Target", 1, 5000, st.session_state.p_limit)
    st.session_state.p_depth = c4.number_input("Depth", 5, 500, st.session_state.p_depth)

    st.divider()
    # 🔥 FILTERS RESTORED
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ Filters:")
        f = st.columns(4) # Wraps on mobile
        w_phone = f[0].checkbox("Phone", True)
        w_web = f[1].checkbox("Web", True)
        w_email = f[2].checkbox("Email (Deep)", False)
        w_nosite = f[3].checkbox("No Website", False)
        w_strict = st.checkbox("Strict City Match", True)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("START ENGINE", type="primary", use_container_width=True):
            if st.session_state.p_keywords and st.session_state.p_city:
                st.session_state.running = True; st.session_state.results_df = None; st.rerun()
        if b2.button("STOP", type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

# TABS
t1, t2, t3 = st.tabs(["⚡ RESULTS", "📜 ARCHIVE", "🤖 MARKETING"])

with t1:
    table_spot = st.empty()
    if st.session_state.results_df is not None:
        st.download_button("📥 CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "data.csv")
        table_spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    if st.session_state.running:
        results = []
        # 🔥 Split Keywords Logic
        keywords_list = [k.strip() for k in st.session_state.p_keywords.split(',')]
        total_kws = len(keywords_list)
        
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{st.session_state.p_keywords} - {st.session_state.p_city}", time.strftime("%Y-%m-%d %H:%M")))
        s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        
        driver = get_driver_fresh()
        if driver:
            try:
                for kw_idx, kw in enumerate(keywords_list):
                    if not st.session_state.running: break
                    
                    st.session_state.status_txt = f"SEARCHING: {kw} ({kw_idx+1}/{total_kws})"
                    st.session_state.progress_val = int((kw_idx / total_kws) * 100)
                    st.rerun()
                    
                    target = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(st.session_state.p_city)}"
                    driver.get(target); time.sleep(4)
                    
                    # Scroll
                    try:
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(st.session_state.p_depth):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1)
                    except: pass
                    
                    # Extract
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:st.session_state.p_limit]
                    links = [el.get_attribute("href") for el in items]
                    
                    for l_idx, link in enumerate(links):
                        if not st.session_state.running: break
                        if not is_admin and get_user_data(current_user)[0] <= 0: break
                        
                        try:
                            driver.get(link); time.sleep(1)
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                            except: addr = ""
                            
                            if w_strict and st.session_state.p_city.lower() not in addr.lower(): continue
                            
                            web = "N/A"
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            if w_nosite and web != "N/A": continue
                            
                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email_deep(driver, web)
                            
                            phone = "N/A"; wa_link = None
                            try:
                                p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                            except: pass

                            # Filters Logic
                            if w_phone and phone == "N/A": continue
                            if w_web and web == "N/A": continue

                            res_row = {"Keyword": kw, "Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Email": email, "Address": addr}
                            results.append(res_row)
                            
                            if not is_admin: deduct_credit(current_user)
                            st.session_state.results_df = pd.DataFrame(results)
                            table_spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                            run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, phone, web, addr, wa_link, email))
                        except: continue

                st.session_state.status_txt = "COMPLETED"; st.session_state.progress_val = 100
            finally: driver.quit(); st.session_state.running = False; st.rerun()

with t2:
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 10", is_select=True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", is_select=True)
                st.dataframe(pd.DataFrame(d, columns=["Name", "Phone", "WA", "Web", "Email", "Addr"]), use_container_width=True)
    except: pass

with t3:
    st.subheader("🤖 Outreach Generator")
    if st.button("Generate"):
        st.code(f"Hi, I saw your business {st.session_state.p_keywords} in {st.session_state.p_city}...")

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

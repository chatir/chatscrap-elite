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
from streamlit_authenticator.utilities.hasher import Hasher
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# --- 1. CONFIG & STYLING ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")

bg_color = "#0f111a"
card_bg = "#1a1f2e"
text_color = "#FFFFFF"
bar_color = "#FF8C00" 
start_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)" 
stop_grad = "linear-gradient(135deg, #e52d27 0%, #b31217 100%)"

st.markdown(f"""
    <style>
    .block-container {{ padding-top: 2rem !important; padding-bottom: 5rem !important; }}
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    .logo-container {{ display: flex; justify-content: center; padding: 20px; }}
    .logo-img {{ width: 280px; }}
    .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; }}
    .progress-container {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {bar_color}; }}
    .progress-fill {{ height: 14px; background: {start_grad}; border-radius: 20px; transition: width 0.4s ease; }}
    .progress-text {{ font-weight: 900; color: {bar_color}; text-align: center; margin-top: 10px; }}
    div.stButton > button[kind="primary"] {{ background: {start_grad} !important; color: white !important; border: none !important; width: 100% !important; font-weight: bold !important; }}
    div.stButton > button[kind="secondary"] {{ background: {stop_grad} !important; color: white !important; border: none !important; width: 100% !important; }}
    </style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL UTILS ---
def get_image_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    return None

def fetch_email(driver, url):
    if not url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[1]); driver.get(url); time.sleep(2)
        emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", driver.page_source, re.I)
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# 🔥 DRIVER SETUP (The Native Way for Streamlit Cloud)
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.binary_location = "/usr/bin/chromium" # مسار الكروميوم في السيرفر
    try:
        return webdriver.Chrome(options=options)
    except Exception as e:
        st.error(f"Driver Error: {e}")
        return None

# --- 3. DATABASE & AUTH ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
        curr = conn.cursor(); curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

# Init DB Tables
run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')

def get_user_info(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, ?, ?)", (username, 5, 'active')); return (5, 'active')

# Load Config
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("config.yaml missing!"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])

# Login
try: authenticator.login()
except: pass

if st.session_state["authentication_status"] is not True:
    if st.session_state["authentication_status"] is False: st.error('Incorrect Username/Password')
    else: st.warning('Please login')
    st.stop()

# User Data
current_user = st.session_state["username"]
user_bal, user_status = get_user_info(current_user)

if user_status == 'suspended' and current_user != 'admin':
    st.error("Account Suspended!"); st.stop()

# --- 4. APP INTERFACE ---
if 'running' not in st.session_state: st.session_state.running = False
if 'results_df' not in st.session_state: st.session_state.results_df = None

# Sidebar Logic
app_mode = "App"
with st.sidebar:
    st.title("Settings")
    if current_user == 'admin':
        app_mode = st.radio("Mode", ["App", "Admin Panel"])
    st.divider()
    st.write(f"👤 {st.session_state['name']}")
    st.info(f"💎 Credits: {user_bal}")
    authenticator.logout('Logout', 'main')

if app_mode == "Admin Panel":
    st.title("🛡️ Admin Panel")
    t1, t2 = st.tabs(["Dashboard", "Add User"])
    with t1:
        users = run_query("SELECT * FROM user_credits", is_select=True)
        st.table(pd.DataFrame(users, columns=['User', 'Balance', 'Status']))
    with t2:
        with st.form("add"):
            u = st.text_input("Username"); p = st.text_input("Password", type="password"); creds = st.number_input("Credits", value=100)
            if st.form_submit_button("Create"):
                h = Hasher([p]).generate()[0]
                config['credentials']['usernames'][u] = {'name': u, 'email': '', 'password': h}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, ?, 'active')", (u, creds))
                st.success("Done!"); st.rerun()

else:
    # APP UI
    logo_b64 = get_image_base64("chatscrape.png")
    if logo_b64: st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    # Inputs
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    niche = c1.text_input("🔍 Niche")
    city_in = c2.text_input("🌍 Cities (split by comma)")
    limit = c3.number_input("Target", 1, 1000, 20)
    scrolls = c4.number_input("Depth", 1, 100, 10)
    
    opts = st.columns(6)
    w_phone = opts[0].checkbox("Phone", True); w_web = opts[1].checkbox("Web", True)
    w_email = opts[2].checkbox("Email"); w_no_site = opts[3].checkbox("No Site")
    w_strict = opts[4].checkbox("Strict", True); w_sync = opts[5].checkbox("Sync")

    b1, b2 = st.columns(2)
    if b1.button("START ENGINE", type="primary"):
        if not niche or not city_in: st.error("Fill info!")
        elif user_bal <= 0: st.error("No credits!")
        else:
            st.session_state.running = True; st.session_state.results_df = None; st.rerun()
    if b2.button("STOP", type="secondary"): st.session_state.running = False; st.rerun()

    # Progress Bar Placeholder
    prog_place = st.empty()

    # Results
    if st.session_state.results_df is not None:
        st.dataframe(st.session_state.results_df, use_container_width=True)

    # Scraper Loop
    if st.session_state.running:
        cities = [c.strip() for c in city_in.split(',') if c.strip()]
        driver = get_driver()
        if driver:
            try:
                results = []
                for c_idx, city in enumerate(cities):
                    if not st.session_state.running: break
                    prog_place.markdown(f"🚀 **Targeting: {city.upper()}...**")
                    
                    run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%H:%M")))
                    s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                    
                    driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}")
                    time.sleep(5)
                    
                    # Basic Scroll
                    try:
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(scrolls): 
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed); time.sleep(1)
                    except: pass
                    
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit]
                    links = [i.get_attribute("href") for i in items]
                    
                    for link in links:
                        if not st.session_state.running or get_user_info(current_user)[0] <= 0: break
                        driver.get(link); time.sleep(2)
                        try:
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe').text
                            except: addr = "N/A"
                            
                            if w_strict and city.lower() not in addr.lower(): continue
                            
                            web = "N/A"
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            
                            if w_no_site and web != "N/A": continue
                            
                            row = {"Name": name, "Address": addr, "Website": web}
                            if w_phone:
                                try: p = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label"); row["Phone"] = p
                                except: row["Phone"] = "N/A"
                            
                            if w_email: row["Email"] = fetch_email(driver, web)
                            
                            results.append(row)
                            run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (current_user,))
                            st.session_state.results_df = pd.DataFrame(results)
                            st.rerun()
                        except: continue
                prog_place.success("✅ Extraction Completed!")
            finally: driver.quit(); st.session_state.running = False

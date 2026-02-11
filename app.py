import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
import shutil
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# --- 1. CONFIG & AUTHENTICATION ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark'

try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ config.yaml not found!")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# --- 2. LOGIN LOGIC ---
if st.session_state.get("authentication_status") is not True:
    try:
        authenticator.login()
    except Exception as e:
        st.error(f"Login Error: {e}")

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()

# --- 3. APP LOGIC (LOGGED IN) ---
if st.session_state["authentication_status"]:
    
    # --- DATABASE FUNCTIONS ---
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
        # DB Fixes
        try: run_query("SELECT status FROM user_credits LIMIT 1")
        except: run_query("ALTER TABLE user_credits ADD COLUMN status TEXT DEFAULT 'active'")
        try: run_query("SELECT whatsapp FROM leads LIMIT 1")
        except: run_query("ALTER TABLE leads ADD COLUMN whatsapp TEXT")
        try: run_query("SELECT email FROM leads LIMIT 1")
        except: run_query("ALTER TABLE leads ADD COLUMN email TEXT")

    init_db()

    def get_user_data(username):
        res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
        if res: return res[0]
        else:
            run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
            return (5, 'active')

    def deduct_credit(username):
        if username != "admin": # Admin Unlimited Logic
            run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

    def add_credits(username, amount):
        run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

    def update_user_status(username, status):
        run_query("UPDATE user_credits SET status = ? WHERE username=?", (status, username))

    # --- SESSION DATA ---
    current_user = st.session_state["username"]
    user_balance, user_status = get_user_data(current_user)

    if user_status == 'suspended' and current_user != "admin":
        st.error("🚫 Account Suspended. Contact Admin.")
        st.stop()

    if 'results_df' not in st.session_state: st.session_state.results_df = None
    if 'running' not in st.session_state: st.session_state.running = False
    if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
    if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

    # --- SIDEBAR NAVIGATION (HIDE FOR USERS) ---
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"User: **{st.session_state['name']}**")
        
        if current_user == "admin":
            st.success("💎 Credits: **Unlimited ♾️**")
            st.divider()
            choice = st.radio("GO TO:", ["🚀 SCRAPER ENGINE", "🛠️ USER MANAGEMENT"], index=0)
        else:
            st.warning(f"💎 Credits: **{user_balance}**")
            choice = "🚀 SCRAPER ENGINE" # Direct access for users
        
        st.divider()
        if st.button("Logout", type="secondary", use_container_width=True):
            authenticator.logout('Logout', 'main'); st.rerun()

    # --- STYLING (ORANGE THEME) ---
    st.markdown(f"""
        <style>
        .stApp {{ background-color: #0f111a; }}
        .stApp p, .stApp label, h1, h2, h3 {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
        .logo-img {{ width: 280px; filter: drop-shadow(0 0 10px rgba(255,140,0,0.5)) saturate(180%) hue-rotate(-5deg); margin-bottom: 25px; }}
        .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
        .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid #FF8C00; }}
        .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, #FF8C00, #FF8C00 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; }}
        div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important; width: 100% !important; border: none !important; color: white !important; font-weight: 900 !important; }}
        div.stButton > button[kind="secondary"] {{ background: linear-gradient(135deg, #e52d27 0%, #b31217 100%) !important; width: 100% !important; border: none !important; color: white !important; font-weight: 900 !important; }}
        .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); }}
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------
    # VIEW 1: USER MANAGEMENT
    # ---------------------------
    if choice == "🛠️ USER MANAGEMENT":
        st.markdown("<h1>🛠️ Admin Control Panel</h1>", unsafe_allow_html=True)
        users_list = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        live_df = pd.DataFrame(users_list, columns=["Username", "Balance", "Status"])
        st.dataframe(live_df, use_container_width=True)

        col_add, col_manage = st.columns(2)
        with col_add:
            st.markdown("### ➕ Register User")
            new_u, new_n, new_p = st.text_input("Username"), st.text_input("Name"), st.text_input("Password", type="password")
            if st.button("CREATE ACCOUNT", type="primary"):
                if new_u and new_p:
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_n, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    get_user_data(new_u); st.success(f"User {new_u} Created!"); time.sleep(1); st.rerun()

        with col_manage:
            st.markdown("### ⚙️ Management")
            db_users = [row[0] for row in users_list if row[0] != 'admin']
            if db_users:
                target = st.selectbox("Select User", db_users)
                c_top, c_stat = st.columns(2)
                with c_top:
                    amt = st.number_input("Credits", min_value=1, value=100)
                    if st.button("💰 Recharge", type="primary"):
                        add_credits(target, amt); st.success("Done!"); time.sleep(1); st.rerun()
                with c_stat:
                    _, u_stat = get_user_data(target)
                    b_lbl = "🚫 Suspend" if u_stat == "active" else "✅ Activate"
                    if st.button(b_lbl):
                        update_user_status(target, "suspended" if u_stat == "active" else "active"); st.rerun()
                
                st.divider()
                if st.button("🗑️ DELETE USER PERMANENTLY", use_container_width=True):
                    run_query("DELETE FROM user_credits WHERE username=?", (target,))
                    if target in config['credentials']['usernames']:
                        del config['credentials']['usernames'][target]
                        with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    st.error("Deleted!"); time.sleep(1); st.rerun()

    # ---------------------------
    # VIEW 2: SCRAPER ENGINE
    # ---------------------------
    elif choice == "🚀 SCRAPER ENGINE":
        def get_image_base64(path):
            if os.path.exists(path):
                with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
            return None

        @st.cache_resource
        def get_driver():
            opts = Options()
            opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")
            try:
                service = Service(ChromeDriverManager().install())
                return webdriver.Chrome(service=service, options=opts)
            except:
                try: return webdriver.Chrome(options=opts)
                except Exception as e: st.error(f"Driver Error: {e}"); return None

        c_main = st.columns([1, 6, 1])[1]
        with c_main:
            logo_b64 = get_image_base64("chatscrape.png")
            if logo_b64: st.markdown(f'<div style="display:flex; justify-content:center;"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
            
            pbar = st.empty()
            def update_bar(p, t):
                st.session_state.progress_val, st.session_state.status_txt = p, t
                pbar.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width:{p}%;"></div></div><div style='color:#FF8C00;font-weight:bold;margin-top:10px;'>{t} {p}%</div></div>""", unsafe_allow_html=True)
            update_bar(st.session_state.progress_val, st.session_state.status_txt)

        with st.container():
            col1, col2, col3, col4 = st.columns([3, 3, 1.5, 1.5])
            niche, city = col1.text_input("🔍 Business Niche", ""), col2.text_input("🌍 Global City", "")
            limit, scrolls = col3.number_input("Target", 1, 2000, 20), col4.number_input("Depth", 5, 500, 30)
            
            st.divider()
            col_opt, col_btn = st.columns([5, 3])
            with col_opt:
                st.write("⚙️ Filters:")
                # ALL FILTERS RESTORED (No Site, Sync, etc)
                f_opts = st.columns(6)
                w_phone = f_opts[0].checkbox("Phone", True); w_web = f_opts[1].checkbox("Web", True)
                w_email = f_opts[2].checkbox("Email", False); w_no_site = f_opts[3].checkbox("No Site", False)
                w_strict = f_opts[4].checkbox("Strict", True); w_sync = f_opts[5].checkbox("Sync", True)

            with col_btn:
                if st.button("START ENGINE", type="primary", use_container_width=True):
                    if niche and city and (user_balance > 0 or current_user == "admin"):
                        st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.results_df = None; st.rerun()
                    else: st.error("Check niche/city or credits!")
                if st.button("STOP", type="secondary", use_container_width=True): 
                    st.session_state.running = False; st.rerun()

        if st.session_state.results_df is not None:
            st.divider()
            st.download_button("📥 DOWNLOAD CSV RESULTS", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), f"{niche}_{city}.csv", "text/csv", use_container_width=True)

        if st.session_state.running:
            results = []
            run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
            s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
            
            driver = get_driver()
            if driver:
                try:
                    update_bar(5, "INITIALIZING..."); search_url = f"https://www.google.com/maps/search/{quote(niche)}+in+{quote(city)}"
                    driver.get(search_url); time.sleep(4)
                    
                    feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                    for i in range(scrolls):
                        if not st.session_state.running: break
                        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                        time.sleep(1.5); update_bar(10 + int((i/scrolls)*40), "SCROLLING...")
                    
                    links = [el.get_attribute("href") for el in driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]]
                    for idx, link in enumerate(links):
                        cb, _ = get_user_data(current_user)
                        if (cb <= 0 and current_user != "admin") or not st.session_state.running or len(results) >= limit: break
                        
                        update_bar(50 + int((idx/len(links))*50), f"SCRAPING {len(results)+1}/{limit}")
                        driver.get(link); time.sleep(2)
                        try:
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                            if w_strict and city.lower() not in addr.lower(): continue
                            
                            website = "N/A"
                            try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            if w_no_site and website != "N/A": continue
                            
                            row = {"Name": name, "Phone": "N/A", "Website": website, "Address": addr, "Email": "N/A"}
                            try:
                                p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                row["Phone"] = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                row["WhatsApp"] = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                            except: pass

                            results.append(row); deduct_credit(current_user)
                            st.session_state.results_df = pd.DataFrame(results)
                            st.dataframe(st.session_state.results_df, use_container_width=True)
                            run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, row["Phone"], website, addr, row.get("WhatsApp",""), "N/A"))
                        except: continue
                    update_bar(100, "COMPLETED")
                finally: driver.quit(); st.session_state.running = False

    st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

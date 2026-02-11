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
    st.error("❌ config.yaml missing!")
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
        # DB column integrity
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
        if username != "admin": # Unlimited for Admin
            run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

    def add_credits(username, amount):
        run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

    # --- SESSION CONTEXT ---
    current_user = st.session_state["username"]
    user_balance, user_status = get_user_data(current_user)

    if user_status == 'suspended' and current_user != "admin":
        st.error("🚫 Your account is suspended. Contact Admin.")
        st.stop()

    if 'results_df' not in st.session_state: st.session_state.results_df = None
    if 'running' not in st.session_state: st.session_state.running = False
    if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
    if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

    # --- SIDEBAR (DYNAMIC VIEW) ---
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"Logged as: **{st.session_state['name']}**")
        
        if current_user == "admin":
            st.success("💎 Credits: **Unlimited ♾️**")
            st.divider()
            # Only admin sees navigation
            choice = st.radio("MAIN NAVIGATION", ["🚀 SCRAPER ENGINE", "🛠️ USER MANAGEMENT"], index=0)
        else:
            st.warning(f"💎 Credits: **{user_balance}**")
            choice = "🚀 SCRAPER ENGINE"
        
        st.divider()
        if st.button("Logout", type="secondary", use_container_width=True):
            authenticator.logout('Logout', 'main'); st.rerun()

    # --- CSS (ORANGE ELITE THEME) ---
    orange_elite = "#FF8C00"
    st.markdown(f"""
        <style>
        .stApp {{ background-color: #0f111a; }}
        .stApp p, .stApp label, h1, h2, h3 {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
        /* Orange Glow Filter */
        .logo-img {{ width: 280px; filter: drop-shadow(0 0 12px rgba(255,140,0,0.5)) saturate(160%) hue-rotate(-5deg); margin-bottom: 30px; }}
        .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
        .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_elite}; }}
        .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {orange_elite}, {orange_elite} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; }}
        div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_elite} 0%, #FF4500 100%) !important; border: none !important; font-weight: 900 !important; color: white !important; }}
        .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); font-size: 13px; }}
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------
    # VIEW: ADMIN MANAGEMENT
    # ---------------------------
    if choice == "🛠️ USER MANAGEMENT" and current_user == "admin":
        st.markdown("<h1>🛠️ Admin Control Panel</h1>", unsafe_allow_html=True)
        users_sql = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        st.subheader("📊 Live Credits Table")
        st.dataframe(pd.DataFrame(users_sql, columns=["Username", "Balance", "Status"]), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### ➕ Register New User")
            new_u, new_n, new_p = st.text_input("Username"), st.text_input("Display Name"), st.text_input("Password", type="password")
            if st.button("CREATE ACCOUNT", type="primary"):
                if new_u and new_p:
                    # Updated Hasher for compatibility
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_n, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    get_user_data(new_u); st.success(f"Added {new_u}!"); time.sleep(1); st.rerun()

        with c2:
            st.markdown("### ⚙️ User Actions")
            db_user_list = [r[0] for r in users_sql if r[0] != 'admin']
            if db_user_list:
                target = st.selectbox("Select User", db_user_list)
                ma, ms = st.columns(2)
                with ma:
                    if st.button("💰 Add 100 Credits", type="primary"):
                        add_credits(target, 100); st.success("Updated!"); time.sleep(1); st.rerun()
                with ms:
                    _, u_st = get_user_data(target)
                    lbl = "🚫 Suspend" if u_st == "active" else "✅ Activate"
                    if st.button(lbl):
                        run_query("UPDATE user_credits SET status=? WHERE username=?", ("suspended" if u_st=="active" else "active", target)); st.rerun()
                
                st.divider()
                if st.button("🗑️ DELETE PERMANENTLY", use_container_width=True):
                    run_query("DELETE FROM user_credits WHERE username=?", (target,))
                    if target in config['credentials']['usernames']:
                        del config['credentials']['usernames'][target]
                        with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    st.error(f"User {target} wiped!"); time.sleep(1); st.rerun()

    # ---------------------------
    # VIEW: SCRAPER ENGINE
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
            # Improved driver setup to mitigate MaxRetryError
            try:
                service = Service(ChromeDriverManager().install())
                return webdriver.Chrome(service=service, options=opts)
            except:
                try: return webdriver.Chrome(options=opts)
                except Exception as e: st.error(f"Driver Error: {e}"); return None

        # Logo & Progress Area
        cm = st.columns([1, 6, 1])[1]
        with cm:
            logo_b64 = get_image_base64("chatscrape.png")
            if logo_b64: st.markdown(f'<div style="display:flex; justify-content:center;"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
            
            p_holder = st.empty()
            def update_bar(p, t):
                st.session_state.progress_val, st.session_state.status_txt = p, t
                p_holder.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width:{p}%;"></div></div><div style='color:{orange_elite};font-weight:bold;margin-top:10px;'>{t} {p}%</div></div>""", unsafe_allow_html=True)
            update_bar(st.session_state.progress_val, st.session_state.status_txt)

        # Input Controls
        with st.container():
            i1, i2, i3, i4 = st.columns([3, 3, 1.5, 1.5])
            niche, city = i1.text_input("🔍 Business Niche", ""), i2.text_input("🌍 Global City", "")
            limit, scrolls = i3.number_input("Target", 1, 2000, 20), i4.number_input("Depth", 5, 500, 30)
            
            st.divider()
            co, cb = st.columns([5, 3])
            with co:
                st.write("⚙️ Lead Filters:")
                fo = st.columns(6)
                w_phone = fo[0].checkbox("Phone", True); w_web = fo[1].checkbox("Web", True)
                w_email = fo[2].checkbox("Email", False); w_no_site = fo[3].checkbox("No Site", False)
                w_strict = fo[4].checkbox("Strict", True); w_sync = fo[5].checkbox("Sync", True)

            with cb:
                if st.button("START ENGINE", type="primary", use_container_width=True):
                    if niche and city and (user_balance > 0 or current_user == "admin"):
                        st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.results_df = None; st.rerun()
                    else: st.error("Check inputs or credits!")
                if st.button("STOP", type="secondary", use_container_width=True): 
                    st.session_state.running = False; st.rerun()

        # Output View
        t1, t2 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE"])
        
        with t1:
            table_spot = st.empty()
            if st.session_state.results_df is not None: table_spot.dataframe(st.session_state.results_df, use_container_width=True)

            if st.session_state.running:
                results = []
                run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
                s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                
                driver = get_driver()
                if driver:
                    try:
                        update_bar(5, "INITIALIZING ENGINE...")
                        # Safe URL encoding to prevent MaxRetryError
                        target_url = f"https://www.google.com/maps/search/{quote(niche)}+in+{quote(city)}"
                        driver.get(target_url); time.sleep(4)
                        
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(scrolls):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1.5); update_bar(10 + int((i/scrolls)*40), "SCROLLING...")
                        
                        links = [el.get_attribute("href") for el in driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]]
                        for idx, link in enumerate(links):
                            bal, _ = get_user_data(current_user)
                            if (bal <= 0 and current_user != "admin") or not st.session_state.running or len(results) >= limit: break
                            
                            update_bar(50 + int((idx/len(links))*50), f"SCRAPING {len(results)+1}/{limit}")
                            driver.get(link); time.sleep(2)
                            try:
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                adr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                if w_strict and city.lower() not in adr.lower(): continue
                                web = "N/A"
                                try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                
                                # No Site Filter Logic
                                if w_no_site and web != "N/A": continue
                                
                                row = {"Name": name, "Phone": "N/A", "Website": web, "Address": adr}
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    row["Phone"] = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    row["WhatsApp"] = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                                except: pass

                                results.append(row); deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(results)
                                table_spot.dataframe(st.session_state.results_df, use_container_width=True)
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?)", (s_id, name, row["Phone"], web, adr, row.get("WhatsApp","")))
                            except: continue
                        update_bar(100, "COMPLETED")
                    finally: driver.quit(); st.session_state.running = False

        with t2:
            st.subheader("📜 History")
            hists = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
            for h in hists:
                with st.expander(f"📦 {h[2]} | {h[1]}"):
                    dat = run_query(f"SELECT name, phone, website, address FROM leads WHERE session_id={h[0]}", is_select=True)
                    st.dataframe(pd.DataFrame(dat, columns=["Name", "Phone", "Website", "Address"]), use_container_width=True)

    st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

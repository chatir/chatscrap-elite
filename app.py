import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
import shutil
import yaml
import gspread
from google.oauth2.service_account import Credentials
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

# 🔥 PERSISTENCE: Initialize inputs to prevent data reset on navigation
if 'niche_val' not in st.session_state: st.session_state.niche_val = ""
if 'city_val' not in st.session_state: st.session_state.city_val = ""
if 'limit_val' not in st.session_state: st.session_state.limit_val = 20
if 'scroll_val' not in st.session_state: st.session_state.scroll_val = 30
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ config.yaml missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# --- 2. LOGIN LOGIC ---
if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except Exception as e: st.error(f"Login Error: {e}")

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your credentials'); st.stop()

# --- 3. APP LOGIC (LOGGED IN) ---
if st.session_state["authentication_status"]:
    
    # --- GOOGLE SHEETS SYNC ---
    def sync_to_gsheet(df, url):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
            client = gspread.authorize(creds)
            sh = client.open_by_url(url)
            ws = sh.get_worksheet(0)
            ws.clear()
            ws.update([df.columns.values.tolist()] + df.fillna("N/A").values.tolist())
            return True
        except Exception as e:
            st.error(f"Sync Error: {e}"); return False

    # --- DATABASE ---
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
        try: run_query("SELECT whatsapp FROM leads LIMIT 1")
        except: run_query("ALTER TABLE leads ADD COLUMN whatsapp TEXT")

    init_db()

    def get_user_data(username):
        res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
        if res: return res[0]
        else:
            run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
            return (5, 'active')

    def deduct_credit(username):
        if username != "admin": # 🔥 Admin Unlimited Credits
            run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

    # --- SESSION CONTEXT ---
    current_user = st.session_state["username"]
    user_balance, user_status = get_user_data(current_user)

    if user_status == 'suspended' and current_user != "admin":
        st.error("🚫 Account Suspended. Contact Admin."); st.stop()

    # --- SIDEBAR & LOGOUT FIX ---
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"Logged as: **{st.session_state['name']}**")
        
        if current_user == "admin":
            st.success("💎 Credits: **Unlimited ♾️**")
            st.divider()
            # Navigation persistent via Session State
            choice = st.radio("GO TO:", ["🚀 SCRAPER ENGINE", "🛠️ USER MANAGEMENT"], key="nav_choice")
        else:
            st.warning(f"💎 Credits: **{user_balance}**")
            choice = "🚀 SCRAPER ENGINE"
        
        st.divider()
        # 🔥 Fixed Logout logic
        if st.button("Logout", type="secondary", use_container_width=True):
            authenticator.logout('Logout', 'main')
            st.session_state.clear()
            st.rerun()

    # --- CSS (ORANGE ELITE DESIGN) ---
    orange_c = "#FF8C00"
    st.markdown(f"""
        <style>
        .stApp {{ background-color: #0f111a; }}
        .stApp p, .stApp label, h1, h2, h3 {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
        /* Orange Effect Filter */
        .logo-img {{ width: 280px; filter: drop-shadow(0 0 10px rgba(255,140,0,0.6)) saturate(200%) hue-rotate(-15deg); margin-bottom: 25px; }}
        .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
        .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
        .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; animation: move-stripes 1s linear infinite; }}
        @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
        div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; color: white !important; font-weight: 900 !important; border: none !important; }}
        .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); }}
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------
    # VIEW: ADMIN CONTROL
    # ---------------------------
    if choice == "🛠️ USER MANAGEMENT" and current_user == "admin":
        st.markdown("<h1>🛠️ Admin Control Panel</h1>", unsafe_allow_html=True)
        users_sql = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        st.subheader("📊 Live User Credits Monitor")
        st.dataframe(pd.DataFrame(users_sql, columns=["Username", "Balance", "Status"]), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### ➕ Register New User")
            new_u = st.text_input("Username")
            new_n = st.text_input("Name")
            new_p = st.text_input("Password", type="password")
            if st.button("CREATE ACCOUNT", type="primary"):
                if new_u and new_p:
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_n, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    get_user_data(new_u); st.success(f"Added {new_u}!"); time.sleep(1); st.rerun()

        with c2:
            st.markdown("### ⚙️ User Actions")
            db_list = [r[0] for r in users_sql if r[0] != 'admin']
            if db_list:
                target = st.selectbox("Select User", db_list)
                m1, m2 = st.columns(2)
                with m1:
                    if st.button("💰 Add 100 Credits", type="primary"):
                        run_query("UPDATE user_credits SET balance = balance + 100 WHERE username=?", (target,)); st.rerun()
                with m2:
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
                    st.error("User wiped out!"); time.sleep(1); st.rerun()

    # ---------------------------
    # VIEW: SCRAPER ENGINE
    # ---------------------------
    elif choice == "🚀 SCRAPER ENGINE":
        def get_driver_live():
            opts = Options()
            opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")
            try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            except: return webdriver.Chrome(options=opts)

        # Logo Area
        cm = st.columns([1, 6, 1])[1]
        with cm:
            if os.path.exists("chatscrape.png"):
                with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
                st.markdown(f'<div style="display:flex; justify-content:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
            
            p_holder = st.empty()
            def update_bar(p, t):
                st.session_state.progress_val = p
                p_holder.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width:{p}%;"></div></div><div style='color:{orange_c};font-weight:bold;margin-top:10px;text-align:center;'>{t} {p}%</div></div>""", unsafe_allow_html=True)
            update_bar(st.session_state.progress_val, "SYSTEM READY")

        # 🔥 Persistence Logic: Connect inputs to session state
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 3, 1.5, 1.5])
            niche = col1.text_input("🔍 Business Niche", value=st.session_state.niche_val, key="ni")
            city = col2.text_input("🌍 Global City", value=st.session_state.city_val, key="ci")
            limit = col3.number_input("Target Leads", 1, 2000, value=st.session_state.limit_val, key="li")
            depth = col4.number_input("Search Depth", 5, 500, value=st.session_state.scroll_val, key="sc")
            
            # Sync session state
            st.session_state.niche_val, st.session_state.city_val = niche, city
            st.session_state.limit_val, st.session_state.scroll_val = limit, depth

            st.divider()
            co, cb = st.columns([5, 3])
            with co:
                st.write("⚙️ Filters:")
                f_opts = st.columns(6)
                w_phone = f_opts[0].checkbox("Phone", True); w_web = f_opts[1].checkbox("Web", True)
                w_email = f_opts[2].checkbox("Email", False); w_no_site = f_opts[3].checkbox("No Site", False)
                w_strict = f_opts[4].checkbox("Strict", True); w_sync = f_opts[5].checkbox("Sync", True)

            with cb:
                if st.button("START ENGINE", type="primary", use_container_width=True):
                    if niche and city and (user_balance > 0 or current_user == "admin"):
                        st.session_state.running = True; st.session_state.results_df = None; st.rerun()
                    else: st.error("Check inputs or credits!")
                if st.button("STOP", type="secondary", use_container_width=True): st.session_state.running = False; st.rerun()

        # 🔥 Bottom Tabs Persistent
        t1, t2, t3 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE", "🤖 MARKETING KIT"])
        
        with t1:
            table_spot = st.empty()
            # SCRAPER LOGIC
            if st.session_state.running:
                results = []
                run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
                s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                
                # Fresh driver instance to prevent MaxRetryError
                driver = get_driver_live()
                if driver:
                    try:
                        update_bar(5, "INITIALIZING..."); target_url = f"https://www.google.com/maps/search/{quote(niche)}+in+{quote(city)}"
                        driver.get(target_url); time.sleep(4)
                        
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(depth):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1.5); update_bar(10 + int((i/depth)*40), "SCROLLING...")
                        
                        items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]
                        links = [el.get_attribute("href") for el in items]
                        for idx, link in enumerate(links):
                            bal, _ = get_user_data(current_user)
                            if (bal <= 0 and current_user != "admin") or not st.session_state.running or len(results) >= limit: break
                            
                            update_bar(50 + int((idx/len(links))*50), f"SCRAPING {len(results)+1}")
                            try:
                                driver.get(link); time.sleep(2)
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                adr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                if w_strict and city.lower() not in adr.lower(): continue
                                website = "N/A"
                                try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                if w_no_site and website != "N/A": continue
                                
                                # 🔥 Direct WhatsApp link
                                phone = "N/A"; wa_link = None
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                                except: pass

                                row = {"Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": website, "Address": adr}
                                results.append(row); deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(results)
                                table_spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?)", (s_id, name, phone, website, adr, wa_link))
                            except: continue
                        update_bar(100, "COMPLETED")
                    finally: driver.quit(); st.session_state.running = False

            # --- 🔥 PERSISTENT DATA VIEW (Shows even if admin switches pages) ---
            if st.session_state.results_df is not None:
                st.divider()
                # Config table with icon 💬
                table_spot.dataframe(
                    st.session_state.results_df, use_container_width=True,
                    column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
                )
                
                # 🔥 Persistent Google Sheet Export
                if w_sync:
                    st.subheader("📤 Export Results to Google Sheets")
                    gs_url = st.text_input("Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/...", key="gs_u")
                    if st.button("🚀 Sync to Sheet Now"):
                        if sync_to_gsheet(st.session_state.results_df, gs_url): st.success("✅ Success!")

        with t2:
            st.subheader("📜 Search History")
            hists = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
            for h in hists:
                with st.expander(f"📦 {h[2]} | {h[1]}"):
                    dat = run_query(f"SELECT name, phone, whatsapp, website, address FROM leads WHERE session_id={h[0]}", is_select=True)
                    df_h = pd.DataFrame(dat, columns=["Name", "Phone", "WhatsApp", "Website", "Address"])
                    st.dataframe(df_h, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                    st.download_button("Export CSV", df_h.to_csv(index=False).encode('utf-8-sig'), f"leads_{h[0]}.csv", key=f"dl_{h[0]}")

        with t3:
            st.subheader("🤖 Outreach Generator")
            offer = st.selectbox("Select Service", ["Web Design", "SEO", "SMMA"])
            if st.button("✨ Generate Message"):
                st.code(f"Hi! We noticed your business in {city}...", language="text")

    st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

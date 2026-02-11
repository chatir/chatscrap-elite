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
    
    # --- DATABASE FUNCTIONS (UPDATED FOR MANAGEMENT) ---
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
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

    def add_credits(username, amount):
        run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

    def update_user_status(username, status):
        run_query("UPDATE user_credits SET status = ? WHERE username=?", (status, username))

    # --- STATUS CHECK ---
    current_user = st.session_state["username"]
    user_balance, user_status = get_user_data(current_user)

    if user_status == 'suspended' and current_user != "admin":
        st.error("🚫 Your account has been suspended. Please contact the administrator.")
        st.stop()

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"User: **{st.session_state['name']}**")
        st.success(f"💎 Credits: **{user_balance}**")
        
        st.divider()
        # Navigation Menu
        menu_options = ["🚀 SCRAPER ENGINE"]
        if current_user == "admin":
            menu_options.append("🛠️ USER MANAGEMENT")
        
        choice = st.radio("GO TO:", menu_options, index=0)
        
        st.divider()
        authenticator.logout('Logout', 'main')

    # --- INITIALIZE STATE ---
    if 'results_df' not in st.session_state: st.session_state.results_df = None
    if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
    if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
    if 'running' not in st.session_state: st.session_state.running = False

    # --- STYLING (YOUR ORIGINAL DESIGN) ---
    bg_color = "#0f111a"; card_bg = "#1a1f2e"; text_color = "#FFFFFF"
    start_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)" 
    stop_grad = "linear-gradient(135deg, #e52d27 0%, #b31217 100%)"
    bar_color = "#FF8C00" 
    input_bg = "#1a1f2e"

    st.markdown(f"""
        <style>
        .block-container {{ padding-top: 2rem !important; padding-bottom: 5rem !important; }}
        .stApp {{ background-color: {bg_color}; }}
        .stApp p, .stApp label, h1, h2, h3 {{ color: {text_color} !important; font-family: 'Segoe UI', sans-serif; }}
        .logo-container {{ display: flex; flex-direction: column; align-items: center; padding-bottom: 20px; }}
        .logo-img {{ width: 280px; filter: sepia(100%) saturate(500%) hue-rotate(-10deg) brightness(1.2); transition: 0.3s; margin-bottom: 15px; }}
        .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
        .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {bar_color}; }}
        .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {bar_color}, {bar_color} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; }}
        div.stButton > button {{ border: none !important; border-radius: 12px !important; font-weight: 900 !important; font-size: 15px !important; height: 3.2em !important; color: #FFFFFF !important; }}
        div.stButton > button[kind="primary"] {{ background: {start_grad} !important; width: 100% !important; }}
        div.stButton > button[kind="secondary"] {{ background: {stop_grad} !important; width: 100% !important; }}
        .stTextInput input, .stNumberInput input {{ background-color: {input_bg} !important; color: {text_color} !important; border: 1px solid rgba(128,128,128,0.2) !important; border-radius: 10px !important; }}
        div[data-testid="metric-container"] {{ background-color: {card_bg}; padding: 15px; border-radius: 12px; }}
        .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: {bg_color}; color: #888888; text-align: center; padding: 15px; border-top: 1px solid rgba(128,128,128,0.1); font-size: 14px; }}
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------
    # VIEW 1: USER MANAGEMENT
    # ---------------------------
    if choice == "🛠️ USER MANAGEMENT" and current_user == "admin":
        st.title("🛠️ Admin Control Panel")
        
        # LIVE USER MONITORING
        st.subheader("📊 Live User Credits Monitor")
        users_list = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        live_df = pd.DataFrame(users_list, columns=["Username", "Balance", "Status"])
        st.dataframe(live_df, use_container_width=True)

        col_add, col_manage = st.columns(2)
        with col_add:
            st.markdown("### ➕ Register New User")
            new_u = st.text_input("Username")
            new_n = st.text_input("Name")
            new_p = st.text_input("Password", type="password")
            if st.button("CREATE ACCOUNT"):
                if new_u and new_p:
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_n, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                    get_user_data(new_u) # Create in DB
                    st.success("User added successfully!"); time.sleep(1); st.rerun()

        with col_manage:
            st.markdown("### ⚙️ Manage Existing User")
            target = st.selectbox("Select User", list(config['credentials']['usernames'].keys()))
            c_a, c_b = st.columns(2)
            with c_a:
                if st.button("💰 Add 100 Credits"):
                    add_credits(target, 100)
                    st.success("Credits added!"); time.sleep(1); st.rerun()
            with c_b:
                _, u_stat = get_user_data(target)
                b_lbl = "🚫 Suspend" if u_stat == "active" else "✅ Activate"
                if st.button(b_lbl):
                    update_user_status(target, "suspended" if u_stat == "active" else "active")
                    st.warning("Status changed!"); time.sleep(1); st.rerun()

    # ---------------------------
    # VIEW 2: SCRAPER ENGINE (FULL LOGIC)
    # ---------------------------
    elif choice == "🚀 SCRAPER ENGINE":
        
        # --- UTILS (FETCH EMAIL & PHONE) ---
        def get_image_base64(file_path):
            if os.path.exists(file_path):
                with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
            return None

        def fetch_email(driver, url):
            if not url or url == "N/A": return "N/A"
            try:
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[1])
                driver.get(url); time.sleep(1.5)
                emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", driver.page_source, re.I)
                driver.close(); driver.switch_to.window(driver.window_handles[0])
                return emails[0] if emails else "N/A"
            except:
                if len(driver.window_handles) > 1: driver.close()
                driver.switch_to.window(driver.window_handles[0]); return "N/A"

        def clean_phone_for_wa(phone):
            if not phone or phone == "N/A": return None
            clean = re.sub(r'[^\d+]', '', phone)
            return f"https://wa.me/{clean}"

        def clean_phone_display(text):
            if not text: return "N/A"
            return re.sub(r'[^\d+\s]', '', text).strip()

        @st.cache_resource
        def get_driver():
            opts = Options()
            opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--window-size=1920,1080")
            chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
            if chromium_path: opts.binary_location = chromium_path
            try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            except: return webdriver.Chrome(options=opts)

        # --- HEADER ---
        c_spacer, c_main, c_spacer2 = st.columns([1, 6, 1])
        with c_main:
            logo_b64 = get_image_base64("chatscrape.png")
            if logo_b64: st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
            else: st.markdown("<h1 style='text-align: center;'>ChatScrap</h1>", unsafe_allow_html=True)

            pbar_placeholder = st.empty()
            def update_bar(percent, text):
                st.session_state.progress_val = percent; st.session_state.status_txt = text
                bar_html = f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: {percent}%;"></div></div><div style='color:{bar_color};text-align:center;font-weight:bold;'>{text} {percent}%</div></div>"""
                pbar_placeholder.markdown(bar_html, unsafe_allow_html=True)

            if st.session_state.progress_val > 0: update_bar(st.session_state.progress_val, st.session_state.status_txt)
            else: update_bar(0, "SYSTEM READY")

        # --- MAIN FORM ---
        with st.container():
            c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
            with c1: niche = st.text_input("🔍 Business Niche", "")
            with c2: city = st.text_input("🌍 Global City", "")
            with c3: limit = st.number_input("Target Leads", 1, 2000, 20)
            with c4: scrolls = st.number_input("Search Depth", 5, 500, 30)
            
            st.divider()
            col_opt, col_btn = st.columns([5, 3])
            with col_opt:
                st.write("⚙️ Filters:")
                opts = st.columns(4)
                w_phone = opts[0].checkbox("Phone", True); w_web = opts[1].checkbox("Web", True)
                w_email = opts[2].checkbox("Email", False); w_strict = opts[3].checkbox("Strict", True)

            with col_btn:
                b1, b2 = st.columns([2, 1.5])
                with b1:
                    if st.button("START ENGINE", type="primary", use_container_width=True): 
                        if niche and city and user_balance > 0:
                            st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.results_df = None; st.rerun()
                        else: st.error("Check inputs/credits!")
                with b2:
                    if st.button("STOP", type="secondary", use_container_width=True): 
                        st.session_state.running = False; st.session_state.status_txt = "STOPPED"; st.rerun()

        # --- TABS & SCRAPER CORE ---
        t1, t2, t3 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE", "🤖 MARKETING KIT"])

        with t1:
            metrics_placeholder = st.empty(); table_placeholder = st.empty()
            if st.session_state.results_df is not None: table_placeholder.dataframe(st.session_state.results_df, use_container_width=True)

            if st.session_state.running:
                results = []
                run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
                s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                
                driver = get_driver()
                if driver:
                    try:
                        update_bar(5, "INITIALIZING..."); driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}"); time.sleep(4)
                        
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(scrolls):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1.2); update_bar(10 + int((i/scrolls)*40), "SCROLLING...")
                        
                        links = [el.get_attribute("href") for el in driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]]
                        
                        for idx, link in enumerate(links):
                            curr_bal, _ = get_user_data(current_user)
                            if curr_bal <= 0 or not st.session_state.running or len(results) >= limit: break
                            
                            update_bar(50 + int((idx/len(links))*50), f"SCRAPING {len(results)+1}")
                            driver.get(link); time.sleep(2)
                            try:
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                if w_strict and city.lower() not in addr.lower(): continue

                                website = "N/A"
                                try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                
                                row = {"Name": name, "Address": addr, "Website": website}
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    row["Phone"] = clean_phone_display(p_raw); row["WhatsApp"] = clean_phone_for_wa(p_raw)
                                except: row["Phone"] = "N/A"; row["WhatsApp"] = None

                                if w_email: row["Email"] = fetch_email(driver, website)

                                results.append(row); deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(results)
                                table_placeholder.dataframe(st.session_state.results_df, use_container_width=True)
                                
                                run_query("INSERT INTO leads (session_id, name, phone, website, email, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                          (s_id, name, row.get("Phone","N/A"), website, row.get("Email","N/A"), addr, row.get("WhatsApp","")))
                            except: continue
                        update_bar(100, "COMPLETED")
                    finally: driver.quit(); st.session_state.running = False

        with t2:
            sessions = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
            for sid, q, d in sessions:
                with st.expander(f"📦 {d} | {q}"):
                    data = run_query(f"SELECT name, phone, website, address FROM leads WHERE session_id={sid}", is_select=True)
                    st.dataframe(pd.DataFrame(data, columns=["Name", "Phone", "Website", "Address"]), use_container_width=True)

    st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

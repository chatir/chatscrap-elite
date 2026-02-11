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
from streamlit_authenticator.utilities.hasher import Hasher # 🔥 لزيادة الكليان
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. CONFIG & SETUP ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark'

CONFIG_FILE = 'config.yaml'

def load_config():
    try:
        with open(CONFIG_FILE) as file:
            return yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("❌ config.yaml not found!")
        st.stop()

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as file:
        yaml.dump(config_data, file, default_flow_style=False)

config = load_config()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# --- 2. DATABASE (CRM) ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    # 🔥 زدنا status باش نقدرو نبلوكيو الكليان
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
    
    # تأكد من وجود عمود status للكليان القدام
    try: run_query("ALTER TABLE user_credits ADD COLUMN status TEXT DEFAULT 'active'")
    except: pass

init_db()

# --- CRM FUNCTIONS ---
def get_user_info(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    else:
        # كليان جديد (أول مرة كيدخل)
        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
        return (5, 'active')

def update_user_balance(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

def update_user_status(username, status):
    run_query("UPDATE user_credits SET status = ? WHERE username=?", (status, username))

def delete_user_db(username):
    run_query("DELETE FROM user_credits WHERE username=?", (username,))

# --- 3. LOGIN LOGIC ---
try:
    authenticator.login()
except Exception:
    pass

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()

# --- 4. CHECK ACCOUNT STATUS (BAN SYSTEM) ---
current_user = st.session_state["username"]
user_data = get_user_info(current_user) # (balance, status)
current_balance = user_data[0]
account_status = user_data[1]

if account_status == 'suspended' and current_user != 'admin':
    st.error("🚫 Your account has been suspended. Please contact Admin.")
    st.stop()

# --- 5. APP INIT ---
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'running' not in st.session_state: st.session_state.running = False

# --- 6. ADMIN PANEL (THE POWER) 👑 ---
# هذا الكود كيبان غير لـ Admin
if current_user == 'admin':
    with st.sidebar:
        st.title("🛡️ Admin CRM")
        admin_tab = st.radio("Menu", ["Dashboard", "Add Client", "Manage Clients"])
        st.divider()

    if admin_tab == "Dashboard":
        # عرض جميع الكليان
        all_users = run_query("SELECT * FROM user_credits", is_select=True)
        st.subheader("📊 Client Overview")
        if all_users:
            admin_df = pd.DataFrame(all_users, columns=['Username', 'Balance', 'Status'])
            st.dataframe(admin_df, use_container_width=True)
        else:
            st.info("No clients found in database yet.")

    elif admin_tab == "Add Client":
        st.subheader("➕ Add New Client")
        with st.form("add_user_form"):
            new_user = st.text_input("Username (Login)")
            new_name = st.text_input("Full Name")
            new_email = st.text_input("Email")
            new_pass = st.text_input("Password", type="password")
            new_credits = st.number_input("Starting Credits", value=50)
            submitted = st.form_submit_button("Create Account")
            
            if submitted and new_user and new_pass:
                # 1. Update Config (YAML)
                hashed_pass = Hasher([new_pass]).generate()[0]
                config['credentials']['usernames'][new_user] = {
                    'name': new_name,
                    'email': new_email,
                    'password': hashed_pass
                }
                save_config(config)
                
                # 2. Update DB
                run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (new_user, new_credits, 'active'))
                st.success(f"User {new_user} created successfully!")
                time.sleep(1)
                st.rerun()

    elif admin_tab == "Manage Clients":
        st.subheader("⚙️ Manage Clients")
        # Get list of users from config (exclude admin)
        users_list = [u for u in config['credentials']['usernames'].keys() if u != 'admin']
        
        selected_user = st.selectbox("Select Client", users_list)
        
        if selected_user:
            u_info = get_user_info(selected_user) # (balance, status)
            
            c1, c2, c3 = st.columns(3)
            # Top Up
            with c1:
                st.info(f"💰 Balance: {u_info[0]}")
                amount = st.number_input("Add Credits", value=100, key="amt")
                if st.button("Top Up"):
                    update_user_balance(selected_user, amount)
                    st.success("Credits added!")
                    time.sleep(0.5); st.rerun()
            
            # Suspend/Active
            with c2:
                st.info(f"🚦 Status: {u_info[1]}")
                if u_info[1] == 'active':
                    if st.button("⏸️ Suspend Account"):
                        update_user_status(selected_user, 'suspended')
                        st.rerun()
                else:
                    if st.button("▶️ Activate Account"):
                        update_user_status(selected_user, 'active')
                        st.rerun()
            
            # Delete
            with c3:
                st.error("🗑️ Danger Zone")
                if st.button("Delete User"):
                    # Remove from Config
                    del config['credentials']['usernames'][selected_user]
                    save_config(config)
                    # Remove from DB
                    delete_user_db(selected_user)
                    st.success(f"User {selected_user} deleted!")
                    time.sleep(1); st.rerun()

# --- 7. REGULAR USER SIDEBAR ---
if current_user != 'admin':
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"User: **{st.session_state['name']}**")
        if user_balance > 10: st.success(f"💎 Credits: **{user_balance}**")
        elif user_balance > 0: st.warning(f"⚠️ Credits: **{user_balance}**")
        else: st.error(f"🚫 Credits: **0**")
        authenticator.logout('Logout', 'main')
else:
    with st.sidebar:
        if st.button("Logout Admin"):
            authenticator.logout('Logout', 'main')

# --- 8. UTILS & DRIVER ---
# (نفس الدوال السابقة: get_image_base64, fetch_email, clean_phone...)
def get_image_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

def fetch_email(driver, url):
    if not url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[1])
        driver.get(url)
        time.sleep(1.5)
        emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", driver.page_source, re.I)
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

def clean_phone_for_wa(phone):
    if not phone or phone == "N/A": return None
    clean = re.sub(r'[^\d+]', '', phone)
    check_num = clean.replace(" ", "").replace("-", "")
    if check_num.startswith("05") or check_num.startswith("+2125") or check_num.startswith("002125"):
        return None
    return f"https://wa.me/{clean}"

def clean_phone_display(text):
    if not text: return "N/A"
    clean = re.sub(r'[^\d+\s]', '', text).strip()
    return clean

@st.cache_resource
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=NetworkService")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium_path: options.binary_location = chromium_path

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception:
        return None

# --- 9. STYLING ---
bg_color = "#0f111a"
card_bg = "#1a1f2e"
text_color = "#FFFFFF"
start_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)" 
stop_grad = "linear-gradient(135deg, #e52d27 0%, #b31217 100%)"
bar_color = "#FF8C00" 
input_bg = "#1a1f2e"
footer_bg = "#0f111a"
footer_text = "#888888"

st.markdown(f"""
    <style>
    .block-container {{ padding-top: 2rem !important; padding-bottom: 5rem !important; }}
    .stApp {{ background-color: {bg_color}; }}
    .stApp p, .stApp label, h1, h2, h3, .progress-text {{ color: {text_color} !important; font-family: 'Segoe UI', sans-serif; }}
    .logo-container {{ display: flex; flex-direction: column; align-items: center; padding-bottom: 20px; }}
    .logo-img {{ width: 280px; filter: sepia(100%) saturate(500%) hue-rotate(-10deg) brightness(1.2); transition: 0.3s; margin-bottom: 15px; }}
    .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
    .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {bar_color}; box-shadow: 0 0 15px rgba(255, 140, 0, 0.2); }}
    .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {bar_color}, {bar_color} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; animation: move-stripes 1s linear infinite; box-shadow: 0 0 20px {bar_color}; }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    .progress-text {{ font-weight: 900; color: {bar_color}; margin-top: 10px; font-size: 1rem; letter-spacing: 2px; text-transform: uppercase; text-shadow: 0 0 10px rgba(255, 140, 0, 0.5); }}
    div.stButton > button {{ border: none !important; border-radius: 12px !important; font-weight: 900 !important; font-size: 15px !important; height: 3.2em !important; text-transform: uppercase !important; color: #FFFFFF !important; box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important; }}
    div.stButton > button[kind="primary"] {{ background: {start_grad} !important; width: 100% !important; }}
    div.stButton > button[kind="secondary"] {{ background: {stop_grad} !important; width: 100% !important; }}
    .stTextInput input, .stNumberInput input {{ background-color: {input_bg} !important; color: {text_color} !important; border: 1px solid rgba(128,128,128,0.2) !important; border-radius: 10px !important; }}
    div[data-testid="metric-container"] {{ background-color: {card_bg}; border: 1px solid rgba(255, 140, 0, 0.1); padding: 15px; border-radius: 12px; }}
    div[data-testid="metric-container"] label {{ opacity: 0.7; }}
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {{ color: {bar_color} !important; }}
    .stTooltipIcon {{ color: {bar_color} !important; }}
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: {footer_bg}; color: {footer_text}; text-align: center; padding: 15px; font-weight: bold; border-top: 1px solid rgba(128,128,128,0.1); z-index: 9999; font-size: 14px; }}
    </style>
""", unsafe_allow_html=True)

# --- 10. MAIN APP INTERFACE (ONLY IF ADMIN IS DONE OR REGULAR USER) ---
if current_user == 'admin' and admin_tab != "Dashboard":
    # إذا كان الادمين فاتح التبويبات الأخرى، نخبيو التطبيق باش مايتبرزطش
    pass
else:
    # --- HEADER ---
    c_spacer, c_main, c_spacer2 = st.columns([1, 6, 1])
    with c_main:
        logo_b64 = get_image_base64("chatscrape.png")
        if logo_b64: st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
        else: st.markdown("<h1 style='text-align: center;'>ChatScrap</h1>", unsafe_allow_html=True)

        pbar_placeholder = st.empty()
        def update_bar(percent, text):
            st.session_state.progress_val = percent
            st.session_state.status_txt = text
            bar_html = f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: {percent}%;"></div></div><div class="progress-text">{text} {percent}%</div></div>"""
            pbar_placeholder.markdown(bar_html, unsafe_allow_html=True)

        if st.session_state.progress_val > 0: update_bar(st.session_state.progress_val, st.session_state.status_txt)
        else: update_bar(0, "SYSTEM READY")

    # --- MAIN FORM ---
    with st.container():
        c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
        with c1: niche = st.text_input("🔍 Business Niche", "")
        with c2: city_input = st.text_input("🌍 Global Cities", "", help="Ex: Agadir, Casablanca")
        with c3: limit = st.number_input("Target Leads", 1, 2000, 20)
        with c4: scrolls = st.number_input("Search Depth", 5, 500, 30)
        
        st.markdown("<br>", unsafe_allow_html=True)
        col_opt, col_btn = st.columns([5, 3])
        with col_opt:
            st.write("⚙️ Filters:")
            opts = st.columns(6)
            w_phone = opts[0].checkbox("Phone", True)
            w_web = opts[1].checkbox("Web", True)
            w_email = opts[2].checkbox("Email", False)
            w_no_site = opts[3].checkbox("No Site", False)
            w_strict = opts[4].checkbox("Strict", True)
            opts[5].checkbox("Sync", True)

        with col_btn:
            st.write("")
            b1, b2 = st.columns([2, 1.5])
            with b1:
                if st.button("START ENGINE", type="primary", use_container_width=True): 
                    if not niche or not city_input:
                        st.error("Missing Info!")
                    elif user_balance <= 0:
                        st.error("❌ Insufficient Credits!")
                    else:
                        st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.status_txt = "STARTING..."; st.session_state.results_df = None; st.rerun()
            with b2:
                if st.button("STOP", type="secondary", use_container_width=True): 
                    st.session_state.running = False; st.session_state.status_txt = "STOPPED"; st.rerun()

    # --- RESULTS TABS & LOGIC ---
    t1, t2, t3 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE", "🤖 MARKETING KIT"])
    
    with t1:
        metrics_placeholder = st.empty()
        table_placeholder = st.empty()
        
        def update_metrics(df):
            with metrics_placeholder.container():
                m1, m2, m3, m4 = st.columns(4)
                if df is not None:
                    m1.metric("Leads", len(df), "🎯 Scraped")
                    m2.metric("Phones", len(df[df['WhatsApp'].notnull()]), "📱 Valid")
                    m3.metric("Sites", len(df[df['Website'] != "N/A"]), "🌐 Web")
                    m4.metric("Emails", len(df[df['Email'] != "N/A"]) if 'Email' in df.columns else 0, "📧 B2B")
                else: m1.metric("Leads", 0); m2.metric("Phones", 0); m3.metric("Sites", 0); m4.metric("Emails", 0)
        
        update_metrics(st.session_state.results_df)

        if st.session_state.results_df is not None:
            table_placeholder.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat"), "Website": st.column_config.LinkColumn("Site")})

        if st.session_state.running:
            results = []
            target_cities = [c.strip() for c in city_input.split(',') if c.strip()]
            driver = get_driver()
            
            if driver:
                try:
                    for city_idx, city in enumerate(target_cities):
                        if not st.session_state.running: break
                        
                        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
                        s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]

                        update_bar(0, f"🚀 TARGETING: {city.upper()}")
                        driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}")
                        time.sleep(4)
                        
                        try:
                            scroll_div = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            for i in range(scrolls):
                                if not st.session_state.running: break
                                driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scroll_div)
                                time.sleep(1)
                                update_bar(int((i / scrolls) * 30), f"SCROLLING {city.upper()}...")
                        except: pass
                        
                        items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]
                        links = [el.get_attribute("href") for el in items]
                        
                        for idx, link in enumerate(links):
                            if get_balance(current_user) <= 0: st.error("Credits Exhausted!"); st.session_state.running = False; break
                            if not st.session_state.running or len(results) >= limit * (city_idx + 1): break
                            
                            update_bar(30 + int((idx/len(links))*70), f"EXTRACTING FROM {city.upper()}")
                            try:
                                driver.get(link); time.sleep(1.5)
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                if any(d['Name'] == name for d in results): continue
                                
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: addr = "N/A"
                                
                                if w_strict and city.lower() not in addr.lower(): continue
                                website = "N/A"
                                if w_web:
                                    try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                    except: website = "N/A"
                                if w_no_site and website != "N/A": continue
                                
                                row = {"Name": name, "Address": addr, "Website": website, "City": city}
                                if w_phone:
                                    try: 
                                        p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                        row["Phone"] = clean_phone_display(p_raw)
                                        row["WhatsApp"] = clean_phone_for_wa(p_raw)
                                    except: row["Phone"] = "N/A"; row["WhatsApp"] = None
                                if w_email: row["Email"] = fetch_email(driver, row.get("Website", "N/A"))
                                
                                results.append(row)
                                deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(results)
                                update_metrics(st.session_state.results_df)
                                table_placeholder.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat"), "Website": st.column_config.LinkColumn("Site")})
                                run_query("INSERT INTO leads (session_id, name, phone, website, email, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, row.get("Phone", "N/A"), row.get("Website", "N/A"), row.get("Email", "N/A"), addr, row.get("WhatsApp", "")))
                            except: continue
                    update_bar(100, "COMPLETED")
                finally: driver.quit(); st.session_state.running = False

    with t2:
        sessions = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
        for sid, q, d in sessions:
            with st.expander(f"📦 {d} | {q}"):
                data = run_query(f"SELECT name, phone, website, email, address, whatsapp FROM leads WHERE session_id={sid}", is_select=True)
                df = pd.DataFrame(data, columns=["Name", "Phone", "Website", "Email", "Address", "WhatsApp"])
                st.dataframe(df, use_container_width=True)
                st.download_button("Export CSV", df.to_csv(index=False).encode('utf-8-sig'), f"leads_{sid}.csv", key=f"dl_{sid}")

    with t3:
        st.subheader("🤖 AI Cold Outreach")
        c1, c2 = st.columns(2)
        with c1: offer = st.selectbox("Offer", ["Web Design", "SEO"])
        with c2: aud = st.text_input("Audience", value=niche or "Business")
        if st.button("Generate"): st.code(f"Subject: Help {aud}...\n\nHello...", language="text")

st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

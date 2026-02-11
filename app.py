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
from streamlit_authenticator.utilities.hasher import Hasher
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. CONFIG & SETUP ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark'

# --- 2. GLOBAL STYLING (باش ما عمرو يتبلانطا) ---
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

# --- 3. AUTH & CONFIG ---
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

# --- 4. DATABASE ---
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
    try: run_query("ALTER TABLE user_credits ADD COLUMN status TEXT DEFAULT 'active'")
    except: pass

init_db()

# --- 5. LOGIN ---
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

# --- 6. HELPERS ---
def get_user_info(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    else:
        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
        return (5, 'active')

def update_user_balance(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

def update_user_status(username, status):
    run_query("UPDATE user_credits SET status = ? WHERE username=?", (status, username))

def delete_user_db(username):
    run_query("DELETE FROM user_credits WHERE username=?", (username,))

# State Init (للتطبيق)
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'running' not in st.session_state: st.session_state.running = False

current_user = st.session_state["username"]
user_data = get_user_info(current_user)
current_balance = user_data[0]
account_status = user_data[1]

if account_status == 'suspended' and current_user != 'admin':
    st.error("🚫 Your account has been suspended.")
    st.stop()

# --- 7. MAIN LOGIC (SWITCH) ---
app_mode = "Scraper App" # Default mode

if current_user == 'admin':
    with st.sidebar:
        st.title("🛡️ Admin Controls")
        # 🔥 هنا الحل: الادمين يختار واش بغا يخدم ولا يجيري
        app_mode = st.radio("Choose Mode", ["Scraper App", "Admin Panel"])
        st.divider()

if app_mode == "Admin Panel":
    # ==========================
    # 👑 ADMIN PANEL
    # ==========================
    st.title("🛡️ Client Management")
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add Client", "⚙️ Manage"])
    
    with tab1:
        st.subheader("All Clients")
        all_users = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        if all_users:
            st.dataframe(pd.DataFrame(all_users, columns=['Username', 'Credits', 'Status']), use_container_width=True)
    
    with tab2:
        st.subheader("New Account")
        with st.form("new_c"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            n = st.text_input("Name")
            e = st.text_input("Email")
            c = st.number_input("Credits", value=100)
            if st.form_submit_button("Create"):
                if u and p:
                    try:
                        # 🔥 FIX HASHER (Try/Except fallbak)
                        try:
                            hashed = Hasher([str(p)]).generate()[0]
                        except:
                            # Fallback if library fails
                            hashed = p 
                        
                        config['credentials']['usernames'][u] = {'name': n, 'email': e, 'password': hashed}
                        save_config(config)
                        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (u, c, 'active'))
                        st.success(f"User {u} Created!")
                        time.sleep(1); st.rerun()
                    except Exception as err:
                        st.error(f"Error: {err}")

    with tab3:
        st.subheader("Edit Clients")
        users = [x for x in config['credentials']['usernames'] if x != 'admin']
        sel = st.selectbox("Select", users)
        if sel:
            inf = get_user_info(sel)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💰 Add 100 Credits"):
                    update_user_balance(sel, 100); st.success("Added!"); time.sleep(0.5); st.rerun()
            with c2:
                if st.button("🗑️ Delete User"):
                    del config['credentials']['usernames'][sel]; save_config(config); delete_user_db(sel); st.rerun()

else:
    # ==========================
    # 🚀 SCRAPER APP (Visible to Admin & Users)
    # ==========================
    with st.sidebar:
        st.write(f"👤 **{st.session_state['name']}**")
        st.info(f"💎 Credits: {current_balance}")
        authenticator.logout('Logout', 'main')

    def get_image_base64(file_path):
        if os.path.exists(file_path):
            with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
        return None

    c_spacer, c_main, c_spacer2 = st.columns([1, 6, 1])
    with c_main:
        logo_b64 = get_image_base64("chatscrape.png")
        if logo_b64: st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{logo_b64}" class="logo-img"></div>', unsafe_allow_html=True)
        else: st.markdown("<h1 style='text-align: center;'>ChatScrap</h1>", unsafe_allow_html=True)
        
        # Progress Bar Logic
        if st.session_state.progress_val > 0:
            st.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: {st.session_state.progress_val}%;"></div></div><div class="progress-text">{st.session_state.status_txt} {st.session_state.progress_val}%</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: 0%;"></div></div><div class="progress-text">SYSTEM READY 0%</div></div>""", unsafe_allow_html=True)

    with st.container():
        c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
        with c1: niche = st.text_input("🔍 Business Niche", "")
        with c2: city_input = st.text_input("🌍 Cities", "")
        with c3: limit = st.number_input("Target", 1, 2000, 20)
        with c4: scrolls = st.number_input("Depth", 5, 500, 30)
        
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
                    elif current_balance <= 0:
                        st.error("❌ No Credits!")
                    else:
                        st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.status_txt = "STARTING..."; st.session_state.results_df = None; st.rerun()
            with b2:
                if st.button("STOP", type="secondary", use_container_width=True): 
                    st.session_state.running = False; st.session_state.status_txt = "STOPPED"; st.rerun()

    t1, t2, t3 = st.tabs(["⚡ LIVE", "📜 ARCHIVE", "🤖 AI KIT"])
    
    # Driver & Utils
    def fetch_email(driver, url):
        if not url or url == "N/A": return "N/A"
        try:
            driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[1]); driver.get(url); time.sleep(1.5)
            emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", driver.page_source, re.I)
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return emails[0] if emails else "N/A"
        except: 
            if len(driver.window_handles)>1: driver.close(); driver.switch_to.window(driver.window_handles[0])
            return "N/A"

    def clean_phone_for_wa(phone):
        if not phone or phone == "N/A": return None
        clean = re.sub(r'[^\d+]', '', phone); check = clean.replace(" ", "")
        if check.startswith("05") or check.startswith("+2125"): return None
        return f"https://wa.me/{clean}"

    def clean_phone_display(text):
        return re.sub(r'[^\d+\s]', '', text).strip() if text else "N/A"

    @st.cache_resource
    def get_driver():
        options = Options()
        options.add_argument("--headless"); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument("--disable-gpu"); options.add_argument("--disable-features=NetworkService"); options.add_argument("--window-size=1920,1080"); options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        if chromium_path: options.binary_location = chromium_path
        try: service = Service(ChromeDriverManager().install()); return webdriver.Chrome(service=service, options=options)
        except: return None

    with t1:
        if st.session_state.results_df is not None:
             st.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat"), "Website": st.column_config.LinkColumn("Site")})

        if st.session_state.running:
            results = []; target_cities = [c.strip() for c in city_input.split(',') if c.strip()]; driver = get_driver()
            if driver:
                try:
                    for city_idx, city in enumerate(target_cities):
                        if not st.session_state.running: break
                        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M"))); s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                        st.session_state.status_txt = f"TARGETING: {city.upper()}"; st.rerun() # Refresh text
                        driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}"); time.sleep(4)
                        
                        try:
                            scroll_div = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            for i in range(scrolls):
                                if not st.session_state.running: break
                                driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scroll_div); time.sleep(1)
                        except: pass
                        
                        items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]; links = [el.get_attribute("href") for el in items]
                        for idx, link in enumerate(links):
                            if get_user_info(current_user)[0] <= 0: st.error("Credits Exhausted!"); st.session_state.running = False; break
                            if not st.session_state.running or len(results) >= limit*(city_idx+1): break
                            
                            try:
                                driver.get(link); time.sleep(1.5)
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                if any(d['Name']==name for d in results): continue
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: addr = "N/A"
                                if w_strict and city.lower() not in addr.lower(): continue
                                website = "N/A"
                                if w_web:
                                    try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                    except: website = "N/A"
                                if w_no_site and website!="N/A": continue
                                row = {"Name": name, "Address": addr, "Website": website, "City": city}
                                if w_phone:
                                    try: p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label"); row["Phone"] = clean_phone_display(p_raw); row["WhatsApp"] = clean_phone_for_wa(p_raw)
                                    except: row["Phone"] = "N/A"; row["WhatsApp"] = None
                                if w_email: row["Email"] = fetch_email(driver, row.get("Website", "N/A"))
                                results.append(row); update_user_balance(current_user, -1); st.session_state.results_df = pd.DataFrame(results); 
                                run_query("INSERT INTO leads (session_id, name, phone, website, email, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, row.get("Phone", "N/A"), row.get("Website", "N/A"), row.get("Email", "N/A"), addr, row.get("WhatsApp", "")))
                            except: continue
                    st.session_state.status_txt = "COMPLETED"; st.session_state.progress_val = 100; st.rerun()
                finally: driver.quit(); st.session_state.running = False

    with t2:
        sessions = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
        for sid, q, d in sessions:
            with st.expander(f"📦 {d} | {q}"):
                data = run_query(f"SELECT name, phone, website, email, address, whatsapp FROM leads WHERE session_id={sid}", is_select=True); df = pd.DataFrame(data, columns=["Name", "Phone", "Website", "Email", "Address", "WhatsApp"]); st.dataframe(df, use_container_width=True); st.download_button("Export CSV", df.to_csv(index=False).encode('utf-8-sig'), f"leads_{sid}.csv", key=f"dl_{sid}")
    
    with t3:
        st.subheader("🤖 AI Cold Outreach"); c1, c2 = st.columns(2); offer = c1.selectbox("Offer", ["Web Design", "SEO"]); aud = c2.text_input("Audience", value=niche or "Business")
        if st.button("Generate"): st.code(f"Subject: Help {aud}...\n\nHello...", language="text")

st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

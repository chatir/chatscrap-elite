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

# ==========================================
# 1. CONFIGURATION & SESSION STATE SETUP
# ==========================================
st.set_page_config(page_title="ChatScrap Elite", layout="wide", page_icon="🕷️")
st.session_state.theme = 'Dark'

# Initialize all Session State variables for Persistence (باش ميمشيش ليك والو)
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'niche_val' not in st.session_state: st.session_state.niche_val = ""
if 'city_val' not in st.session_state: st.session_state.city_val = ""
if 'limit_val' not in st.session_state: st.session_state.limit_val = 20
if 'scroll_val' not in st.session_state: st.session_state.scroll_val = 30

# Load Credentials
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ Error: config.yaml file not found!")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# ==========================================
# 2. AUTHENTICATION LOGIC
# ==========================================
if st.session_state.get("authentication_status") is not True:
    try:
        authenticator.login()
    except Exception as e:
        st.error(f"Authentication Error: {e}")

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
    st.stop()

# ==========================================
# 3. DATABASE MANAGEMENT FUNCTIONS
# ==========================================
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select:
            return curr.fetchall()
        conn.commit()

def init_db():
    # Session History Table
    run_query('''CREATE TABLE IF NOT EXISTS sessions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
    # Leads Table
    run_query('''CREATE TABLE IF NOT EXISTS leads 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, 
                  name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    # Users Credits Table
    run_query('''CREATE TABLE IF NOT EXISTS user_credits 
                 (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')
    
    # Migrations (Just in case columns are missing)
    try: run_query("SELECT status FROM user_credits LIMIT 1")
    except: run_query("ALTER TABLE user_credits ADD COLUMN status TEXT DEFAULT 'active'")
    try: run_query("SELECT whatsapp FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN whatsapp TEXT")
    try: run_query("SELECT email FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN email TEXT")

init_db()

def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res:
        return res[0]
    else:
        # Auto-create entry for new users in config but not in DB
        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
        return (5, 'active')

def deduct_credit(username):
    if username != "admin": # Admin Unlimited
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def add_credits(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

# ==========================================
# 4. UTILITY FUNCTIONS (Scraping & UI)
# ==========================================
def get_driver_fresh():
    """Generates a fresh driver instance to prevent MaxRetryError"""
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=opts)
    except:
        return webdriver.Chrome(options=opts)

def fetch_email_from_site(driver, url):
    """Extra logic to dig for emails inside websites"""
    if not url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        time.sleep(2)
        page_source = driver.page_source
        emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", page_source, re.I)
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        # Cleanup if tab crashes
        if len(driver.window_handles) > 1:
            driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==========================================
# 5. UI STYLING (ORANGE ELITE & MOBILE)
# ==========================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, h4 {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* Logo Effect */
    .logo-img {{ 
        width: 280px; 
        filter: drop-shadow(0 0 10px rgba(255,140,0,0.6)) saturate(180%) hue-rotate(-5deg); 
        margin-bottom: 25px; 
    }}
    
    /* Progress Bar Animation */
    .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
    .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .progress-fill {{ 
        height: 14px; 
        background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; 
        transition: width 0.4s ease; 
        animation: move-stripes 1s linear infinite; 
    }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    
    /* Buttons */
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; color: white !important; font-weight: 900 !important; border: none !important; }}
    div.stButton > button[kind="secondary"] {{ background: linear-gradient(135deg, #e52d27 0%, #b31217 100%) !important; color: white !important; font-weight: 900 !important; border: none !important; }}
    
    /* Mobile Responsive Logic */
    .mobile-float {{ display: none; }}
    @media (max-width: 768px) {{
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
        .mobile-float {{ 
            display: block; position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
            width: 90%; background: {orange_c}; color: white; padding: 10px; border-radius: 10px;
            z-index: 9999; text-align: center; font-weight: bold; box-shadow: 0 5px 15px rgba(0,0,0,0.5);
        }}
    }}
    
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); font-size: 13px; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 6. MAIN APP LOGIC
# ==========================================
if st.session_state["authentication_status"]:
    
    # Check User Status
    current_user = st.session_state["username"]
    user_balance, user_status = get_user_data(current_user)

    if user_status == 'suspended' and current_user != "admin":
        st.error("🚫 Your account is suspended. Please contact the administrator.")
        st.stop()

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.title("👤 User Profile")
        st.write(f"Logged as: **{st.session_state['name']}**")
        
        if current_user == "admin":
            st.success("💎 Credits: **Unlimited ♾️**")
            st.divider()
            # Navigation persistent key
            choice = st.radio("MAIN MENU", ["🚀 SCRAPER ENGINE", "🛠️ USER MANAGEMENT"], index=0, key="nav_main")
        else:
            st.warning(f"💎 Credits: **{user_balance}**")
            choice = "🚀 SCRAPER ENGINE"
        
        st.divider()
        if st.button("Logout", type="secondary", use_container_width=True):
            authenticator.logout('Logout', 'main')
            st.session_state.clear() # Clear session logic
            st.rerun()

    # ---------------------------
    # VIEW 1: USER MANAGEMENT (ADMIN ONLY)
    # ---------------------------
    if choice == "🛠️ USER MANAGEMENT" and current_user == "admin":
        st.markdown("<h1>🛠️ Admin Control Panel</h1>", unsafe_allow_html=True)
        
        # Live Monitoring Table
        st.subheader("📊 Live User Database")
        users_sql = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
        st.dataframe(pd.DataFrame(users_sql, columns=["Username", "Balance", "Status"]), use_container_width=True)

        col_create, col_action = st.columns(2)
        
        # Section: Create User
        with col_create:
            st.markdown("### ➕ Add New User")
            new_u = st.text_input("Username", key="new_u")
            new_n = st.text_input("Full Name", key="new_n")
            new_p = st.text_input("Password", type="password", key="new_p")
            
            if st.button("CREATE ACCOUNT", type="primary"):
                if new_u and new_p:
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    
                    config['credentials']['usernames'][new_u] = {'name': new_n, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    
                    run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (new_u, 5, 'active'))
                    st.success(f"User {new_u} created successfully!"); time.sleep(1); st.rerun()

        # Section: Manage User
        with col_action:
            st.markdown("### ⚙️ User Actions")
            db_users_list = [r[0] for r in users_sql if r[0] != 'admin']
            if db_users_list:
                target_user = st.selectbox("Select User", db_users_list, key="target_u")
                
                c_act_1, c_act_2 = st.columns(2)
                with c_act_1:
                    credits_to_add = st.number_input("Credits", min_value=1, value=100, key="cred_val")
                    if st.button("💰 Add Credits"):
                        add_credits(target_user, credits_to_add)
                        st.success("Credits added!"); time.sleep(0.5); st.rerun()
                
                with c_act_2:
                    _, u_curr_status = get_user_data(target_user)
                    btn_label = "🚫 Suspend" if u_curr_status == "active" else "✅ Activate"
                    if st.button(btn_label):
                        new_status = "suspended" if u_curr_status == "active" else "active"
                        run_query("UPDATE user_credits SET status=? WHERE username=?", (new_status, target_user))
                        st.rerun()
                
                st.divider()
                if st.button("🗑️ DELETE USER PERMANENTLY", type="secondary", use_container_width=True):
                    run_query("DELETE FROM user_credits WHERE username=?", (target_user,))
                    if target_user in config['credentials']['usernames']:
                        del config['credentials']['usernames'][target_user]
                        with open('config.yaml', 'w') as f: yaml.dump(config, f, default_flow_style=False)
                    st.error(f"User {target_user} deleted!"); time.sleep(1); st.rerun()

    # ---------------------------
    # VIEW 2: SCRAPER ENGINE (MAIN)
    # ---------------------------
    elif choice == "🚀 SCRAPER ENGINE":
        
        # Logo Display
        cm = st.columns([1, 6, 1])[1]
        with cm:
            if os.path.exists("chatscrape.png"):
                with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
                st.markdown(f'<div style="display:flex; justify-content:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
            
            # Progress Bar Component
            p_holder = st.empty()
            def update_bar(p, t):
                st.session_state.progress_val = p
                st.session_state.status_txt = t
                p_holder.markdown(f"""<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width:{p}%;"></div></div><div style='color:{orange_c};font-weight:bold;margin-top:10px;text-align:center;'>{t} {p}%</div></div>""", unsafe_allow_html=True)
            
            # Initial Bar State
            update_bar(st.session_state.progress_val, st.session_state.status_txt)

        # Mobile Floating Status
        if st.session_state.running:
            st.markdown(f'<div class="mobile-float">🚀 {st.session_state.status_txt} {st.session_state.progress_val}%</div>', unsafe_allow_html=True)

        # INPUT FORM (PERSISTENT)
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 3, 1.5, 1.5])
            
            # Linking inputs to session state to prevent reset
            niche = col1.text_input("🔍 Business Niche", value=st.session_state.niche_val, key="inp_niche")
            city = col2.text_input("🌍 Global City", value=st.session_state.city_val, key="inp_city")
            limit = col3.number_input("Target Leads", 1, 2000, value=st.session_state.limit_val, key="inp_limit")
            depth = col4.number_input("Search Depth", 5, 500, value=st.session_state.scroll_val, key="inp_depth")
            
            # Update state immediately
            st.session_state.niche_val = niche
            st.session_state.city_val = city
            st.session_state.limit_val = limit
            st.session_state.scroll_val = depth

            st.divider()
            
            # Filters Section (Responsive Grid)
            co, cb = st.columns([5, 3])
            with co:
                st.write("⚙️ Search Filters:")
                f_cols = st.columns(4) # 4 cols desktop, auto-wrap mobile
                w_phone = f_cols[0].checkbox("Phone", True, key="chk_phone")
                w_web = f_cols[1].checkbox("Web", True, key="chk_web")
                w_email = f_cols[2].checkbox("Email", False, key="chk_email") # Restored Email logic
                w_strict = f_cols[3].checkbox("Strict", True, key="chk_strict")
                
                # Additional row for filters
                f_cols2 = st.columns(4)
                w_no_site = f_cols2[0].checkbox("No Site", False, key="chk_nosite")

            with cb:
                st.write("") # Spacer
                b1, b2 = st.columns(2)
                if b1.button("START ENGINE", type="primary", use_container_width=True):
                    if niche and city and (user_balance > 0 or current_user == "admin"):
                        st.session_state.running = True
                        st.session_state.results_df = None # Clear previous
                        st.rerun()
                    else:
                        st.error("Check inputs or credits!")
                
                if b2.button("STOP", type="secondary", use_container_width=True):
                    st.session_state.running = False
                    st.session_state.status_txt = "STOPPED"
                    st.rerun()

        # TABS AREA
        t1, t2, t3 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE", "🤖 MARKETING KIT"])
        
        # --- TAB 1: LIVE SCRAPING ---
        with t1:
            table_spot = st.empty()
            
            # Display results if they exist (Persistence)
            if st.session_state.results_df is not None:
                st.divider()
                st.download_button("📥 Download CSV", 
                                   st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), 
                                   f"{niche}_{city}.csv", "text/csv", use_container_width=True)
                
                table_spot.dataframe(
                    st.session_state.results_df, 
                    use_container_width=True,
                    column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
                )

            # Scraper Logic
            if st.session_state.running:
                results = []
                # Log Session
                run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", 
                          (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
                s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
                
                driver = get_driver_fresh()
                if driver:
                    try:
                        update_bar(5, "INITIALIZING...")
                        search_url = f"https://www.google.com/maps/search/{quote(niche)}+in+{quote(city)}"
                        driver.get(search_url)
                        time.sleep(4)
                        
                        # Scrolling
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(depth):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1.5)
                            update_bar(10 + int((i/depth)*40), "SCROLLING...")
                        
                        # Extraction
                        items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]
                        links = [el.get_attribute("href") for el in items]
                        
                        for idx, link in enumerate(links):
                            # Credit Check
                            bal, _ = get_user_data(current_user)
                            if (bal <= 0 and current_user != "admin") or not st.session_state.running or len(results) >= limit: 
                                break
                            
                            update_bar(50 + int((idx/len(links))*50), f"SCRAPING {len(results)+1}/{limit}")
                            
                            try:
                                driver.get(link)
                                time.sleep(2)
                                
                                name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                adr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                
                                if w_strict and city.lower() not in adr.lower(): continue
                                
                                website = "N/A"
                                try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                
                                if w_no_site and website != "N/A": continue
                                
                                # WhatsApp & Phone
                                phone = "N/A"; wa_link = None
                                try:
                                    p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                    phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                    clean_num = re.sub(r'[^\d]', '', p_raw)
                                    wa_link = f"https://wa.me/{clean_num}"
                                except: pass
                                
                                # Email Extraction (If enabled)
                                email = "N/A"
                                if w_email and website != "N/A":
                                    email = fetch_email_from_site(driver, website)

                                row_data = {
                                    "Name": name, 
                                    "Phone": phone, 
                                    "WhatsApp": wa_link, 
                                    "Website": website, 
                                    "Address": adr,
                                    "Email": email
                                }
                                results.append(row_data)
                                
                                # Live Update
                                st.session_state.results_df = pd.DataFrame(results)
                                table_spot.dataframe(
                                    st.session_state.results_df, 
                                    use_container_width=True,
                                    column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
                                )
                                
                                # Save to DB & Deduct
                                deduct_credit(current_user)
                                run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                          (s_id, name, phone, website, adr, wa_link, email))
                                
                            except Exception as e:
                                continue
                                
                        update_bar(100, "COMPLETED")
                        
                    except Exception as e:
                        st.error(f"Runtime Error: {e}")
                    finally:
                        driver.quit()
                        st.session_state.running = False
                        st.session_state.status_txt = "FINISHED"
                        st.rerun() # Refresh to allow download

        # --- TAB 2: ARCHIVE ---
        with t2:
            st.subheader("📜 Database History")
            try:
                history_data = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
                for sess in history_data:
                    with st.expander(f"📦 {sess[2]} | {sess[1]}"):
                        leads_data = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={sess[0]}", is_select=True)
                        if leads_data:
                            df_h = pd.DataFrame(leads_data, columns=["Name", "Phone", "WhatsApp", "Website", "Email", "Address"])
                            st.dataframe(df_h, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                            st.download_button("📥 Export This Search", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{sess[0]}.csv", "text/csv")
                        else:
                            st.write("No leads found for this session.")
            except: st.write("Archive is empty.")

        # --- TAB 3: MARKETING KIT ---
        with t3:
            st.subheader("🤖 AI Outreach Generator")
            col_m1, col_m2 = st.columns(2)
            service_type = col_m1.selectbox("Service Offered", ["Web Design & Dev", "SEO Optimization", "Social Media Ads", "Google Maps Ranking"])
            tone = col_m2.selectbox("Tone", ["Professional", "Casual & Friendly", "Urgent"])
            
            if st.button("✨ Generate Script"):
                st.info("Here is your generated outreach script based on current niche:")
                script = f"""
                **Subject:** Upgrade {niche} business in {city} with {service_type}
                
                Hi there,
                
                I recently came across your business, **[Business Name]**, while looking for the best {niche} in {city}.
                
                I noticed that you could really benefit from {service_type} to get more customers...
                """
                st.code(script, language="markdown")

    st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

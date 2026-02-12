import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
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

# ==========================================
# 1. CONFIG & STATE INIT
# ==========================================
st.set_page_config(page_title="ChatScrap Elite", layout="wide", page_icon="🕷️")

# Initialize Session State (Persistence)
keys = [
    'niche_val', 'city_val', 'limit_val', 'depth_val',
    'results_df', 'running', 'progress_val', 'status_txt', 'lang'
]
for k in keys:
    if k not in st.session_state:
        st.session_state[k] = "English" if k == 'lang' else (None if k == 'results_df' else 0)
if 'niche_val' not in st.session_state: st.session_state.niche_val = ""
if 'city_val' not in st.session_state: st.session_state.city_val = ""
if 'limit_val' not in st.session_state: st.session_state.limit_val = 20
if 'depth_val' not in st.session_state: st.session_state.depth_val = 30

# Translations Dictionary (Multi-Language Sync Included)
TRANS = {
    "English": {
        "nav_engine": "🚀 SCRAPER ENGINE", "nav_admin": "🛠️ USER MANAGEMENT",
        "lbl_niche": "Business Niche", "lbl_city": "Target City",
        "lbl_limit": "Leads Target", "lbl_depth": "Scroll Depth",
        "btn_start": "START ENGINE", "btn_stop": "STOP",
        "tab_live": "⚡ LIVE DATA", "tab_arch": "📜 ARCHIVE", "tab_mkt": "🤖 MARKETING KIT",
        "sync_title": "📤 Export to Google Sheets",
        "sync_place": "Paste Google Sheet URL here...",
        "sync_btn": "🚀 Sync Now", "sync_ok": "✅ Synced Successfully!",
        "filters": "Search Filters"
    },
    "Français": {
        "nav_engine": "🚀 MOTEUR DE SCRAPING", "nav_admin": "🛠️ GESTION UTILISATEURS",
        "lbl_niche": "Niche d'activité", "lbl_city": "Ville Cible",
        "lbl_limit": "Objectif Leads", "lbl_depth": "Profondeur",
        "btn_start": "DÉMARRER", "btn_stop": "ARRÊTER",
        "tab_live": "⚡ RÉSULTATS", "tab_arch": "📜 ARCHIVE", "tab_mkt": "🤖 KIT MARKETING",
        "sync_title": "📤 Exporter vers Google Sheets",
        "sync_place": "Collez l'URL Google Sheet ici...",
        "sync_btn": "🚀 Synchroniser", "sync_ok": "✅ Synchronisé avec succès!",
        "filters": "Filtres de Recherche"
    },
    "العربية": {
        "nav_engine": "🚀 محرك البحث", "nav_admin": "🛠️ إدارة المستخدمين",
        "lbl_niche": "مجال العمل", "lbl_city": "المدينة",
        "lbl_limit": "عدد النتائج", "lbl_depth": "عمق البحث",
        "btn_start": "ابدأ البحث", "btn_stop": "توقف",
        "tab_live": "⚡ نتائج حية", "tab_arch": "📜 الأرشيف", "tab_mkt": "🤖 التسويق الذكي",
        "sync_title": "📤 تصدير إلى Google Sheets",
        "sync_place": "ضع رابط Google Sheet هنا...",
        "sync_btn": "🚀 إرسال الآن", "sync_ok": "✅ تم الإرسال بنجاح!",
        "filters": "فلاتر البحث"
    }
}

# ==========================================
# 2. AUTHENTICATION
# ==========================================
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

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except Exception as e: st.error(f"Auth Error: {e}")

if st.session_state["authentication_status"] is False:
    st.error('❌ Username/password incorrect'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('🔒 Please login'); st.stop()

# ==========================================
# 3. DATABASE & SYNC FUNCTIONS (FIXED)
# ==========================================
def run_query(query, params=(), is_select=False):
    # 🔥 FIXED: params defaults to empty tuple, is_select handles return logic
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
    else:
        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 5, 'active')) 
        return (5, 'active')

def deduct_credit(username):
    if username != "admin": 
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def add_credits(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        st.error("❌ Error: 'gcp_service_account' missing in Secrets."); return False
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
        st.error(f"Sync Failed: {e}"); return False

# ==========================================
# 4. SCRAPING ENGINE (FULL BEAST MODE)
# ==========================================
def get_driver_fresh():
    opts = Options()
    opts.add_argument("--headless"); opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    """Deep extraction of emails"""
    if not url or url == "N/A" or "google" in url: return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        driver.get(url); time.sleep(1.5)
        html = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)
        driver.close(); driver.switch_to.window(driver.window_handles[0])
        return emails[0] if emails else "N/A"
    except:
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==========================================
# 5. UI & CSS (ORANGE ELITE + MOBILE POPUP)
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
# 6. APP LAYOUT
# ==========================================
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

if user_st == 'suspended' and not is_admin: st.error("🚫 ACCOUNT SUSPENDED"); st.stop()

# Translation
T = TRANS[st.session_state.lang]

with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{user_bal}**")
    
    st.session_state.lang = st.selectbox("🌐 Language", ["English", "Français", "العربية"])
    st.divider()
    
    # Persistent Navigation
    menu_opts = [T['nav_engine']]
    if is_admin: menu_opts.append(T['nav_admin'])
    choice = st.radio("GO TO:", menu_opts, key="nav_main")
    
    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ---------------------------
# VIEW: USER MANAGEMENT (FULL)
# ---------------------------
if is_admin and choice == T['nav_admin']:
    st.markdown(f"<h1>{T['nav_admin']}</h1>", unsafe_allow_html=True)
    # 🔥 FIXED SQL Call
    users_sql = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
    st.dataframe(pd.DataFrame(users_sql, columns=["Username", "Balance", "Status"]), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### ➕ Register New")
        n_u = st.text_input("Username", key="n_u")
        n_n = st.text_input("Full Name", key="n_n")
        n_p = st.text_input("Password", type="password", key="n_p")
        if st.button("CREATE USER", type="primary"):
            if n_u and n_p:
                try: hpw = stauth.Hasher.hash(n_p)
                except: hpw = stauth.Hasher([n_p]).generate()[0]
                config['credentials']['usernames'][n_u] = {'name': n_n, 'password': hpw, 'email': f"{n_u}@mail.com"}
                with open('config.yaml', 'w') as f: yaml.dump(config, f)
                run_query("INSERT INTO user_credits VALUES (?, ?, ?)", (n_u, 5, 'active'))
                st.success("User Created!"); time.sleep(1); st.rerun()

    with c2:
        st.markdown("### ⚙️ Manage User")
        db_usrs = [r[0] for r in users_sql if r[0] != 'admin']
        if db_usrs:
            tgt = st.selectbox("Select User", db_usrs)
            amt = st.number_input("Credits", 1, 1000, 100)
            if st.button("💰 Add Credits"):
                add_credits(tgt, amt); st.success("Added!"); time.sleep(0.5); st.rerun()
            if st.button("🗑️ DELETE PERMANENTLY", type="secondary"):
                run_query("DELETE FROM user_credits WHERE username=?", (tgt,))
                if tgt in config['credentials']['usernames']:
                    del config['credentials']['usernames'][tgt]
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                st.warning("Deleted!"); st.rerun()

# ---------------------------
# VIEW: SCRAPER ENGINE (FULL)
# ---------------------------
elif choice == T['nav_engine']:
    
    # Mobile Popup
    if st.session_state.running:
        st.markdown(f"""
            <div class="mobile-popup">
                <span style="color:{orange_c};font-weight:bold;">🚀 {st.session_state.status_txt}</span><br>
                <div style="background:#333;height:6px;border-radius:3px;margin-top:5px;">
                    <div style="background:{orange_c};width:{st.session_state.progress_val}%;height:100%;border-radius:3px;"></div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    cm = st.columns([1, 6, 1])[1]
    with cm:
        if os.path.exists("chatscrape.png"):
            with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
            st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
        
        # Desktop Progress
        p_holder = st.empty()
        p_holder.markdown(f"""<div class="progress-container"><div class="progress-fill" style="width:{st.session_state.progress_val}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;'>{st.session_state.status_txt} {st.session_state.progress_val}%</div>""", unsafe_allow_html=True)

    # PERSISTENT INPUTS
    with st.container():
        c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
        st.session_state.niche_val = c1.text_input(f"🔍 {T['lbl_niche']}", st.session_state.niche_val)
        st.session_state.city_val = c2.text_input(f"🌍 {T['lbl_city']}", st.session_state.city_val)
        st.session_state.limit_val = c3.number_input(T['lbl_limit'], 1, 5000, st.session_state.limit_val)
        st.session_state.depth_val = c4.number_input(T['lbl_depth'], 5, 500, st.session_state.depth_val)

        st.divider()
        st.markdown(f"**⚙️ {T['filters']}**")
        f = st.columns(4)
        w_phone = f[0].checkbox(T['phone'], True)
        w_web = f[1].checkbox(T['web'], True)
        w_email = f[2].checkbox("Email (Slow)", False)
        w_nosite = f[3].checkbox("No Website", False)
        w_strict = st.checkbox("Strict City Match", True)

        b1, b2 = st.columns(2)
        if b1.button(T['btn_start'], type="primary", use_container_width=True):
            if st.session_state.niche_val and st.session_state.city_val:
                st.session_state.running = True; st.session_state.results_df = None; st.rerun()
        if b2.button(T['btn_stop'], type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

    # TABS (FULL)
    t1, t2, t3 = st.tabs([T['tab_live'], T['tab_arch'], T['tab_mkt']])
    
    with t1:
        table_spot = st.empty()
        
        # 🔥 MULTI-LANGUAGE SYNC SECTION
        if st.session_state.results_df is not None:
            st.divider()
            st.subheader(T['sync_title'])
            c_ex1, c_ex2 = st.columns([3, 1])
            gs_url = c_ex1.text_input(T['sync_place'], key="gs_url_main")
            if c_ex2.button(T['sync_btn']):
                if sync_to_gsheet(st.session_state.results_df, gs_url): st.success(T['sync_ok'])
            
            table_spot.dataframe(
                st.session_state.results_df, use_container_width=True,
                column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
            )

        # ENGINE CORE
        if st.session_state.running:
            results = []
            # 🔥 FIXED SQL Call
            run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{st.session_state.niche_val} - {st.session_state.city_val}", time.strftime("%Y-%m-%d %H:%M")))
            # 🔥 FIXED SQL Call: Explicitly pass is_select=True
            s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
            
            driver = get_driver_fresh()
            if driver:
                try:
                    st.session_state.status_txt = "INITIALIZING..."
                    st.session_state.progress_val = 5; st.rerun()
                    
                    target = f"https://www.google.com/maps/search/{quote(st.session_state.niche_val)}+in+{quote(st.session_state.city_val)}"
                    driver.get(target); time.sleep(4)
                    
                    # Scroll Loop
                    feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                    for i in range(st.session_state.depth_val):
                        if not st.session_state.running: break
                        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                        time.sleep(1.2)
                        st.session_state.progress_val = 10 + int((i/st.session_state.depth_val)*30)
                        st.session_state.status_txt = "SCROLLING..."
                        st.rerun() 
                    
                    # Extraction Loop
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:st.session_state.limit_val*2]
                    links = [el.get_attribute("href") for el in items]
                    
                    for idx, link in enumerate(links):
                        bal, _ = get_user_data(current_user)
                        if (bal <= 0 and not is_admin) or not st.session_state.running or len(results) >= st.session_state.limit_val: break
                        
                        st.session_state.status_txt = f"SCRAPING {len(results)+1}"
                        st.session_state.progress_val = 40 + int((idx/len(links))*60)
                        
                        try:
                            driver.get(link); time.sleep(1.5)
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                            
                            if w_strict and st.session_state.city_val.lower() not in addr.lower(): continue
                            
                            web = "N/A"
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: pass
                            if w_nosite and web != "N/A": continue
                            
                            # Email Extraction
                            email = "N/A"
                            if w_email and web != "N/A": email = fetch_email_deep(driver, web)
                            
                            # Phone & WA
                            phone = "N/A"; wa_link = None
                            try:
                                p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                                phone = re.sub(r'[^\d+\s]', '', p_raw).strip()
                                wa_link = f"https://wa.me/{re.sub(r'[^\d]', '', p_raw)}"
                            except: pass

                            results.append({"Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Address": addr, "Email": email})
                            
                            if not is_admin: deduct_credit(current_user)
                            st.session_state.results_df = pd.DataFrame(results)
                            table_spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                            run_query("INSERT INTO leads (session_id, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?)", (s_id, name, phone, web, addr, wa_link, email))
                        except: continue
                    
                    st.session_state.status_txt = "COMPLETED"; st.session_state.progress_val = 100
                finally: driver.quit(); st.session_state.running = False; st.rerun()

    with t2:
        try:
            # 🔥 FIXED SQL Call
            hists = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 20", is_select=True)
            for h in hists:
                with st.expander(f"📦 {h[2]} | {h[1]}"):
                    # 🔥 FIXED SQL Call
                    d = run_query(f"SELECT name, phone, whatsapp, website, email, address FROM leads WHERE session_id={h[0]}", is_select=True)
                    df_h = pd.DataFrame(d, columns=["Name", "Phone", "WhatsApp", "Website", "Email", "Address"])
                    st.dataframe(df_h, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                    st.download_button("📥 Export CSV", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{h[0]}.csv")
        except: st.info("No history found.")

    with t3:
        st.subheader(T['tab_mkt'])
        c_m1, c_m2 = st.columns(2)
        srv = c_m1.selectbox("Service", ["Web Design", "SEO", "Ads", "SMMA"])
        
        if st.button("✨ Generate Outreach Script"):
            msg = f"Subject: Proposal for {st.session_state.niche_val} in {st.session_state.city_val}\n\nHi,\nI noticed your business..."
            if st.session_state.lang == "Français": msg = "Bonjour,\nJ'ai remarqué votre entreprise..."
            if st.session_state.lang == "العربية": msg = "مرحباً،\nلقد لاحظت نشاطك التجاري..."
            st.text_area("Copy this message:", value=msg, height=200)

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

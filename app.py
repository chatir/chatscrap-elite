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
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. SYSTEM SETUP & PERSISTENCE
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Ultimate Beast", layout="wide", page_icon="🕷️")

# تهيئة الذاكرة لضمان عدم ضياع البيانات
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"

# ==============================================================================
# 2. SECURITY & AUTHENTICATION
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except:
    st.error("❌ Critical Error: 'config.yaml' missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is not True:
    st.info("Please login to access the Beast Mode."); st.stop()

# ==============================================================================
# 3. DATABASE ENGINE
# ==============================================================================
def run_query(query, params=(), is_select=False):
    try:
        with sqlite3.connect('scraper_beast_ultimate.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except: return [] if is_select else False

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, keyword TEXT, city TEXT, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')

init_db()

def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,))
    return (100, 'active')

def deduct_credit(username):
    if username != "admin": run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

# ==============================================================================
# 4. BEAST SCRAPER ENGINE
# ==============================================================================
def get_driver_beast():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        try:
            driver.get(url); time.sleep(2)
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", driver.page_source)
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            valid = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            return valid[0] if valid else "N/A"
        except:
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return "N/A"
    except: return "N/A"

# ==============================================================================
# 5. UI STYLING (CALIBRI FONT & ANIMATED DESIGN)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;800&display=swap');
    
    /* Calibri-like clean typography */
    html, body, [class*="css"], .stApp {{
        font-family: 'Open Sans', 'Segoe UI', Tahoma, sans-serif !important;
        background-color: #0f111a;
    }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; }}
    
    /* Branding */
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* Floating Progress for Mobile */
    .mobile-popup {{
        display: none; position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); border: 2px solid {orange_c};
        border-radius: 12px; padding: 12px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 30px rgba(255, 140, 0, 0.3);
    }}
    @media (max-width: 768px) {{ .mobile-popup {{ display: block; }} }}
    
    /* Stripes Animation */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ 
        height: 14px; background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; transition: width 0.4s ease; animation: stripes 1s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 50px 50px;}} }}
    
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; font-weight: 800 !important; font-size: 16px; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. APPLICATION LOGIC
# ==============================================================================
user = st.session_state["username"]
user_bal, user_st = get_user_data(user)
is_admin = user == "admin"

with st.sidebar:
    st.title("👤 Profile")
    st.write(f"Logged as: **{st.session_state['name']}**")
    if is_admin: st.success("💎 Credits: Unlimited ♾️")
    else: st.warning(f"💎 Credits: {user_bal}")
    
    if is_admin:
        with st.expander("🛠️ ADMIN DASHBOARD"):
            u_data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(u_data, columns=["User", "Bal", "Sts"]), hide_index=True)
            tgt = st.selectbox("Select User", [u[0] for u in u_data if u[0]!='admin'])
            if st.button("💰 Grant 100 Cr"):
                run_query("UPDATE user_credits SET balance=balance+100 WHERE username=?", (tgt,))
                st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# Layout
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    p_holder = st.empty()
    m_holder = st.empty()

def update_ui(prog, txt):
    st.session_state.progress_val = prog
    st.session_state.status_txt = txt
    p_holder.markdown(f"""<div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div><div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{txt} {prog}%</div>""", unsafe_allow_html=True)
    if st.session_state.running:
        m_holder.markdown(f"""<div class="mobile-popup"><span style="color:{orange_c};font-weight:bold;">🚀 {txt}</span><br><div style="background:#333;height:6px;border-radius:3px;margin-top:5px;"><div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div></div><small>{prog}%</small></div>""", unsafe_allow_html=True)

if not st.session_state.running: update_ui(0, "SYSTEM READY")

# Search UI
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kw_in = c1.text_input("🔍 Keywords (Ex: cafe, snack)", placeholder="cafe, restaurant")
    city_in = c2.text_input("🌍 Cities (Ex: Agadir, Casa)", placeholder="Agadir, Casablanca")
    limit_in = c3.number_input("Limit/City", 1, 5000, 20)
    depth_in = c4.number_input("Scroll Depth", 1, 100, 10)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ **PRECISION FILTERS:**")
        f = st.columns(4)
        w_phone = f[0].checkbox("Has Phone (Required)", True)
        w_web = f[1].checkbox("Has Website (Scrape)", False)
        w_email = f[2].checkbox("Extract Email (Deep)", False)
        w_nosite = f[3].checkbox("No Website Only", False)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        if b1.button("START ENGINE", type="primary", use_container_width=True):
            if kw_in and city_in: st.session_state.running = True; st.session_state.results_df = None; st.rerun()
        if b2.button("STOP", type="secondary", use_container_width=True):
            st.session_state.running = False; st.rerun()

# Results Tab
t1, t2 = st.tabs(["⚡ LIVE ENGINE", "📜 HISTORY"])

with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        # Dynamic Columns based on Checkboxes
        cols_to_show = ["Keyword", "City", "Name", "Phone", "WhatsApp", "Address"]
        if w_web: cols_to_show.append("Website")
        if w_email: cols_to_show.append("Email")
        
        final_df = st.session_state.results_df[cols_to_show]
        st.download_button("📥 Export CSV", final_df.to_csv(index=False).encode('utf-8-sig'), "leads_elite.csv")
        spot.dataframe(final_df, use_container_width=True, column_config={
            "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat Now")
        })

    if st.session_state.running:
        all_res = []
        kw_list = [k.strip() for k in kw_in.split(',') if k.strip()]
        ct_list = [c.strip() for c in city_in.split(',') if c.strip()]
        total_tasks = len(kw_list) * len(ct_list)
        curr_op = 0
        
        driver = get_driver_beast()
        if driver:
            try:
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        curr_op += 1
                        update_ui(int(((curr_op-1)/total_tasks)*100), f"SCANNING: {kw} in {city}")

                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                        driver.get(url); time.sleep(5)
                        try: driver.find_element(By.XPATH, "//button[contains(., 'Accept all')]").click(); time.sleep(2)
                        except: pass

                        # 🛠️ Robust Scroll
                        try:
                            feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            for _ in range(depth_in):
                                if not st.session_state.running: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                time.sleep(1.5)
                        except: pass
                        
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        seen_urls = set()
                        unique_els = []
                        for e in elements:
                            h = e.get_attribute("href")
                            if h and h not in seen_urls: seen_urls.add(h); unique_els.append(e)
                        
                        valid_count = 0
                        for el in unique_els:
                            if not st.session_state.running or valid_count >= limit_in: break
                            if not is_admin and get_user_data(user)[0] <= 0: break
                            
                            try:
                                driver.execute_script("arguments[0].click();", el); time.sleep(1.5)
                                name = "N/A"; phone = "N/A"; web = "N/A"; addr = "N/A"
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: pass
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: pass
                                try: phone = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label").replace("Phone:", "").strip()
                                except: pass
                                try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                
                                # 🔥 SMART WHATSAPP FILTER (Strict Morocco 06/07 Only)
                                wa_link = None
                                wa_num = re.sub(r'[^\d]', '', phone)
                                
                                # Check if it's Mobile (06/07) and NOT Fixe (05)
                                is_mobile = (wa_num.startswith('2126') or wa_num.startswith('2127') or wa_num.startswith('06') or wa_num.startswith('07'))
                                is_fixe = wa_num.startswith('2125') or (wa_num.startswith('05') and len(wa_num) <= 10)
                                
                                if is_mobile and not is_fixe:
                                    wa_link = f"https://wa.me/{wa_num}"

                                # 🔥 STRICT FILTER CHECK
                                if w_phone and (phone == "N/A" or phone == ""): continue
                                if w_web and (web == "N/A" or web == ""): continue
                                if w_nosite and web != "N/A": continue
                                
                                email = "N/A"
                                if w_email and web != "N/A": email = fetch_email_deep(driver, web)
                                
                                # Save
                                row = {"Keyword": kw, "City": city, "Name": name, "Phone": phone, "WhatsApp": wa_link, "Website": web, "Email": email, "Address": addr}
                                all_res.append(row); valid_count += 1
                                
                                if not is_admin: deduct_credit(user)
                                st.session_state.results_df = pd.DataFrame(all_res)
                                spot.dataframe(st.session_state.results_df[cols_to_show], use_container_width=True, column_config={
                                    "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="🟢 Chat Now")
                                })
                            except: continue
                update_ui(100, "COMPLETED SUCCESSFULLY ✅")
            finally: driver.quit(); st.session_state.running = False; st.rerun()

with t2:
    try:
        data = run_query("SELECT keyword, city, name, phone, website, email, address FROM leads ORDER BY id DESC LIMIT 100", is_select=True)
        st.dataframe(pd.DataFrame(data, columns=["KW", "City", "Name", "Phone", "Web", "Email", "Addr"]), use_container_width=True)
    except: pass

st.markdown('<div class="footer">Designed by Chatir ❤ | Elite Scraping Mastery</div>', unsafe_allow_html=True)

import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
import base64
import yaml
from yaml.loader import SafeLoader
from playwright.sync_api import sync_playwright
import streamlit_authenticator as stauth
from urllib.parse import quote

# ==============================================================================
# 1. GLOBAL CONFIGURATION & STATE
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎") #

if 'results_list' not in st.session_state: st.session_state.results_list = [] #
if 'running' not in st.session_state: st.session_state.running = False #
if 'paused' not in st.session_state: st.session_state.paused = False #
if 'task_index' not in st.session_state: st.session_state.task_index = 0 #
if 'progress' not in st.session_state: st.session_state.progress = 0 #
if 'current_sid' not in st.session_state: st.session_state.current_sid = None #

if 'active_kw' not in st.session_state: st.session_state.active_kw = "" #
if 'active_city' not in st.session_state: st.session_state.active_city = "" #

# ==============================================================================
# 2. DESIGN SYSTEM (WP LOGIN + STRIPY PROGRESS)
# ==============================================================================
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">', unsafe_allow_html=True) #

if st.session_state.get("authentication_status") is not True:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    [data-testid="stAppViewContainer"] { background-color: #0e1117 !important; }
    div[data-testid="stForm"] {
        background-color: #161922 !important; padding: 40px !important; border: 1px solid #FF8C00 !important;
        box-shadow: 0 10px 40px rgba(255,140,0,0.2) !important; border-radius: 12px !important; max-width: 400px !important; margin: auto !important;
    }
    .stButton > button { background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important; color: white !important; font-weight: 800 !important; height: 50px !important; border-radius: 8px !important; width: 100% !important; }
    [data-testid="stHeader"], [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True) #
else:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif !important; background-color: #0e1117; }
    .centered-logo { text-align: center; padding: 20px 0 40px 0; }
    .logo-img { width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.3)); }
    div[data-testid="stHorizontalBlock"]:has(button) { gap: 5px !important; }
    .stButton > button { width: 100% !important; height: 50px !important; font-weight: 700 !important; border-radius: 8px !important; color: white !important; }
    div[data-testid="column"]:nth-of-type(1) .stButton > button { background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important; }
    div[data-testid="column"]:nth-of-type(2) .stButton > button { background-color: #1F2937 !important; color: #E5E7EB !important; border: 1px solid #374151 !important; }
    div[data-testid="column"]:nth-of-type(3) .stButton > button { background: linear-gradient(135deg, #28a745 0%, #218838 100%) !important; }
    div[data-testid="column"]:nth-of-type(4) .stButton > button { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%) !important; }
    .prog-container { width: 100%; background: #111827; border-radius: 50px; padding: 4px; border: 1px solid #374151; margin: 25px 0; }
    .prog-bar-fill { height: 16px; background: repeating-linear-gradient(45deg, #FF8C00, #FF8C00 12px, #FF4500 12px, #FF4500 24px); border-radius: 20px; transition: width 0.3s ease-in-out; animation: stripes 1s linear infinite; }
    @keyframes stripes { 0% {background-position: 0 0;} 100% {background-position: 48px 48px;} }
    .wa-link { color: #25D366 !important; text-decoration: none !important; font-weight: bold; display: inline-flex; align-items: center; gap: 5px; }
    </style>
    """, unsafe_allow_html=True) #

# ==============================================================================
# 3. DATABASE
# ==============================================================================
DB_NAME = "chatscrap_elite_pro_v9.db" #

def init_db():
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)") #
        cursor.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, 
            keyword TEXT, city TEXT, country TEXT, name TEXT, phone TEXT, 
            website TEXT, email TEXT, address TEXT, whatsapp TEXT)""") #
        cursor.execute("CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')") #
        
        # SMART MIGRATION
        cols = [c[1] for c in cursor.execute("PRAGMA table_info(leads)").fetchall()]
        for col in ["rating", "social_media"]:
            if col not in cols: cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
        conn.commit()

init_db()

def get_user_data(username):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT balance, status FROM user_credits WHERE username=?", (username,)).fetchone() #
        if res: return res
        conn.execute("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,)) #
        conn.commit(); return (100, 'active')

# ==============================================================================
# 4. AUTHENTICATION & LOGIN
# ==============================================================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader) #
except: st.error("config.yaml missing"); st.stop()

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']) #

if st.session_state.get("authentication_status") is not True:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode() #
        st.markdown(f'<div style="text-align:center; padding-top: 100px; padding-bottom: 20px;"><img src="data:image/png;base64,{b64}" style="width:320px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.3));"></div>', unsafe_allow_html=True) #
    
    col1, col2, col3 = st.columns([1, 1.2, 1]) #
    with col2:
        try: authenticator.login() #
        except: pass
        if st.session_state["authentication_status"] is False: st.error("Wrong credentials")
        if st.session_state["authentication_status"] is None: st.info("🔒 Private Access Required")
        st.stop()

# ==============================================================================
# 5. SIDEBAR & ADMIN
# ==============================================================================
with st.sidebar:
    st.title("Profile Settings") #
    me = st.session_state["username"] #
    bal, sts = get_user_data(me) #
    if sts == 'suspended' and me != 'admin': st.error("Account Suspended"); st.stop()
    st.metric("Elite Balance", f"💎 {bal}" if me != 'admin' else "💎 Unlimited") #
    
    if me == 'admin':
        with st.expander("🛠️ Admin Panel"): #
            conn = sqlite3.connect(DB_NAME); u_df = pd.read_sql("SELECT * FROM user_credits", conn)
            st.dataframe(u_df, hide_index=True)
            target = st.selectbox("Select User", u_df['username'])
            c1, c2, c3 = st.columns(3)
            if c1.button("💰 +100"): conn.execute("UPDATE user_credits SET balance=balance+100 WHERE username=?", (target,)); conn.commit(); st.rerun()
            if c2.button("🚫 State"):
                curr = conn.execute("SELECT status FROM user_credits WHERE username=?", (target,)).fetchone()[0]
                conn.execute("UPDATE user_credits SET status=? WHERE username=?", ('suspended' if curr=='active' else 'active', target)); conn.commit(); st.rerun()
            if c3.button("🗑️ Del"): conn.execute("DELETE FROM user_credits WHERE username=?", (target,)); conn.commit(); st.rerun()

    st.divider() #
    if st.button("Logout"): authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# ==============================================================================
# 6. MAIN INTERFACE
# ==============================================================================
if os.path.exists("chatscrape.png"):
    with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode() #
    st.markdown(f'<div class="centered-logo"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True) #

with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1.5]) #
    kw_in = c1.text_input("Keywords", placeholder="e.g. hotel, cafe", key="kw_in_key") #
    city_in = c2.text_input("Cities", placeholder="e.g. Agadir, Rabat", key="city_in_key") #
    country_in = c3.selectbox("Country", ["Morocco", "France", "USA", "Spain", "UAE", "UK"], key="country_in_key") #
    limit_in = c4.number_input("Limit/City", 1, 1000, 20, key="limit_in_key") #

    st.divider() #
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1.2, 1.2]) #
    w_phone = f1.checkbox("Phone Only", True) #
    w_web = f2.checkbox("Website", False) #
    w_email = f3.checkbox("Deep Email", False) #
    w_social = f4.checkbox("🛡️ Social Media", False)
    w_global = f5.checkbox("🛡️ Global Dedupe", True)
    
    f6, f7, f8 = st.columns([1.5, 1.5, 2.5])
    w_neg = f6.checkbox("⭐ Negative Filter (<3.5)", False)
    depth_in = f8.slider("Scroll Depth", 1, 100, 10) #

    st.write("") #
    b_start, b_pause, b_cont, b_stop = st.columns(4) #
    
    with b_start:
        if st.button("Start Search", disabled=st.session_state.running): #
            if kw_in and city_in:
                st.session_state.active_kw, st.session_state.active_city = kw_in, city_in #
                st.session_state.running, st.session_state.paused = True, False #
                st.session_state.results_list, st.session_state.progress, st.session_state.task_index = [], 0, 0 #
                with sqlite3.connect(DB_NAME) as conn:
                    cur = conn.cursor(); cur.execute("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kw_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
                    st.session_state.current_sid = cur.lastrowid; conn.commit()
                st.rerun()

    with b_pause:
        if st.button("Pause", disabled=not st.session_state.running or st.session_state.paused): st.session_state.paused = True; st.rerun() #
    with b_cont:
        if st.button("Continue", disabled=not st.session_state.running or not st.session_state.paused): st.session_state.paused = False; st.rerun() #
    with b_stop:
        if st.button("Stop Search", disabled=not st.session_state.running): st.session_state.running, st.session_state.paused = False, False; st.rerun() #

# ==============================================================================
# 8. PLAYWRIGHT ENGINE (CLEAN & SELENIUM-FREE)
# ==============================================================================
def safe_math_rating(text):
    try:
        if not text: return 5.0
        nums = re.findall(r"(\d+\.\d+|\d+)", text)
        return float(nums[0]) if nums else 5.0
    except: return 5.0

def fetch_deep_site(context, url, find_socials, find_email):
    social, em = "N/A", "N/A"
    if not url or url == "N/A": return social, em
    try:
        page = context.new_page()
        page.goto(url, timeout=12000, wait_until="domcontentloaded")
        time.sleep(2); src = page.content().lower()
        if find_socials:
            patterns = [r'instagram\.com/[a-zA-Z0-9_.]+', r'facebook\.com/[a-zA-Z0-9_.]+', r'linkedin\.com/company/[a-zA-Z0-9_-]+']
            for p in patterns:
                m = re.findall(p, src); 
                if m: social = m[0]; break
        if find_email:
            em_m = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", src)
            em = list(set(em_m))[0] if em_m else "N/A"
        page.close()
    except: pass
    return social, em

tab_live, tab_archive, tab_tools = st.tabs(["⚡ Live Data", "📜 Archives", "🤖 Marketing"]) #

with tab_live:
    prog_spot, status_ui, table_ui, download_ui = st.empty(), st.empty(), st.empty(), st.empty() #
    prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True) #

    if st.session_state.results_list:
        df_live = pd.DataFrame(st.session_state.results_list) #
        table_ui.write(df_live.to_html(escape=False, index=False), unsafe_allow_html=True)
        download_ui.download_button(label="⬇️ Download CSV", data=df_live.to_csv(index=False).encode('utf-8'), file_name="leads.csv", mime="text/csv")

    if st.session_state.running and not st.session_state.paused:
        akws = [k.strip() for k in st.session_state.active_kw.split(',') if k.strip()] #
        acts = [c.strip() for c in st.session_state.active_city.split(',') if c.strip()] #
        all_tasks = [(c, k) for c in acts for k in akws] #
        
        if all_tasks:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                page = context.new_page()
                try:
                    total_est = len(all_tasks) * limit_in
                    for i, (city, kw) in enumerate(all_tasks):
                        if i < st.session_state.task_index: continue
                        if not st.session_state.running: break
                        base_progress = i * limit_in
                        status_ui.markdown(f"**Scanning:** `{kw}` in `{city}`... ({i+1}/{len(all_tasks)})")
                        page.goto(f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en&gl=ma", timeout=60000)
                        time.sleep(5)
                        for _ in range(depth_in): page.mouse.wheel(0, 5000); time.sleep(1)
                        
                        items = page.locator('a[href*="/maps/place/"]').all()
                        processed = 0
                        for item in items:
                            if processed >= limit_in or not st.session_state.running: break
                            try:
                                item.click(); time.sleep(3)
                                name = page.locator('h1.DUwDvf').first.inner_text()
                                phone = "N/A"
                                try: phone = page.locator('button[data-item-id*="phone:tel"]').first.get_attribute("aria-label").replace("Phone: ", "")
                                except: pass
                                
                                if w_phone and (phone == "N/A" or not phone): continue
                                if w_global:
                                    with sqlite3.connect(DB_NAME) as conn:
                                        if conn.execute("SELECT 1 FROM leads WHERE name=? AND phone=?", (name, phone)).fetchone(): continue

                                full_rev = "N/A"; rating_val = 5.0
                                try:
                                    rating_el = page.locator('span[aria-label*="stars"]').first
                                    full_rev = rating_el.get_attribute("aria-label") 
                                    rating_val = safe_math_rating(full_rev)
                                except: pass

                                if w_neg and rating_val >= 3.5: continue

                                st.session_state.progress = min(int(((base_progress + processed + 1) / total_est) * 100), 100)
                                prog_spot.markdown(f'<div class="prog-container"><div class="prog-bar-fill" style="width: {st.session_state.progress}%;"></div></div>', unsafe_allow_html=True) #

                                maps_web = "N/A"
                                try: maps_web = page.locator('a[data-item-id="authority"]').get_attribute("href")
                                except: pass
                                
                                final_web = maps_web; social_found = "N/A"
                                if any(x in str(maps_web).lower() for x in ["facebook.com", "instagram.com", "linkedin.com", "twitter.com"]):
                                    social_found = maps_web; final_web = "N/A"

                                email = "N/A"
                                if final_web != "N/A" and (w_social or w_email):
                                    s_crawl, em_crawl = fetch_deep_site(context, final_web, w_social, w_email)
                                    if social_found == "N/A": social_found = s_crawl
                                    email = em_crawl

                                wa = "N/A"; cp = re.sub(r'\D', '', phone)
                                if any(cp.startswith(x) for x in ['2126','2127','06','07']) and not (cp.startswith('2125') or cp.startswith('05')):
                                    wa = f'<a href="https://wa.me/{cp}" target="_blank" class="wa-link"><i class="fab fa-whatsapp"></i> Chat Now</a>' #
                                
                                row = {"Keyword":kw, "City":city, "Name":name, "Phone":phone, "WhatsApp":wa, 
                                       "Website": final_web if w_web else "N/A", "Email": email if w_email else "N/A",
                                       "Rating/Reviews": full_rev, "Social Media": social_found if w_social else "N/A"}
                                
                                with sqlite3.connect(DB_NAME) as conn:
                                    conn.execute("""INSERT INTO leads (session_id, keyword, city, country, name, phone, website, email, whatsapp, rating, social_media)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (st.session_state.current_sid, kw, city, country_in, name, phone, row["Website"], row["Email"], wa, full_rev, social_found))
                                    if me != 'admin': conn.execute("UPDATE user_credits SET balance=balance-1 WHERE username=?", (me,))
                                    conn.commit()
                                
                                st.session_state.results_list.append(row); table_ui.write(pd.DataFrame(st.session_state.results_list).to_html(escape=False, index=False), unsafe_allow_html=True)
                                processed += 1
                            except: continue
                        st.session_state.task_index += 1
                    if st.session_state.task_index >= len(all_tasks) and st.session_state.running:
                        st.success("🏁 Extraction Finished!"); st.session_state.running = False
                finally: browser.close()

# ==============================================================================
# 9. ARCHIVE & MARKETING (CLEANED)
# ==============================================================================
with tab_archive:
    st.subheader("Persistent History") #
    search_f = st.text_input("Filter History", placeholder="🔍 Search...")
    with sqlite3.connect(DB_NAME) as conn:
        df_s = pd.read_sql("SELECT * FROM sessions WHERE query LIKE ? ORDER BY id DESC LIMIT 30", conn, params=(f"%{search_f}%",))
    if not df_s.empty:
        for _, sess in df_s.iterrows():
            with st.expander(f"📦 {sess['date']} | {sess['query']}"):
                with sqlite3.connect(DB_NAME) as conn: df_l = pd.read_sql(f"SELECT * FROM leads WHERE session_id={sess['id']}", conn)
                if not df_l.empty:
                    st.write(df_l.drop(columns=['id', 'session_id']).to_html(escape=False, index=False), unsafe_allow_html=True)
                    st.download_button(label="⬇️ Export CSV", data=df_l.to_csv(index=False).encode('utf-8'), file_name=f"archive_{sess['id']}.csv", key=f"btn_{sess['id']}")

with tab_tools:
    st.subheader("🤖 Marketing Automation") #
    st.info("AI generated messaging tools based on extracted leads.") #

st.markdown('<div style="text-align:center;color:#666;padding:30px;">Designed by Chatir Elite Pro - Architect Edition V88 (Playwright)</div>', unsafe_allow_html=True) #

import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. CONFIG & STATE ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark' # Force Dark Mode

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'running' not in st.session_state: st.session_state.running = False

# --- 2. DATABASE ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, whatsapp TEXT)''')
    try: run_query("SELECT whatsapp FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN whatsapp TEXT")

init_db()

# --- 3. UTILS ---
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

# 🔥 SMART WHATSAPP FILTER
def clean_phone_for_wa(phone):
    if not phone or phone == "N/A": return None
    clean = re.sub(r'[^\d+]', '', phone)
    check_num = clean.replace(" ", "").replace("-", "")
    # Check for Moroccan Landlines (05...)
    if check_num.startswith("05") or check_num.startswith("+2125") or check_num.startswith("002125"):
        return None
    return f"https://wa.me/{clean}"

# 🔥 PHONE TEXT CLEANER (Displays only numbers)
def clean_phone_display(text):
    if not text: return "N/A"
    # Removes all letters, keeps digits, spaces, and +
    clean = re.sub(r'[^\d+\s]', '', text).strip()
    return clean

# --- 4. STYLING ---
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

    /* LOGO & BAR */
    .logo-container {{ display: flex; flex-direction: column; align-items: center; padding-bottom: 20px; }}
    .logo-img {{ width: 280px; filter: sepia(100%) saturate(500%) hue-rotate(-10deg) brightness(1.2); transition: 0.3s; margin-bottom: 15px; }}

    /* NEON PROGRESS BAR */
    .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
    .progress-container {{
        width: 100%; background-color: rgba(255, 140, 0, 0.1);
        border-radius: 50px; padding: 4px; 
        border: 1px solid {bar_color};
        box-shadow: 0 0 15px rgba(255, 140, 0, 0.2);
    }}
    .progress-fill {{
        height: 14px;
        background: repeating-linear-gradient(45deg, {bar_color}, {bar_color} 10px, #FF4500 10px, #FF4500 20px);
        border-radius: 20px; transition: width 0.4s ease;
        animation: move-stripes 1s linear infinite; box-shadow: 0 0 20px {bar_color};
    }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    .progress-text {{ font-weight: 900; color: {bar_color}; margin-top: 10px; font-size: 1rem; letter-spacing: 2px; text-transform: uppercase; text-shadow: 0 0 10px rgba(255, 140, 0, 0.5); }}

    /* BUTTONS */
    div.stButton > button {{
        border: none !important; border-radius: 12px !important;
        font-weight: 900 !important; font-size: 15px !important;
        height: 3.2em !important; text-transform: uppercase !important;
        color: #FFFFFF !important; box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    }}
    div.stButton > button[kind="primary"] {{ background: {start_grad} !important; width: 100% !important; }}
    div.stButton > button[kind="secondary"] {{ background: {stop_grad} !important; width: 100% !important; }}

    /* INPUTS */
    .stTextInput input, .stNumberInput input {{ background-color: {input_bg} !important; color: {text_color} !important; border: 1px solid rgba(128,128,128,0.2) !important; border-radius: 10px !important; }}

    /* METRICS */
    div[data-testid="metric-container"] {{ background-color: {card_bg}; border: 1px solid rgba(255, 140, 0, 0.1); padding: 15px; border-radius: 12px; }}
    div[data-testid="metric-container"] label {{ opacity: 0.7; }}
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {{ color: {bar_color} !important; }}

    /* TOOLTIP STYLE */
    .stTooltipIcon {{ color: {bar_color} !important; }}

    /* FOOTER */
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: {footer_bg}; color: {footer_text}; text-align: center; padding: 15px; font-weight: bold; border-top: 1px solid rgba(128,128,128,0.1); z-index: 9999; font-size: 14px; }}
    </style>
""", unsafe_allow_html=True)

# --- 5. HEADER ---
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

# --- 6. MAIN FORM ---
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    with c1: niche = st.text_input("🔍 Business Niche", "")
    with c2: city = st.text_input("🌍 Global City", "")
    with c3: limit = st.number_input("Target Leads", 1, 2000, 20)
    with c4: scrolls = st.number_input("Search Depth", 5, 500, 30)
    
    st.markdown("<br>", unsafe_allow_html=True)
    col_opt, col_btn = st.columns([5, 3])
    with col_opt:
        st.write("⚙️ Filters:")
        opts = st.columns(5)
        w_phone = opts[0].checkbox("Phone", True)
        w_web = opts[1].checkbox("Web", True)
        w_email = opts[2].checkbox("Email", False)
        
        # 🔥 ADDED TOOLTIPS HERE
        opts[3].checkbox(
            "Strict", 
            value=True, 
            help="Enables Exact Match: Only saves leads where the City address matches your input exactly."
        )
        opts[4].checkbox(
            "Sync", 
            value=True, 
            help="High Precision Mode: Slows down scraping slightly to ensure all data (like Emails) is fully loaded."
        )

    with col_btn:
        st.write("")
        b1, b2 = st.columns([2, 1.5])
        with b1:
            if st.button("START ENGINE", type="primary", use_container_width=True): 
                if not niche or not city:
                    st.error("Please enter a Niche and City!")
                else:
                    st.session_state.running = True; st.session_state.progress_val = 0; st.session_state.status_txt = "STARTING..."; st.session_state.results_df = None; st.rerun()
        with b2:
            if st.button("STOP", type="secondary", use_container_width=True): 
                st.session_state.running = False; st.session_state.status_txt = "STOPPED"; st.rerun()

# --- 7. LOGIC & DASHBOARD ---
t1, t2 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE"])

with t1:
    metrics_placeholder = st.empty()
    table_placeholder = st.empty()

    with metrics_placeholder.container():
        m1, m2, m3, m4 = st.columns(4)
        if st.session_state.results_df is not None:
            df = st.session_state.results_df
            m1.metric("Total Leads", len(df), "🎯 Scraped")
            m2.metric("Valid Phones", len(df[df['WhatsApp'].notnull()]), "📱 WhatsApp")
            m3.metric("Websites", len(df[df['Website'] != "N/A"]), "🌐 Digital")
            m4.metric("Emails", len(df[df['Email'] != "N/A"]) if 'Email' in df.columns else 0, "📧 B2B")
        else:
            m1.metric("Total Leads", 0); m2.metric("Valid Phones", 0); m3.metric("Websites", 0); m4.metric("Emails", 0)

    if st.session_state.results_df is not None:
        table_placeholder.dataframe(
            st.session_state.results_df, use_container_width=True,
            column_config={
                "WhatsApp": st.column_config.LinkColumn("Fast Action", display_text="Chat 💬"),
                "Website": st.column_config.LinkColumn("Site"),
            }
        )

    if st.session_state.running:
        results = [] 
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{niche} in {city}", time.strftime("%Y-%m-%d %H:%M")))
        s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        
        options = Options(); options.add_argument("--headless")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        try:
            update_bar(5, "INITIALIZING...")
            driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}")
            time.sleep(4)
            
            scroll_div = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            for i in range(scrolls):
                if not st.session_state.running: break
                driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scroll_div)
                time.sleep(1)
                prog = 10 + int((i / scrolls) * 40)
                update_bar(prog, "SCROLLING...")
            
            items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit*2]
            links = [el.get_attribute("href") for el in items]
            
            total = len(links) if links else 1
            for idx, link in enumerate(links):
                if not st.session_state.running or len(results) >= limit: break
                
                prog = 50 + int((idx / total) * 50)
                update_bar(prog, f"EXTRACTING {len(results)+1}/{limit}")
                driver.get(link)
                time.sleep(1.5)
                try:
                    name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                    if any(d['Name'] == name for d in results): continue
                    
                    try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                    except: addr = "N/A"
                    row = {"Name": name, "Address": addr}
                    if w_phone:
                        try: 
                            p_raw = driver.find_element(By.XPATH, '//*[contains(@data-item-id, "phone:tel")]').get_attribute("aria-label")
                            # 🔥 CLEAN DISPLAY (Shows only numbers)
                            row["Phone"] = clean_phone_display(p_raw)
                            # 🔥 SMART WA LINK (Based on raw number)
                            row["WhatsApp"] = clean_phone_for_wa(p_raw) 
                        except: row["Phone"] = "N/A"; row["WhatsApp"] = None
                    if w_web:
                        try: row["Website"] = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                        except: row["Website"] = "N/A"
                    if w_email: row["Email"] = fetch_email(driver, row.get("Website", "N/A"))

                    results.append(row)
                    st.session_state.results_df = pd.DataFrame(results)
                    
                    with metrics_placeholder.container():
                        m1, m2, m3, m4 = st.columns(4)
                        df = st.session_state.results_df
                        m1.metric("Total Leads", len(df), "🎯 Scraped")
                        m2.metric("Valid Phones", len(df[df['WhatsApp'].notnull()]), "📱 WhatsApp")
                        m3.metric("Websites", len(df[df['Website'] != "N/A"]), "🌐 Digital")
                        m4.metric("Emails", len(df[df['Email'] != "N/A"]) if 'Email' in df.columns else 0, "📧 B2B")

                    table_placeholder.dataframe(
                        st.session_state.results_df, use_container_width=True,
                        column_config={
                            "WhatsApp": st.column_config.LinkColumn("Fast Action", display_text="Chat 💬"),
                            "Website": st.column_config.LinkColumn("Site"),
                        }
                    )
                    
                    run_query("INSERT INTO leads (session_id, name, phone, website, email, address, whatsapp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (s_id, name, row.get("Phone", "N/A"), row.get("Website", "N/A"), row.get("Email", "N/A"), addr, row.get("WhatsApp", "")))
                except: continue
            
            update_bar(100, "COMPLETED")
        finally:
            driver.quit(); st.session_state.running = False

with t2:
    sessions = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
    for sid, q, d in sessions:
        with st.expander(f"📦 {d} | Search: {q}"):
            data = run_query(f"SELECT name, phone, website, email, address, whatsapp FROM leads WHERE session_id={sid}", is_select=True)
            df = pd.DataFrame(data, columns=["Name", "Phone", "Website", "Email", "Address", "WhatsApp"])
            st.dataframe(df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Fast Action", display_text="Chat 💬")})
            st.download_button("Export CSV", df.to_csv(index=False).encode('utf-8-sig'), f"leads_{sid}.csv", key=f"dl_{sid}")

st.markdown(f'<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)
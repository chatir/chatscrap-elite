import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
import base64
import yaml
import shutil
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import quote

# ==============================================================================
# 1. GLOBAL CONFIGURATION & STATE (RESTORING APP 19 LOGIC)
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Pro", layout="wide", page_icon="💎")

if 'results_list' not in st.session_state: st.session_state.results_list = []
if 'running' not in st.session_state: st.session_state.running = False
if 'paused' not in st.session_state: st.session_state.paused = False
if 'task_index' not in st.session_state: st.session_state.task_index = 0
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'current_sid' not in st.session_state: st.session_state.current_sid = None

if 'active_kw' not in st.session_state: st.session_state.active_kw = ""
if 'active_city' not in st.session_state: st.session_state.active_city = ""

# ==============================================================================
# 2. DATABASE SYSTEM (FULL SCHEMA)
# ==============================================================================
DB_NAME = "google_maps_leads_elite_pro.sqlite"

def run_query(query, params=(), is_select=False):
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, date TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        session_id INTEGER, 
        name TEXT, 
        phone TEXT, 
        website TEXT, 
        email TEXT, 
        address TEXT, 
        whatsapp TEXT, 
        rating TEXT, 
        reviews TEXT, 
        category TEXT, 
        keyword TEXT
    )''')
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER, status TEXT DEFAULT 'active')''')

init_db()

def get_user_info(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    else:
        run_query("INSERT INTO user_credits (username, balance, status) VALUES (?, ?, ?)", (username, 100, 'active')) 
        return (100, 'active')

# ==============================================================================
# 3. ELITE STYLING (YOUR ORIGINAL CSS)
# ==============================================================================
bg_color = "#0f111a"
card_bg = "#1a1f2e"
text_color = "#FFFFFF"
bar_color = "#FF8C00" 

st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg_color}; color: {text_color}; }}
    .stTextInput>div>div>input {{ background-color: {card_bg}; color: white; border: 1px solid #333; }}
    .stTextArea>div>div>textarea {{ background-color: {card_bg}; color: white; border: 1px solid #333; }}
    .logo-container {{ display: flex; flex-direction: column; align-items: center; margin-bottom: 20px; }}
    .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {bar_color}; }}
    .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {bar_color}, {bar_color} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; animation: move-stripes 1s linear infinite; }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important; color: white !important; border: none; font-weight: bold; width: 100%; }}
    div.stButton > button[kind="secondary"] {{ background: #333 !important; color: white !important; border: none; width: 100%; }}
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; text-align: center; padding: 10px; color: #888; font-size: 12px; z-index: 999; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. SERVER-COMPATIBLE DRIVER (THE ONLY FIX)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # مسارات السيرفر المضمونة
    options.binary_location = "/usr/bin/chromium"
    try:
        service = Service(executable_path="/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except:
        return None

# ==============================================================================
# 5. AUTHENTICATION & UTILS
# ==============================================================================
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])
authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please login'); st.stop()

current_user = st.session_state["username"]
user_info = get_user_info(current_user)
user_bal = user_info[0]

# Helper Functions
def get_image_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f: return base64.b64encode(f.read()).decode()
    return None

def clean_phone(text):
    if not text: return "N/A"
    clean = re.sub(r'[^\d+\s]', '', text).strip()
    return clean

def get_whatsapp_link(phone):
    if not phone or phone == "N/A": return None
    clean = re.sub(r'[^\d]', '', phone)
    if clean.startswith("212") or (clean.startswith("0") and len(clean)==10):
        return f"https://wa.me/{clean}"
    return None

# ==============================================================================
# 6. MAIN APPLICATION LOGIC (THE MONSTER ENGINE)
# ==============================================================================
with st.sidebar:
    st.title("💎 Elite Pro")
    st.info(f"👤 {st.session_state['name']}\n\n💰 Credits: {user_bal}")
    
    if current_user == 'admin':
        st.divider()
        st.subheader("🛠️ Admin")
        target = st.text_input("User")
        amount = st.number_input("Credits", 10, 5000, 100)
        if st.button("Top Up"):
            run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, target))
            st.success("Done!"); time.sleep(1); st.rerun()
            
    st.divider()
    authenticator.logout('Logout', 'main')

# Logo Header
c1, c2, c3 = st.columns([1,2,1])
with c2:
    logo_b64 = get_image_base64("chatscrape.png")
    if logo_b64: st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{logo_b64}" width="300"></div>', unsafe_allow_html=True)

# Tabs System
tab_live, tab_archive, tab_tools = st.tabs(["⚡ LIVE SCRAPER", "📦 ARCHIVE", "🛠️ AI TOOLS"])

with tab_live:
    # Inputs
    col_k, col_c = st.columns(2)
    keywords_input = col_k.text_area("🔍 Keywords (One per line)", "Cafe\nGym\nDentist", height=100)
    cities_input = col_c.text_area("🌍 Cities (One per line)", "Agadir\nCasablanca\nMarrakech", height=100)
    
    col_set1, col_set2, col_set3 = st.columns(3)
    limit = col_set1.number_input("Target per Task", 1, 1000, 20)
    scrolls = col_set2.number_input("Scroll Depth", 1, 200, 10)
    
    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
    
    if col_btn1.button("🚀 START MONSTER ENGINE", type="primary"):
        if not keywords_input or not cities_input:
            st.error("Please enter keywords and cities!")
        elif user_bal <= 0:
            st.error("Insufficient Credits!")
        else:
            st.session_state.running = True
            st.session_state.paused = False
            st.session_state.results_list = []
            st.session_state.task_index = 0
            st.rerun()
            
    if col_btn2.button("⏸️ PAUSE"):
        st.session_state.paused = True
        st.rerun()
        
    if col_btn3.button("⏹️ STOP"):
        st.session_state.running = False
        st.rerun()

    # Progress UI
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    table_placeholder = st.empty()

    if st.session_state.results_list:
        df_res = pd.DataFrame(st.session_state.results_list)
        table_placeholder.dataframe(df_res, use_container_width=True)

    # --- THE CORE ENGINE LOOP ---
    if st.session_state.running and not st.session_state.paused:
        driver = get_driver()
        if driver:
            try:
                kws = [k.strip() for k in keywords_input.split('\n') if k.strip()]
                cts = [c.strip() for c in cities_input.split('\n') if c.strip()]
                tasks = [(k, c) for k in kws for c in cts]
                
                if st.session_state.current_sid is None:
                    run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", 
                              (f"Batch: {len(tasks)} Tasks", time.strftime("%Y-%m-%d %H:%M")))
                    st.session_state.current_sid = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]

                total_tasks = len(tasks)
                
                # Resume from task index
                for i in range(st.session_state.task_index, total_tasks):
                    if not st.session_state.running or st.session_state.paused:
                        st.session_state.task_index = i
                        break
                    
                    kw, city = tasks[i]
                    st.session_state.active_kw = kw
                    st.session_state.active_city = city
                    
                    # Update Progress
                    pct = int((i / total_tasks) * 100)
                    progress_placeholder.markdown(f'<div class="progress-container"><div class="progress-fill" style="width: {pct}%;"></div></div>', unsafe_allow_html=True)
                    status_placeholder.info(f"🔄 Processing Task {i+1}/{total_tasks}: **{kw}** in **{city}**")
                    
                    # Search
                    search_query = quote(f"{kw} in {city}")
                    driver.get(f"https://www.google.com/maps/search/{search_query}")
                    time.sleep(4)
                    
                    # Scroll
                    try:
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(scrolls):
                            if not st.session_state.running: break
                            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                            time.sleep(1)
                    except: pass
                    
                    # Extract
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit]
                    
                    for idx, item in enumerate(items):
                        if not st.session_state.running: break
                        try:
                            # Quick Extraction Strategy (No Click if possible for speed)
                            name = item.get_attribute("aria-label")
                            link = item.get_attribute("href")
                            
                            # Deep Extraction (Visit Link)
                            driver.execute_script("window.open('');")
                            driver.switch_to.window(driver.window_handles[-1])
                            driver.get(link)
                            time.sleep(1.5)
                            
                            try: name_real = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            except: name_real = name
                            
                            try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                            except: addr = "N/A"
                            
                            try: website = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: website = "N/A"
                            
                            try: phone_raw = driver.find_element(By.CSS_SELECTOR, 'button[data-item-id*="phone:tel"]').get_attribute("aria-label")
                            except: phone_raw = "N/A"
                            
                            try: rating = driver.find_element(By.CSS_SELECTOR, 'div.F7nice span span[aria-hidden="true"]').text
                            except: rating = "N/A"
                            
                            try: reviews = driver.find_element(By.CSS_SELECTOR, 'div.F7nice span[aria-label*="reviews"]').get_attribute("aria-label")
                            except: reviews = "N/A"
                            
                            try: category = driver.find_element(By.CSS_SELECTOR, 'button.DkEaL').text
                            except: category = "N/A"
                            
                            email = "N/A" # (Optional: Add Email Extraction Function here if needed)
                            
                            clean_ph = clean_phone(phone_raw)
                            wa_link = get_whatsapp_link(clean_ph)
                            
                            row = {
                                "Name": name_real, "Phone": clean_ph, "WhatsApp": wa_link,
                                "Website": website, "Address": addr, "Rating": rating,
                                "Reviews": reviews, "Category": category, "Keyword": kw, "City": city
                            }
                            
                            st.session_state.results_list.append(row)
                            
                            # Save & Deduct
                            run_query("""INSERT INTO leads 
                                (session_id, name, phone, website, email, address, whatsapp, rating, reviews, category, keyword) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                                (st.session_state.current_sid, name_real, clean_ph, website, email, addr, wa_link, rating, reviews, category, kw))
                            
                            run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (current_user,))
                            
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            
                        except: 
                            if len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(driver.window_handles[0])
                            continue
                    
                    # Update Table Live
                    table_placeholder.dataframe(pd.DataFrame(st.session_state.results_list), use_container_width=True)
                
                status_placeholder.success("✅ Sequence Completed!")
                st.session_state.running = False
                
            except Exception as e:
                st.error(f"Engine Error: {e}")
                st.session_state.running = False
            finally:
                driver.quit()
        else:
            st.error("❌ Driver Failed to Init (Server Issue)")

with tab_archive:
    st.subheader("📦 Extraction History")
    search_f = st.text_input("Filter sessions...")
    
    # جلب الجلسات
    sessions_data = run_query("SELECT * FROM sessions ORDER BY id DESC", is_select=True)
    if sessions_data:
        for sid, q, d in sessions_data:
            if search_f and search_f.lower() not in q.lower(): continue
            with st.expander(f"📅 {d} | {q}"):
                leads_data = run_query(f"SELECT * FROM leads WHERE session_id={sid}", is_select=True)
                if leads_data:
                    df = pd.DataFrame(leads_data, columns=['ID', 'SID', 'Name', 'Phone', 'Website', 'Email', 'Address', 'WhatsApp', 'Rating', 'Reviews', 'Category', 'Keyword'])
                    st.dataframe(df.drop(columns=['ID', 'SID']), use_container_width=True)
                    st.download_button("⬇️ Export CSV", df.to_csv(index=False).encode('utf-8'), f"leads_{sid}.csv")
                else:
                    st.info("No leads in this session.")

with tab_tools:
    st.subheader("🤖 AI Personalized Messaging")
    st.info("Select a lead from Archive to generate messages.")
    # (Here you can add your AI logic from app 19 if present)

st.markdown('<div class="footer">ChatScrap Elite Pro © 2026 | Powered by Chatir</div>', unsafe_allow_html=True)

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

# --- 1. ELITE CONFIG & STYLE (الديزاين الأصلي v65) ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark'

bg_color = "#0f111a"
card_bg = "#1a1f2e"
text_color = "#FFFFFF"
start_grad = "linear-gradient(135deg, #FF8C00 0%, #FF4500 100%)" 
bar_color = "#FF8C00" 
input_bg = "#1a1f2e"

st.markdown(f"""
    <style>
    .block-container {{ padding-top: 2rem !important; }}
    .stApp {{ background-color: {bg_color}; }}
    .stApp p, .stApp label, h1, h2, h3, .progress-text {{ color: {text_color} !important; font-family: 'Segoe UI', sans-serif; }}
    .logo-container {{ display: flex; flex-direction: column; align-items: center; padding-bottom: 20px; }}
    .progress-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto 30px auto; text-align: center; }}
    .progress-container {{ width: 100%; background-color: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {bar_color}; }}
    .progress-fill {{ height: 14px; background: repeating-linear-gradient(45deg, {bar_color}, {bar_color} 10px, #FF4500 10px, #FF4500 20px); border-radius: 20px; transition: width 0.4s ease; animation: move-stripes 1s linear infinite; }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    .progress-text {{ font-weight: 900; color: {bar_color}; margin-top: 10px; font-size: 1rem; }}
    div.stButton > button {{ border: none !important; border-radius: 12px !important; font-weight: 900 !important; background: {start_grad} !important; color: white !important; height: 3.2em !important; width: 100% !important; }}
    .stTextInput input, .stNumberInput input {{ background-color: {input_bg} !important; color: {text_color} !important; border-radius: 10px !important; }}
    </style>
""", unsafe_allow_html=True)

# --- 2. DRIVER SYSTEM (التعديل الوحيد لضمان العمل) ---
@st.cache_resource(show_spinner=False)
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # البحث الأوتوماتيكي عن مسارات السيرفر
    chrome_bin = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
    options.binary_location = chrome_bin
    
    driver_bin = shutil.which("chromedriver") or shutil.which("chromium-driver") or "/usr/bin/chromedriver"
    
    try:
        service = Service(executable_path=driver_bin)
        return webdriver.Chrome(service=service, options=options)
    except:
        try:
            return webdriver.Chrome(options=options)
        except Exception as e:
            st.error(f"Driver Error: {e}")
            return None

# --- 3. DATABASE & LOGIC ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_pro.db', timeout=30) as conn:
        curr = conn.cursor(); curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

# --- 4. AUTHENTICATION ---
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
    authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])
    authenticator.login()
except:
    st.warning("Config error")

if st.session_state.get("authentication_status"):
    
    if 'running' not in st.session_state: st.session_state.running = False
    if 'results_df' not in st.session_state: st.session_state.results_df = None

    # Logo
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f:
            img = base64.b64encode(f.read()).decode()
            st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{img}" width="280"></div>', unsafe_allow_html=True)

    # Form
    with st.container():
        c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
        niche = c1.text_input("🔍 Niche")
        city_in = c2.text_input("🌍 City")
        limit = c3.number_input("Target", 1, 1000, 20)
        scrolls = c4.number_input("Depth", 1, 100, 10)

        if st.button("START ENGINE", type="primary"):
            if niche and city_in:
                st.session_state.running = True
                st.session_state.results_df = None
                st.rerun()

    prog_place = st.empty()

    if st.session_state.results_df is not None:
        st.dataframe(st.session_state.results_df, use_container_width=True)

    # --- 5. SCRAPER ENGINE ---
    if st.session_state.running:
        driver = get_driver()
        if driver:
            try:
                results = []
                prog_place.markdown(f'<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: 10%;"></div></div><div class="progress-text">STARTING SEARCH...</div></div>', unsafe_allow_html=True)
                
                driver.get(f"https://www.google.com/maps/search/{niche}+in+{city_in}")
                time.sleep(5)
                
                # Scroll
                try:
                    feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                    for _ in range(scrolls):
                        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', feed)
                        time.sleep(1)
                except: pass
                
                items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit]
                links = [i.get_attribute("href") for i in items]
                
                for idx, link in enumerate(links):
                    if not st.session_state.running: break
                    pct = int(((idx+1)/len(links))*100)
                    prog_place.markdown(f'<div class="progress-wrapper"><div class="progress-container"><div class="progress-fill" style="width: {pct}%;"></div></div><div class="progress-text">EXTRACTING {idx+1}/{len(links)}</div></div>', unsafe_allow_html=True)
                    
                    driver.get(link); time.sleep(2)
                    try:
                        name = driver.find_element(By.CSS_SELECTOR, "h1").text
                        try: phone = driver.find_element(By.CSS_SELECTOR, '[data-item-id*="phone"]').get_attribute("aria-label")
                        except: phone = "N/A"
                        try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                        except: web = "N/A"
                        
                        results.append({"Name": name, "Phone": phone, "Website": web})
                        st.session_state.results_df = pd.DataFrame(results)
                    except: continue
                
                prog_place.success("✅ Completed!")
            finally:
                driver.quit()
                st.session_state.running = False
        else:
            st.error("❌ Driver Initialization Failed. Please check logs.")

st.markdown('<div style="text-align:center; padding:20px; opacity:0.5;">Chatir Elite Worldwide Lead Generation</div>', unsafe_allow_html=True)

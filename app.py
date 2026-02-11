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

# --- 1. CONFIG & STYLE (THE ORIGINAL ELITE) ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")
st.session_state.theme = 'Dark'

bg_color = "#0f111a"
card_bg = "#1a1f2e"
text_color = "#FFFFFF"
bar_color = "#FF8C00" 
input_bg = "#1a1f2e"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg_color}; }}
    .stApp p, .stApp label, h1, h2, h3 {{ color: {text_color} !important; font-family: 'Segoe UI', sans-serif; }}
    div.stButton > button {{ border: none !important; border-radius: 12px !important; font-weight: 900 !important; height: 3em !important; background: linear-gradient(135deg, #FF8C00 0%, #FF4500 100%) !important; color: white !important; }}
    .stTextInput input, .stNumberInput input {{ background-color: {input_bg} !important; color: {text_color} !important; border-radius: 10px !important; }}
    </style>
""", unsafe_allow_html=True)

# --- 2. THE SIMPLE DRIVER (DIRECT PATH) ---
@st.cache_resource
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # هنا التعديل الوحيد: كنقولو ليه خود كروم ديال السيرفر نيشان
    # بلا فلسفة بلا بحث
    options.binary_location = "/usr/bin/chromium"
    
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        st.error(f"Driver Error: {e}")
        return None

# --- 3. DATABASE ---
def run_query(query, params=(), is_select=False):
    with sqlite3.connect('scraper_simple.db', timeout=30) as conn:
        curr = conn.cursor()
        curr.execute(query, params)
        if is_select: return curr.fetchall()
        conn.commit()

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS leads (name TEXT, phone TEXT, website TEXT, email TEXT, address TEXT, city TEXT)''')
    run_query('''CREATE TABLE IF NOT EXISTS user_credits (username TEXT PRIMARY KEY, balance INTEGER)''')

init_db()

# --- 4. AUTHENTICATION ---
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
    authenticator = stauth.Authenticate(config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days'])
    authenticator.login()
except: st.warning("Login Skipped (Config Error)")

if st.session_state.get("authentication_status") is False: st.stop()

# --- 5. MAIN APP (THE ORIGINAL LOGIC) ---
c_spacer, c_main, c_spacer2 = st.columns([1, 6, 1])
with c_main:
    # Logo Logic
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: 
            img = base64.b64encode(f.read()).decode()
            st.markdown(f'<div style="text-align:center"><img src="data:image/png;base64,{img}" width="250"></div>', unsafe_allow_html=True)
    else:
        st.title("ChatScrap Elite")

    # Inputs
    c1, c2 = st.columns(2)
    niche = c1.text_input("🔍 Niche")
    cities_in = c2.text_input("🌍 Cities")
    
    c3, c4 = st.columns(2)
    limit = c3.number_input("Target", 1, 1000, 10)
    scrolls = c4.number_input("Depth", 1, 100, 10)

    if st.button("START ENGINE", use_container_width=True):
        if not niche or not cities_in:
            st.error("Fill inputs!")
        else:
            driver = get_driver()
            if driver:
                st.info("🚀 Driver Started! Scraping...")
                cities = [x.strip() for x in cities_in.split(',')]
                results = []
                
                progress = st.progress(0)
                
                for i, city in enumerate(cities):
                    driver.get(f"https://www.google.com/maps/search/{niche}+in+{city}")
                    time.sleep(3)
                    
                    # Simple Scroll
                    try:
                        div = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for _ in range(scrolls):
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", div)
                            time.sleep(1)
                    except: pass
                    
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:limit]
                    
                    for item in items:
                        try:
                            link = item.get_attribute("href")
                            driver.get(link)
                            time.sleep(1)
                            
                            try: name = driver.find_element(By.CSS_SELECTOR, "h1").text
                            except: name = "N/A"
                            
                            try: web = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]').get_attribute("href")
                            except: web = "N/A"
                            
                            try: phone = driver.find_element(By.CSS_SELECTOR, '[data-item-id*="phone"]').get_attribute("aria-label")
                            except: phone = "N/A"
                            
                            row = {"Name": name, "Phone": phone, "Website": web, "City": city}
                            results.append(row)
                            
                            # Save to DB
                            run_query("INSERT INTO leads VALUES (?, ?, ?, ?, ?, ?)", (name, phone, web, "N/A", "N/A", city))
                            
                        except: continue
                    
                    progress.progress(int((i + 1) / len(cities) * 100))
                
                st.success("✅ Done!")
                if results:
                    st.dataframe(pd.DataFrame(results))
            else:
                st.error("❌ Driver Failed to Init")

# Simple Footer
st.markdown("<br><hr><center>ChatScrap Elite © 2026</center>", unsafe_allow_html=True)

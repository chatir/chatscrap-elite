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

# --- 1. CONFIG & SESSION STATE (ALL FIXED) ---
st.set_page_config(page_title="ChatScrap Elite", layout="wide")

# Initialize Session State for persistence
state_keys = {
    'niche_val': '', 'city_val': '', 'limit_val': 20, 'scroll_val': 30,
    'results_df': None, 'running': False, 'progress_val': 0, 'status_txt': "READY"
}
for key, val in state_keys.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. AUTHENTICATION ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ config.yaml missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if st.session_state.get("authentication_status") is not True:
    authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your credentials'); st.stop()

# --- 3. GOOGLE SHEETS SYNC LOGIC ---
def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        #
        st.error("❌ Sync Error: 'gcp_service_account' key is missing in Streamlit Secrets!")
        return False
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sh = client.open_by_url(url)
        ws = sh.get_worksheet(0)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
        return True
    except Exception as e:
        st.error(f"Sync Error: {e}"); return False

# --- 4. CSS (ORANGE THEME & MOBILE POP-UP) ---
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3 {{ color: #FFFFFF !important; }}
    
    /* 🔥 Floating Progress Pop-up for Mobile */
    .floating-bar {{
        position: fixed; top: 60px; left: 50%; transform: translateX(-50%);
        width: 90%; max-width: 450px; background: #1a1f2e;
        border: 2px solid {orange_c}; border-radius: 12px; padding: 10px;
        z-index: 9999; box-shadow: 0 5px 20px rgba(0,0,0,0.8);
        text-align: center; font-weight: bold;
    }}
    
    /* 🔥 Mobile Filter Grid (2 items per row) */
    @media (max-width: 768px) {{
        [data-testid="stHorizontalBlock"] > div {{
            flex: 1 1 45% !important; min-width: 45% !important;
        }}
    }}
    
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 10px rgba(255,140,0,0.6)) saturate(180%); margin-bottom: 25px; }}
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; width: 100% !important; }}
    </style>
""", unsafe_allow_html=True)

# --- 5. APP INTERFACE ---
current_user = st.session_state["username"]
is_admin = current_user == "admin"

with st.sidebar:
    st.title("👤 User Profile")
    if is_admin: 
        #
        st.success("💎 Credits: **Unlimited ♾️**") 
        choice = st.radio("GO TO:", ["🚀 SCRAPER ENGINE", "🛠️ USER MANAGEMENT"], key="nav_choice")
    else:
        st.warning(f"💎 Credits: {st.session_state.get('user_credits', 0)}")
        choice = "🚀 SCRAPER ENGINE"
    
    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- MAIN ENGINE ---
if choice == "🚀 SCRAPER ENGINE":
    # Floating Bar for Mobile
    if st.session_state.running:
        st.markdown(f'<div class="floating-bar">🚀 {st.session_state.status_txt} - {st.session_state.progress_val}%</div>', unsafe_allow_html=True)

    cm = st.columns([1, 6, 1])[1]
    with cm:
        if os.path.exists("chatscrape.png"):
            with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
            st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)

    # Input persistent via Session State
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    niche = c1.text_input("🔍 Business Niche", value=st.session_state.niche_val, key="ni")
    city = c2.text_input("🌍 Global City", value=st.session_state.city_val, key="ci")
    limit = c3.number_input("Target", 1, 2000, value=st.session_state.limit_val, key="li")
    depth = c4.number_input("Depth", 5, 500, value=st.session_state.scroll_val, key="de")
    
    # Sync state immediately
    st.session_state.niche_val, st.session_state.city_val = niche, city
    st.session_state.limit_val, st.session_state.scroll_val = limit, depth

    st.divider()
    
    # Responsive Filters (Mobile-ready)
    st.write("⚙️ Lead Filters:")
    f_cols = st.columns(3) # Will wrap correctly on mobile
    w_phone = f_cols[0].checkbox("Phone", True)
    w_web = f_cols[1].checkbox("Web", True)
    w_no_site = f_cols[2].checkbox("No Site", False)
    
    btn_cols = st.columns(2)
    if btn_cols[0].button("START ENGINE", type="primary"):
        if niche and city:
            st.session_state.running = True; st.session_state.results_df = None; st.rerun()

    if btn_cols[1].button("STOP", type="secondary"):
        st.session_state.running = False; st.rerun()

    # Results persistent Area
    t1, t2 = st.tabs(["⚡ LIVE ANALYTICS", "📜 ARCHIVE BASE"])
    
    with t1:
        if st.session_state.results_df is not None:
            st.subheader("📤 Export Results")
            gs_url = st.text_input("Paste Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/...")
            if st.button("🚀 Sync to Sheet"):
                if sync_to_gsheet(st.session_state.results_df, gs_url): st.success("✅ Success!")
            
            st.dataframe(st.session_state.results_df, use_container_width=True, 
                         column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

        # Background Scraping Logic
        if st.session_state.running:
            # (Your full scraper loop goes here, updating session_state.results_df live)
            st.session_state.status_txt = "SCRAPING..."; st.session_state.progress_val = 50
            # Simulating results for demonstration
            st.session_state.results_df = pd.DataFrame([{"Name": "Cafe Agadir", "WhatsApp": "https://wa.me/212600000"}])
            st.session_state.running = False; st.rerun()

elif choice == "🛠️ USER MANAGEMENT" and is_admin:
    st.title("🛠️ Admin Control Panel")
    st.write("Background scraping will continue while you manage users.")
    # (Full Admin Table and User Management logic goes here)

st.markdown('<div style="text-align:center; padding:20px; color:#555;">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

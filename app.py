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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==============================================================================
# 1. إعدادات "الوحش" (THE BEAST CONFIGURATION)
# ==============================================================================
st.set_page_config(page_title="ChatScrap The Beast", layout="wide", page_icon="🕷️")

# تهيئة الذاكرة (Persistence Memory)
# هادشي باش المعلومات ما تمشيش فاش كتحرك فالسيت
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_val' not in st.session_state: st.session_state.progress_val = 0
if 'status_txt' not in st.session_state: st.session_state.status_txt = "SYSTEM READY"
if 'logs' not in st.session_state: st.session_state.logs = []

# ==============================================================================
# 2. نظام الأمان والمصادقة (SECURITY LAYER)
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ CRITICAL ERROR: 'config.yaml' NOT FOUND!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# التحقق من الهوية
if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False:
    st.error('❌ ACCESS DENIED: Wrong Password'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('🔒 SYSTEM LOCKED: Please Login'); st.stop()

# ==============================================================================
# 3. محرك قاعدة البيانات والربط (DATABASE & SYNC ENGINE)
# ==============================================================================
def run_query(query, params=(), is_select=False):
    """تنفيذ أوامر SQL بأمان تام"""
    try:
        with sqlite3.connect('scraper_beast.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except Exception as e:
        return [] if is_select else False

def init_db():
    """بناء البنية التحتية للبيانات"""
    tables = [
        '''CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            query TEXT, 
            date TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            session_id INTEGER, 
            keyword TEXT, 
            city TEXT, 
            name TEXT, 
            phone TEXT, 
            website TEXT, 
            email TEXT, 
            address TEXT, 
            whatsapp TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS user_credits (
            username TEXT PRIMARY KEY, 
            balance INTEGER, 
            status TEXT DEFAULT 'active'
        )'''
    ]
    for t in tables: run_query(t)
    
    # إصلاح الجداول القديمة أوتوماتيكياً
    try: run_query("SELECT city FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN city TEXT")

init_db()

# دوال إدارة الرصيد
def get_user_data(username):
    res = run_query("SELECT balance, status FROM user_credits WHERE username=?", (username,), is_select=True)
    if res: return res[0]
    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (username,))
    return (100, 'active')

def deduct_credit(username):
    if username != "admin": 
        run_query("UPDATE user_credits SET balance = balance - 1 WHERE username=?", (username,))

def add_credits(username, amount):
    run_query("UPDATE user_credits SET balance = balance + ? WHERE username=?", (amount, username))

# ربط Google Sheets
def sync_to_gsheet(df, url):
    if "gcp_service_account" not in st.secrets:
        st.toast("⚠️ Secrets Missing: Add 'gcp_service_account'!", icon="❌")
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
        st.error(f"Sync Failed: {e}")
        return False

# ==============================================================================
# 4. محرك البحث الهجين (THE HYBRID SCRAPER CORE)
# ==============================================================================
def get_driver_beast():
    """إعداد متصفح شبحي بقدرات تخفي عالية"""
    opts = Options()
    opts.add_argument("--headless=new") # النسخة الجديدة والأقوى
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US") # فرض الإنجليزية لتوحيد Selectors
    
    # User-Agent حقيقي لتفادي الحظر
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    """الدخول للموقع والبحث العميق عن الإيميل"""
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        # فتح نافذة جديدة
        driver.execute_script("window.open('');"); driver.switch_to.window(driver.window_handles[-1])
        try:
            # محاولة الدخول
            driver.set_page_load_timeout(12)
            driver.get(url); time.sleep(1.5)
            
            # البحث بـ Regex
            page_text = driver.page_source
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_text)
            
            # تنظيف النتائج من الصور والملفات
            valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            
            # إذا فشل، محاولة البحث عن صفحة "اتصل بنا"
            if not valid_emails:
                try:
                    contact_link = driver.find_element(By.XPATH, "//a[contains(@href, 'contact')]")
                    contact_link.click()
                    time.sleep(1.5)
                    page_text = driver.page_source
                    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_text)
                    valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg'))]
                except: pass

            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return valid_emails[0] if valid_emails else "N/A"
        except:
            driver.close(); driver.switch_to.window(driver.window_handles[0])
            return "N/A"
    except: return "N/A"

# ==============================================================================
# 5. التصميم الفاخر (ELITE UI & ANIMATIONS)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    /* الثيم العام */
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* 🔥 نافذة الموبايل المنبثقة (MOBILE POPUP) */
    .mobile-popup {{
        display: none; 
        position: fixed; top: 10px; left: 5%; width: 90%;
        background: rgba(20, 20, 30, 0.95); 
        border: 2px solid {orange_c};
        border-radius: 12px; padding: 12px; text-align: center;
        z-index: 999999; box-shadow: 0 10px 40px rgba(255, 140, 0, 0.3);
        backdrop-filter: blur(10px);
    }}
    @media (max-width: 768px) {{
        .mobile-popup {{ display: block; }}
        /* ترتيب الفلاتر في الموبايل */
        [data-testid="stHorizontalBlock"] > div {{ flex: 1 1 45% !important; min-width: 45% !important; }}
    }}
    
    /* اللوجو */
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* 🔥 شريط التقدم المتحرك (ANIMATED STRIPES) */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; }}
    .prog-fill {{ 
        height: 14px; 
        background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; 
        transition: width 0.4s ease;
        animation: stripes 1s linear infinite; 
    }}
    @keyframes stripes {{ 0% {{background-position: 0 0;}} 100% {{background-position: 50px 50px;}} }}
    
    /* الأزرار */
    div.stButton > button[kind="primary"] {{ 
        background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; 
        border: none; color: white !important; font-weight: 900 !important; font-size: 16px; padding: 10px; 
    }}
    div.stButton > button[kind="secondary"] {{ border: 1px solid #FF4500 !important; color: #FF4500 !important; }}
    
    /* التذييل */
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); font-size: 12px; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. منطق التطبيق (APP LOGIC)
# ==============================================================================
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

if user_st == 'suspended' and not is_admin: st.error("🚫 حسابك معلق (SUSPENDED)"); st.stop()

# --- القائمة الجانبية (SIDEBAR) ---
with st.sidebar:
    st.title("👤 الملف الشخصي")
    st.write(f"المستخدم: **{st.session_state['name']}**")
    
    if is_admin: st.success("💎 الرصيد: **Unlimited ♾️**")
    else: st.warning(f"💎 الرصيد: **{user_bal}**")
    
    st.divider()
    
    # لوحة الأدمن (محمية بـ Expander)
    if is_admin:
        with st.expander("🛠️ لوحة تحكم الأدمن"):
            # جدول المستخدمين
            u_data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            st.dataframe(pd.DataFrame(u_data, columns=["User", "Bal", "Sts"]), hide_index=True)
            
            # العمليات
            tgt_usr = st.selectbox("اختر مستخدم", [u[0] for u in u_data if u[0]!='admin'])
            
            c_a, c_b = st.columns(2)
            if c_a.button("💰 +100"):
                add_credits(tgt_usr, 100); st.rerun()
            if c_b.button("🔄 الحالة"):
                curr = next((u[2] for u in u_data if u[0]==tgt_usr), 'active')
                new_s = 'suspended' if curr=='active' else 'active'
                run_query("UPDATE user_credits SET status=? WHERE username=?", (new_s, tgt_usr))
                st.rerun()
            
            st.markdown("---")
            # إضافة مستخدم
            new_u = st.text_input("اسم المستخدم")
            new_p = st.text_input("كلمة السر", type="password")
            if st.button("➕ إنشاء"):
                if new_u and new_p:
                    try: hp = stauth.Hasher.hash(new_p)
                    except: hp = stauth.Hasher([new_p]).generate()[0]
                    config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hp, 'email': 'x'}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (new_u,))
                    st.success("تم الإنشاء!"); time.sleep(1); st.rerun()

    st.divider()
    if st.button("تسجيل الخروج", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- المحتوى الرئيسي (MAIN UI) ---
cm = st.columns([1, 6, 1])[1]
with cm:
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    # أماكن التحديث الديناميكي (Placeholders)
    p_holder = st.empty()
    m_holder = st.empty()

def update_ui(prog, txt):
    st.session_state.progress_val = prog
    st.session_state.status_txt = txt
    
    # تحديث الديسكتوب
    p_holder.markdown(f"""
        <div class="prog-box"><div class="prog-fill" style="width:{prog}%;"></div></div>
        <div style='color:{orange_c};text-align:center;font-weight:bold;margin-top:5px;'>{txt} {prog}%</div>
    """, unsafe_allow_html=True)
    
    # تحديث الموبايل (يظهر فقط أثناء التشغيل)
    if st.session_state.running:
        m_holder.markdown(f"""
            <div class="mobile-popup">
                <span style="color:{orange_c};font-weight:bold;">🚀 {txt}</span><br>
                <div style="background:#333;height:6px;border-radius:3px;margin-top:5px;">
                    <div style="background:{orange_c};width:{prog}%;height:100%;border-radius:3px;"></div>
                </div>
                <small>{prog}% Completed</small>
            </div>
        """, unsafe_allow_html=True)

# استرجاع حالة الواجهة
if st.session_state.running:
    update_ui(st.session_state.progress_val, st.session_state.status_txt)
else:
    update_ui(0, "SYSTEM READY")

# --- المدخلات (INPUTS) ---
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    # 🔥 Multi-Input Support
    kws_in = c1.text_input("🔍 الكلمات المفتاحية (Multi: cafe, hotel)", placeholder="مثال: cafe, restaurant")
    city_in = c2.text_input("🌍 المدن (Multi: Agadir, Casa)", placeholder="مثال: Agadir, Inezgane")
    limit_in = c3.number_input("الهدف لكل مدينة", 1, 5000, 20)
    depth_in = c4.number_input("عمق السكرول", 1, 500, 10)

    st.divider()
    co, cb = st.columns([5, 3])
    with co:
        st.caption("⚙️ **فلاتر صارمة (STRICT FILTERS):**")
        f = st.columns(4)
        w_phone = f[0].checkbox("ضروري الهاتف (Has Phone)", True)
        w_web = f[1].checkbox("ضروري الموقع (Has Website)", True)
        w_email = f[2].checkbox("جلب الإيميل (Deep Scan)", False)
        w_nosite = f[3].checkbox("بدون موقع فقط (No Website)", False)

    with cb:
        st.write("")
        b1, b2 = st.columns(2)
        start = b1.button("START ENGINE", type="primary", use_container_width=True)
        stop = b2.button("STOP", type="secondary", use_container_width=True)

if stop:
    st.session_state.running = False; st.rerun()

# --- التبويبات (TABS) ---
t1, t2, t3 = st.tabs(["⚡ النتائج الحية", "📜 الأرشيف", "🤖 حقيبة التسويق"])

# --- التبويب 1: المحرك (ENGINE ROOM) ---
with t1:
    spot = st.empty()
    if st.session_state.results_df is not None:
        st.divider()
        c_ex1, c_ex2 = st.columns([3, 1])
        gs_url = c_ex1.text_input("رابط Google Sheet (للتزامن)")
        if c_ex2.button("🚀 Sync Now"):
            if sync_to_gsheet(st.session_state.results_df, gs_url): st.success("تم التزامن بنجاح!")
            
        st.download_button("📥 تحميل CSV", st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), "leads_beast.csv", use_container_width=True)
        spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})

    # 🔥🔥🔥 تشغيل الوحش 🔥🔥🔥
    if start and kws_in and city_in:
        st.session_state.running = True
        st.session_state.results_df = None
        all_leads = []
        
        # معالجة المدخلات
        kw_list = [k.strip() for k in kws_in.split(',') if k.strip()]
        ct_list = [c.strip() for c in city_in.split(',') if c.strip()]
        total_ops = len(kw_list) * len(ct_list)
        curr_op = 0
        
        # تسجيل الجلسة
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{kws_in} | {city_in}", time.strftime("%Y-%m-%d %H:%M")))
        try: s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        except: s_id = 1

        driver = get_driver_beast()
        if driver:
            try:
                # 🔄 اللوب الذكي (Smart Nested Loop)
                for city in ct_list:
                    for kw in kw_list:
                        if not st.session_state.running: break
                        curr_op += 1
                        
                        update_ui(int(((curr_op-1)/total_ops)*100), f"SCANNING: {kw} in {city} ({curr_op}/{total_ops})")

                        # 1. التنقل (Navigation)
                        url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                        driver.get(url); time.sleep(4)

                        # 2. تجاوز الكوكيز (Cookie Bypass)
                        try: driver.find_element(By.XPATH, "//button[contains(., 'Accept all')]").click(); time.sleep(2)
                        except: pass

                        # 3. السكرول (Fallback Logic)
                        try:
                            feed = None
                            try: feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            except: feed = driver.find_element(By.TAG_NAME, 'body')
                            
                            for i in range(depth_in):
                                if not st.session_state.running: break
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                feed.send_keys(Keys.END)
                                time.sleep(1.5)
                        except: pass
                        
                        # 4. الاستخراج الهجين (Hybrid Extraction)
                        # البحث عن الروابط بـ XPATH (أضمن طريقة)
                        elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        
                        # إزالة التكرار
                        seen = set(); unique = []
                        for e in elements:
                            h = e.get_attribute("href")
                            if h and h not in seen: seen.add(h); unique.append(e)
                        
                        valid_count = 0
                        
                        # الدخول لكل عنصر
                        for idx, el in enumerate(unique):
                            if not st.session_state.running: break
                            if valid_count >= limit_in: break # الحد لكل مدينة
                            if not is_admin and get_user_data(user)[0] <= 0: 
                                st.error("نفذ الرصيد!"); st.session_state.running = False; break
                            
                            try:
                                # النقر لفتح التفاصيل
                                driver.execute_script("arguments[0].click();", el)
                                time.sleep(1.5)
                                
                                # جمع البيانات
                                name = "N/A"; phone = "N/A"; web = "N/A"; addr = "N/A"
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = "Unknown"
                                
                                try: addr = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: pass
                                
                                try: 
                                    p = driver.find_element(By.CSS_SELECTOR, '[data-item-id^="phone:tel:"]')
                                    phone = p.text
                                except: pass
                                
                                try:
                                    w = driver.find_element(By.CSS_SELECTOR, '[data-item-id="authority"]')
                                    web = w.get_attribute("href")
                                except: pass
                                
                                # 🔥🔥🔥 نقطة التفتيش الصارمة (STRICT CHECKPOINT) 🔥🔥🔥
                                # إذا مفعل "هاتف" والنتيجة خاوية -> دوز (تجاهل)
                                if w_phone and (phone == "N/A" or phone == ""): continue
                                # إذا مفعل "موقع" والنتيجة خاوية -> دوز
                                if w_web and (web == "N/A" or web == ""): continue
                                # إذا مفعل "بدون موقع" والنتيجة فيها موقع -> دوز
                                if w_nosite and web != "N/A": continue
                                
                                # البحث العميق عن الإيميل (فقط إذا نجحت الفلاتر السابقة)
                                email = "N/A"
                                if w_email and web != "N/A":
                                    update_ui(int(((curr_op-1)/total_ops)*100), f"FETCHING EMAIL: {name}")
                                    email = fetch_email_deep(driver, web)
                                
                                # واتساب
                                wa = f"https://wa.me/{re.sub(r'[^\d]', '', phone)}" if phone != "N/A" else "N/A"
                                
                                # حفظ النتيجة
                                row = {
                                    "Keyword": kw, "City": city, "Name": name, 
                                    "Phone": phone, "WhatsApp": wa, "Website": web, 
                                    "Email": email, "Address": addr
                                }
                                all_leads.append(row)
                                valid_count += 1
                                
                                # تحديث فوري (Real-time Update)
                                if not is_admin: deduct_credit(current_user)
                                st.session_state.results_df = pd.DataFrame(all_leads)
                                spot.dataframe(st.session_state.results_df, use_container_width=True, column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")})
                                run_query("INSERT INTO leads (session_id, keyword, city, name, phone, website, address, whatsapp, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (s_id, kw, city, name, phone, web, addr, wa, email))
                                
                            except: continue
                
                update_ui(100, "COMPLETED ✅")
                st.balloons()
                st.success(f"انتهى البحث! تم جمع {len(all_leads)} نتيجة مطابقة.")
            
            finally:
                driver.quit()
                st.session_state.running = False
                m_holder.empty(); st.rerun()

# --- TAB 2: الأرشيف ---
with t2:
    st.subheader("📜 أرشيف البحث")
    try:
        h = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 20", is_select=True)
        for s in h:
            with st.expander(f"📦 {s[2]} | {s[1]}"):
                d = run_query(f"SELECT keyword, city, name, phone, whatsapp, website, email, address FROM leads WHERE session_id={s[0]}", is_select=True)
                df_h = pd.DataFrame(d, columns=["KW", "City", "Name", "Phone", "WA", "Web", "Email", "Addr"])
                st.dataframe(df_h, use_container_width=True)
                st.download_button("Export CSV", df_h.to_csv(index=False).encode('utf-8-sig'), f"archive_{s[0]}.csv")
    except: pass

# --- TAB 3: التسويق ---
with t3:
    st.subheader("🤖 مولد رسائل التسويق (AI Marketing Kit)")
    c_m1, c_m2 = st.columns(2)
    srv = c_m1.selectbox("الخدمة", ["Web Design", "SEO", "Ads Management", "Google Maps Ranking"])
    tone = c_m2.selectbox("اللغة", ["English", "Français", "العربية"])
    
    if st.button("✨ توليد الرسالة"):
        if tone == "English":
            msg = f"Subject: Proposal regarding {kws_in} in {city_in}\n\nHi,\nI found your business while searching for {kws_in}..."
        elif tone == "Français":
            msg = f"Sujet: Proposition concernant {kws_in} à {city_in}\n\nBonjour,\nJ'ai trouvé votre entreprise..."
        else:
            msg = f"الموضوع: بخصوص نشاطكم في {city_in}\n\nالسلام عليكم،\nلقد وجدت شركتكم أثناء البحث عن {kws_in}..."
            
        st.text_area("انسخ الرسالة:", value=msg, height=200)

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import base64
import os
import yaml
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
# 1. إعدادات النظام وحفظ الحالة (System Setup)
# ==============================================================================
st.set_page_config(page_title="ChatScrap Elite Ultimate", layout="wide", page_icon="🕷️")

# تهيئة المتغيرات باش مايضيعوش (Persistence)
if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress_bar' not in st.session_state: st.session_state.progress_bar = 0
if 'status_text' not in st.session_state: st.session_state.status_text = "Jahiz (Ready)"
if 'logs' not in st.session_state: st.session_state.logs = []

# ==============================================================================
# 2. المصادقة والأمان (Authentication)
# ==============================================================================
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("❌ Critical Error: 'config.yaml' file is missing!"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# التحقق من الدخول
if st.session_state.get("authentication_status") is not True:
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False:
    st.error('❌ كلمة المرور خاطئة (Wrong Password)'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.warning('🔒 المرجو تسجيل الدخول (Please Login)'); st.stop()

# ==============================================================================
# 3. إدارة قاعدة البيانات (Database Manager)
# ==============================================================================
def run_query(query, params=(), is_select=False):
    """تنفيذ أوامر SQL بأمان"""
    try:
        with sqlite3.connect('scraper_pro_final.db', timeout=30) as conn:
            curr = conn.cursor()
            curr.execute(query, params)
            if is_select: return curr.fetchall()
            conn.commit()
            return True
    except Exception as e:
        return [] if is_select else False

def init_db():
    """إنشاء الجداول الضرورية"""
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
    
    # تحديث قاعدة البيانات القديمة إذا كانت ناقصة
    try: run_query("SELECT email FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN email TEXT")
    try: run_query("SELECT keyword FROM leads LIMIT 1")
    except: run_query("ALTER TABLE leads ADD COLUMN keyword TEXT")

init_db()

# دوال الرصيد والمستخدمين
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

# ==============================================================================
# 4. محرك البحث (The Scraper Engine)
# ==============================================================================
def get_driver():
    """إعداد المتصفح الخفي"""
    opts = Options()
    # استخدام Headless العادي لأنه أكثر استقراراً مع السكرول القديم
    opts.add_argument("--headless") 
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US") # فرض الإنجليزية لتثبيت الكلاسات
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except: return webdriver.Chrome(options=opts)

def fetch_email_deep(driver, url):
    """البحث العميق عن الإيميل داخل الموقع"""
    if not url or "google.com" in url or url == "N/A": return "N/A"
    try:
        # فتح تبويب جديد
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # محاولة الدخول للموقع بسرعة
        driver.set_page_load_timeout(15)
        try: driver.get(url)
        except: pass # تجاوز إذا تعطل التحميل
        
        time.sleep(1.5)
        
        # البحث عن الإيميل بـ Regex
        page_text = driver.page_source
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_text)
        
        # إغلاق التبويب والعودة
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        
        # فلترة الإيميلات المكررة أو الصور (.png)
        valid_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif'))]
        
        return valid_emails[0] if valid_emails else "N/A"
    except:
        # في حالة حدوث خطأ، نغلق التبويب فوراً
        if len(driver.window_handles) > 1: driver.close()
        driver.switch_to.window(driver.window_handles[0])
        return "N/A"

# ==============================================================================
# 5. التصميم والواجهة (UI Styling)
# ==============================================================================
orange_c = "#FF8C00"
st.markdown(f"""
    <style>
    /* الخلفية العامة */
    .stApp {{ background-color: #0f111a; }}
    .stApp p, .stApp label, h1, h2, h3, div, span {{ color: #FFFFFF !important; font-family: 'Segoe UI', sans-serif; }}
    
    /* تصميم الجدول */
    .stDataFrame {{ border: 1px solid #333; border-radius: 5px; }}
    
    /* أيقونة اللوجو وتأثيراتها */
    .logo-img {{ width: 280px; filter: drop-shadow(0 0 15px rgba(255,140,0,0.5)) saturate(180%); margin-bottom: 25px; }}
    
    /* شريط التقدم المخصص */
    .prog-box {{ width: 100%; background: rgba(255, 140, 0, 0.1); border-radius: 50px; padding: 4px; border: 1px solid {orange_c}; margin-bottom: 20px; }}
    .prog-fill {{ 
        height: 14px; 
        background: repeating-linear-gradient(45deg, {orange_c}, {orange_c} 10px, #FF4500 10px, #FF4500 20px); 
        border-radius: 20px; 
        transition: width 0.4s ease;
        animation: move-stripes 1s linear infinite; 
    }}
    @keyframes move-stripes {{ 0% {{ background-position: 0 0; }} 100% {{ background-position: 50px 50px; }} }}
    
    /* الأزرار */
    div.stButton > button[kind="primary"] {{ background: linear-gradient(135deg, {orange_c} 0%, #FF4500 100%) !important; border: none; color: white !important; font-weight: 900 !important; font-size: 16px; padding: 10px; width: 100%; }}
    div.stButton > button[kind="secondary"] {{ border: 1px solid #FF4500 !important; color: #FF4500 !important; width: 100%; }}
    
    /* تذييل الصفحة */
    .footer {{ position: fixed; left: 0; bottom: 0; width: 100%; background-color: #0f111a; color: #888888; text-align: center; padding: 10px; border-top: 1px solid rgba(128,128,128,0.1); font-size: 12px; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. منطق التطبيق (Application Logic)
# ==============================================================================
current_user = st.session_state["username"]
user_bal, user_st = get_user_data(current_user)
is_admin = current_user == "admin"

# التحقق من حالة الحساب
if user_st == 'suspended' and not is_admin: 
    st.error("🚫 حسابك موقوف (Suspended). اتصل بالأدمن."); st.stop()

# --- القائمة الجانبية (Sidebar) ---
with st.sidebar:
    st.title("👤 User Profile")
    st.write(f"Logged as: **{st.session_state['name']}**")
    
    if is_admin: st.success("💎 Credits: **Unlimited ♾️**")
    else: st.warning(f"💎 Credits: **{user_bal}**")
    
    st.divider()
    
    # --- لوحة تحكم الأدمن (محمية داخل Sidebar) ---
    if is_admin:
        with st.expander("🛠️ ADMIN CONTROL PANEL"):
            st.write("Manage Users & Credits")
            
            # جدول المستخدمين
            users_data = run_query("SELECT username, balance, status FROM user_credits", is_select=True)
            df_users = pd.DataFrame(users_data, columns=["User", "Credits", "Status"])
            st.dataframe(df_users, hide_index=True, use_container_width=True)
            
            # العمليات
            target_user = st.selectbox("Select User", [u[0] for u in users_data if u[0] != 'admin'])
            
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button("💰 Add 100 Cr"):
                    add_credits(target_user, 100)
                    st.toast(f"Added 100 credits to {target_user}")
                    time.sleep(1); st.rerun()
            
            with col_act2:
                if st.button("🔄 Toggle Status"):
                    curr_status = next((u[2] for u in users_data if u[0] == target_user), 'active')
                    new_status = 'suspended' if curr_status == 'active' else 'active'
                    run_query("UPDATE user_credits SET status=? WHERE username=?", (new_status, target_user))
                    st.toast(f"Status changed to {new_status}")
                    time.sleep(1); st.rerun()
            
            st.markdown("---")
            # إضافة مستخدم جديد
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password", type="password")
            if st.button("➕ Create User"):
                if new_u and new_p:
                    try: hashed_pw = stauth.Hasher.hash(new_p)
                    except: hashed_pw = stauth.Hasher([new_p]).generate()[0]
                    
                    config['credentials']['usernames'][new_u] = {'name': new_u, 'password': hashed_pw, 'email': f"{new_u}@mail.com"}
                    with open('config.yaml', 'w') as f: yaml.dump(config, f)
                    
                    run_query("INSERT INTO user_credits VALUES (?, 100, 'active')", (new_u,))
                    st.success(f"User {new_u} Created!")
                    time.sleep(1); st.rerun()

    st.divider()
    if st.button("Logout", type="secondary"):
        authenticator.logout('Logout', 'main'); st.session_state.clear(); st.rerun()

# --- المحتوى الرئيسي (Main Content) ---
cm = st.columns([1, 6, 1])[1]
with cm:
    # عرض اللوجو
    if os.path.exists("chatscrape.png"):
        with open("chatscrape.png", "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{b64}" class="logo-img"></div>', unsafe_allow_html=True)
    
    # مكان شريط التقدم (Placeholder)
    progress_placeholder = st.empty()
    status_placeholder = st.empty()

# دالة لتحديث الواجهة
def update_ui(progress, message):
    st.session_state.progress_bar = progress
    st.session_state.status_text = message
    
    progress_placeholder.markdown(f"""
        <div class="prog-box"><div class="prog-fill" style="width:{progress}%;"></div></div>
    """, unsafe_allow_html=True)
    
    status_placeholder.markdown(f"""
        <div style='color:{orange_c};text-align:center;font-weight:bold;margin-bottom:20px;font-size:18px;'>
            {message} ({progress}%)
        </div>
    """, unsafe_allow_html=True)

# استرجاع الحالة السابقة عند إعادة التحميل
if st.session_state.running:
    update_ui(st.session_state.progress_bar, st.session_state.status_text)
else:
    update_ui(0, "SYSTEM READY")

# --- إدخال البيانات (Inputs) ---
with st.container():
    col1, col2, col3, col4 = st.columns([3, 3, 1.5, 1.5])
    
    keywords_input = col1.text_input("🔍 Keywords (Multi: cafe, hotel)", placeholder="مثال: cafe, snack, agence")
    cities_input = col2.text_input("🌍 Cities (Multi: Agadir, Casa)", placeholder="مثال: Agadir, Inezgane")
    limit_input = col3.number_input("Target/City", 1, 5000, 20)
    depth_input = col4.number_input("Scroll Depth", 1, 500, 10)

    st.divider()
    
    # الفلاتر
    f_col, b_col = st.columns([5, 3])
    with f_col:
        st.caption("⚙️ Active Filters:")
        f_opts = st.columns(4)
        w_phone = f_opts[0].checkbox("Has Phone", True)
        w_web = f_opts[1].checkbox("Has Website", True)
        w_email = f_opts[2].checkbox("Extract Email (Deep)", False)
        w_nosite = f_opts[3].checkbox("No Website Only", False)
    
    with b_col:
        st.write("") # Spacer
        btn1, btn2 = st.columns(2)
        start_btn = btn1.button("START ENGINE", type="primary")
        stop_btn = btn2.button("STOP", type="secondary")

# زر التوقف
if stop_btn:
    st.session_state.running = False
    st.rerun()

# --- التبويبات (Tabs) ---
t1, t2, t3 = st.tabs(["⚡ LIVE RESULTS", "📜 ARCHIVE", "🤖 MARKETING KIT"])

# --- التبويب 1: النتائج الحية ---
with t1:
    results_placeholder = st.empty()
    
    # عرض النتائج المحفوظة
    if st.session_state.results_df is not None:
        st.divider()
        st.download_button(
            "📥 Download Results (CSV)", 
            st.session_state.results_df.to_csv(index=False).encode('utf-8-sig'), 
            "leads_master_list.csv", 
            "text/csv", 
            use_container_width=True
        )
        results_placeholder.dataframe(
            st.session_state.results_df, 
            use_container_width=True, 
            column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
        )

    # ==============================================================================
    # 🔥 المحرك الرئيسي (THE CORE ENGINE)
    # ==============================================================================
    if start_btn and keywords_input and cities_input:
        st.session_state.running = True
        st.session_state.results_df = None
        all_leads = []
        
        # معالجة المدخلات (Split & Clean)
        kw_list = [k.strip() for k in keywords_input.split(',') if k.strip()]
        ct_list = [c.strip() for c in cities_input.split(',') if c.strip()]
        
        total_operations = len(kw_list) * len(ct_list)
        current_op_index = 0
        
        # تسجيل الجلسة في قاعدة البيانات
        run_query("INSERT INTO sessions (query, date) VALUES (?, ?)", (f"{keywords_input} in {cities_input}", time.strftime("%Y-%m-%d %H:%M")))
        try: 
            s_id = run_query("SELECT id FROM sessions ORDER BY id DESC LIMIT 1", is_select=True)[0][0]
        except: 
            s_id = 1

        # بدء المتصفح
        driver = get_driver()
        
        if driver:
            try:
                # 🔄 الحلقة الكبرى (Loop over Cities & Keywords)
                for city in ct_list:
                    for kw in kw_list:
                        # التحقق من زر التوقف
                        if not st.session_state.running: break
                        
                        current_op_index += 1
                        
                        # تحديث الواجهة: بداية البحث
                        update_ui(
                            int(((current_op_index - 1) / total_operations) * 100), 
                            f"SCANNING: {kw} in {city} ({current_op_index}/{total_operations})..."
                        )
                        
                        # 1. الذهاب للرابط (Force English)
                        search_query = f"{kw} in {city}"
                        url = f"https://www.google.com/maps/search/{quote(search_query)}?hl=en"
                        driver.get(url)
                        time.sleep(4) # انتظار التحميل الأولي
                        
                        # 2. السكرول القديم (The Old Reliable Method)
                        try:
                            # محاولة العثور على القائمة الجانبية (Feed)
                            try:
                                feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                            except:
                                # إذا لم يجد Feed، نبحث عن أي عنصر يحتوي على النتائج
                                feed = driver.find_element(By.TAG_NAME, 'body')
                            
                            # حلقة السكرول
                            for i in range(depth_input):
                                if not st.session_state.running: break
                                
                                # التمرير للأسفل
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                                feed.send_keys(Keys.END) # مفتاح END لضمان التحرك
                                time.sleep(2) # انتظار تحميل العناصر الجديدة
                                
                                # تحديث الواجهة أثناء السكرول (هادشي اللي بغيتي)
                                current_step_progress = int(((current_op_index - 1) / total_operations) * 100) + int((i / depth_input) * (100/total_operations))
                                update_ui(current_step_progress, f"SCROLLING: {kw} in {city} - Step {i+1}/{depth_input}")
                                
                        except Exception as e:
                            st.toast(f"Scroll Warning: {str(e)}", icon="⚠️")

                        # 3. استخراج البيانات (Scraping Loop)
                        # البحث عن الكلاس القديم المضمون hfpxzc
                        items = driver.find_elements(By.CLASS_NAME, "hfpxzc")
                        
                        # إذا لم يجد الكلاس القديم، جرب البحث بالروابط (Backup Strategy)
                        if len(items) == 0:
                            items = driver.find_elements(By.XPATH, '//a[contains(@href, "/maps/place/")]')
                        
                        update_ui(current_step_progress, f"EXTRACTING: Found {len(items)} items for {kw}...")
                        
                        # تحديد العدد المطلوب
                        target_items = items[:limit_input]
                        
                        for idx, item in enumerate(target_items):
                            if not st.session_state.running: break
                            
                            # التحقق من الرصيد
                            if not is_admin and get_user_data(current_user)[0] <= 0:
                                st.error("No Credits Left!"); st.session_state.running = False; break
                            
                            try:
                                # النقر على العنصر لفتح التفاصيل (ضروري للبيانات الدقيقة)
                                # (نستعمل JS Click لتفادي الأخطاء)
                                driver.execute_script("arguments[0].click();", item)
                                time.sleep(1.5) # انتظار تحميل التفاصيل
                                
                                # --- استخراج المعلومات ---
                                
                                # الاسم
                                try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                                except: name = item.get_attribute("aria-label") or "Unknown"
                                
                                # العنوان
                                try: address = driver.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium').text
                                except: address = "N/A"
                                
                                # الهاتف (بحث ذكي)
                                phone = "N/A"; whatsapp_link = "N/A"
                                try:
                                    # البحث عن أي زر يبدأ بـ phone
                                    phone_el = driver.find_element(By.CSS_SELECTOR, '[data-item-id^="phone:tel:"]')
                                    phone = phone_el.text
                                    # تنظيف الرقم للواتساب
                                    clean_phone = re.sub(r'[^\d]', '', phone)
                                    if clean_phone:
                                        whatsapp_link = f"https://wa.me/{clean_phone}"
                                except: pass
                                
                                # الموقع الإلكتروني
                                website = "N/A"
                                try:
                                    web_el = driver.find_element(By.CSS_SELECTOR, '[data-item-id="authority"]')
                                    website = web_el.get_attribute("href")
                                except: pass
                                
                                # الفلترة (Filters Logic)
                                if w_phone and phone == "N/A": continue
                                if w_web and website == "N/A": continue
                                if w_nosite and website != "N/A": continue
                                
                                # استخراج الإيميل (Deep Extraction)
                                email = "N/A"
                                if w_email and website != "N/A":
                                    update_ui(current_step_progress, f"FETCHING EMAIL for {name}...")
                                    email = fetch_email_deep(driver, website)
                                
                                # تجميع البيانات
                                row = {
                                    "Keyword": kw,
                                    "City": city,
                                    "Name": name,
                                    "Phone": phone,
                                    "WhatsApp": whatsapp_link,
                                    "Website": website,
                                    "Email": email,
                                    "Address": address
                                }
                                all_leads.append(row)
                                
                                # خصم الرصيد وحفظ في الداتا بيز
                                if not is_admin: deduct_credit(current_user)
                                
                                run_query("""
                                    INSERT INTO leads (session_id, keyword, city, name, phone, website, address, whatsapp, email) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (s_id, kw, city, name, phone, website, address, whatsapp_link, email))
                                
                                # تحديث الجدول مباشرة
                                st.session_state.results_df = pd.DataFrame(all_leads)
                                results_placeholder.dataframe(
                                    st.session_state.results_df, 
                                    use_container_width=True, 
                                    column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
                                )
                                
                            except Exception as e:
                                continue # تجاوز الخطأ والانتقال للعنصر التالي
            
                # النهاية
                update_ui(100, "COMPLETED SUCCESSFULLY ✅")
                st.success(f"Done! Scraped {len(all_leads)} leads.")
                
            except Exception as main_e:
                st.error(f"Engine Error: {main_e}")
            finally:
                driver.quit()
                st.session_state.running = False
                # st.rerun() # اختياري: تحديث الصفحة في النهاية

# --- التبويب 2: الأرشيف ---
with t2:
    st.subheader("📜 Search History")
    try:
        sessions = run_query("SELECT * FROM sessions ORDER BY id DESC LIMIT 30", is_select=True)
        if sessions:
            for s in sessions:
                with st.expander(f"📅 {s[2]} | 🔍 {s[1]}"):
                    session_leads = run_query(f"SELECT * FROM leads WHERE session_id={s[0]}", is_select=True)
                    if session_leads:
                        # تحويل البيانات إلى DataFrame
                        cols = ["ID", "Session", "KW", "City", "Name", "Phone", "Web", "Email", "Addr", "WA"]
                        df_hist = pd.DataFrame(session_leads, columns=cols)
                        # تنظيف الأعمدة للعرض
                        display_df = df_hist[["KW", "City", "Name", "Phone", "WA", "Web", "Email"]]
                        st.dataframe(display_df, use_container_width=True)
                        st.download_button(f"📥 Export Session {s[0]}", display_df.to_csv(index=False).encode('utf-8-sig'), f"session_{s[0]}.csv")
                    else:
                        st.info("Empty Session")
        else:
            st.info("No history found.")
    except Exception as e:
        st.error(f"History Error: {e}")

# --- التبويب 3: التسويق ---
with t3:
    st.subheader("🤖 Smart Outreach")
    col_mark1, col_mark2 = st.columns(2)
    service_type = col_mark1.selectbox("Service", ["Web Design", "SEO", "Ads", "SaaS"])
    lang_outreach = col_mark2.selectbox("Language", ["English", "French", "Arabic"])
    
    if st.button("Generate Script ✍️"):
        st.markdown("### 📋 Copy this script:")
        script_text = ""
        if lang_outreach == "English":
            script_text = f"Subject: Question about your business in {cities_input}...\n\nHi,\nI found your business while searching for {keywords_input} and noticed..."
        elif lang_outreach == "French":
            script_text = f"Sujet: Question concernant votre activité à {cities_input}...\n\nBonjour,\nJ'ai trouvé votre entreprise en cherchant {keywords_input} et j'ai remarqué..."
        elif lang_outreach == "Arabic":
            script_text = f"الموضوع: بخصوص نشاطكم التجاري في {cities_input}...\n\nالسلام عليكم،\nلقد وجدت نشاطكم أثناء البحث عن {keywords_input} ولاحظت..."
            
        st.text_area("Script", value=script_text, height=200)

st.markdown('<div class="footer">Designed by Chatir ❤ | Worldwide Lead Generation 🌍</div>', unsafe_allow_html=True)

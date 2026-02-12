import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import yaml
import streamlit_authenticator as stauth
from yaml.loader import SafeLoader
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote

# ==========================================
# 1. إعدادات النظام (System Setup)
# ==========================================
st.set_page_config(page_title="ChatScrap Precision", layout="wide", page_icon="🕷️")

if 'results_df' not in st.session_state: st.session_state.results_df = None
if 'running' not in st.session_state: st.session_state.running = False
if 'progress' not in st.session_state: st.session_state.progress = 0
if 'status' not in st.session_state: st.session_state.status = "واجد للعمل"

# ==========================================
# 2. الدخول (Authentication)
# ==========================================
try:
    with open('config.yaml') as file: config = yaml.load(file, Loader=SafeLoader)
except: st.error("ملف config.yaml مفقود"); st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['cookie']['name'], config['cookie']['key'], config['cookie']['expiry_days']
)

if not st.session_state.get("authentication_status"):
    try: authenticator.login()
    except: pass

if st.session_state["authentication_status"] is False: st.error('كلمة السر خاطئة'); st.stop()
elif st.session_state["authentication_status"] is None: st.warning('المرجو تسجيل الدخول'); st.stop()

# ==========================================
# 3. قاعدة البيانات (Database)
# ==========================================
def run_query(q, p=(), s=False):
    with sqlite3.connect('scraper_data.db', timeout=30) as conn:
        cur = conn.cursor()
        cur.execute(q, p)
        if s: return cur.fetchall()
        conn.commit()

run_query('''CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY, keyword TEXT, city TEXT, name TEXT, phone TEXT, whatsapp TEXT, website TEXT, address TEXT)''')
run_query('''CREATE TABLE IF NOT EXISTS credits (user TEXT PRIMARY KEY, bal INTEGER)''')

def get_bal(u):
    r = run_query("SELECT bal FROM credits WHERE user=?", (u,), True)
    if r: return r[0][0]
    run_query("INSERT INTO credits VALUES (?, 100)", (u,))
    return 100

def deduct(u):
    if u != "admin": run_query("UPDATE credits SET bal=bal-1 WHERE user=?", (u,))

# ==========================================
# 4. المحرك (Engine)
# ==========================================
def get_driver():
    o = Options()
    o.add_argument("--headless") 
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--window-size=1920,1080")
    o.add_argument("--lang=en") 
    try: return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    except: return webdriver.Chrome(options=o)

# ==========================================
# 5. الواجهة (UI)
# ==========================================
user = st.session_state["username"]
is_admin = user == "admin"

with st.sidebar:
    st.title("لوحة التحكم")
    st.write(f"مرحباً: **{st.session_state['name']}**")
    if is_admin: st.success("الرصيد: غير محدود ♾️")
    else: st.warning(f"الرصيد: {get_bal(user)}")
    if st.button("تسجيل الخروج"): authenticator.logout('Logout', 'main'); st.rerun()

st.markdown("<h1 style='text-align: center; color: #FF8C00;'>🚀 ChatScrap Elite Precision</h1>", unsafe_allow_html=True)

prog_bar = st.progress(st.session_state.progress)
status_text = st.empty()
status_text.text(st.session_state.status)
results_placeholder = st.empty()

# الخانات
with st.container():
    c1, c2, c3, c4 = st.columns([3, 3, 1.5, 1.5])
    kws_input = c1.text_input("الكلمات المفتاحية (فرق بفاصلة ,)", "cafe, snack")
    city_input = c2.text_input("المدن (فرق بفاصلة ,)", "Agadir, Casa")
    limit = c3.number_input("العدد لكل مدينة", 1, 5000, 10)
    depth = c4.number_input("عمق السكرول", 1, 100, 5)

    st.divider()
    
    # الفلاتر (تحكم كامل)
    st.write("⚙️ **حدد البيانات المطلوبة (ما ستختاره سيتم جلبه وفلترته):**")
    f_cols = st.columns(4)
    
    # إذا كوشيتي = جيب النمرة + ضروري تكون كاينة
    w_phone = f_cols[0].checkbox("هاتف (Phone)", True) 
    
    # إذا كوشيتي = جيب السيت + ضروري يكون كاين
    w_web = f_cols[1].checkbox("موقع (Website)", False)
    
    # الأزرار
    b_cols = st.columns(2)
    start = b_cols[0].button("ابدأ البحث (Start)", type="primary", use_container_width=True)
    stop = b_cols[1].button("توقف (Stop)", use_container_width=True)

if stop:
    st.session_state.running = False
    st.rerun()

# ==========================================
# 6. اللوجيك الدقيق (The Precision Logic)
# ==========================================
if start and kws_input and city_input:
    st.session_state.running = True
    st.session_state.results_df = None
    
    keywords = [k.strip() for k in kws_input.split(',') if k.strip()]
    cities = [c.strip() for c in city_input.split(',') if c.strip()]
    
    all_leads_collected = [] 
    
    driver = get_driver()
    if driver:
        try:
            total_tasks = len(keywords) * len(cities)
            current_task = 0
            
            for city in cities:
                for kw in keywords:
                    if not st.session_state.running: break
                    current_task += 1
                    
                    status_text.text(f"جاري العمل على: {kw} في {city} ({current_task}/{total_tasks})...")
                    
                    # 1. الرابط
                    url = f"https://www.google.com/maps/search/{quote(kw)}+in+{quote(city)}?hl=en"
                    driver.get(url)
                    time.sleep(4)
                    
                    # 2. السكرول (Old School)
                    try:
                        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
                        for i in range(depth):
                            if not st.session_state.running: break
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
                            time.sleep(2)
                            
                            prog = int(((current_task - 1) / total_tasks * 100) + (i / depth * (100 / total_tasks)))
                            prog_bar.progress(prog)
                    except: pass

                    # 3. جمع البيانات (على حساب الفلتر)
                    items = driver.find_elements(By.CLASS_NAME, "hfpxzc")
                    valid_leads_count = 0
                    
                    for item in items:
                        if not st.session_state.running: break
                        if valid_leads_count >= limit: break
                        if not is_admin and get_bal(user) <= 0: break
                        
                        try:
                            driver.execute_script("arguments[0].click();", item)
                            time.sleep(1.5)
                            
                            name = "N/A"; phone = "N/A"; wa_link = "N/A"; website = "N/A"
                            
                            try: name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                            except: name = item.get_attribute("aria-label")
                            
                            # 🔥 التحكم في الهاتف 🔥
                            if w_phone: # إذا بغيتي الهاتف
                                try:
                                    p_btn = driver.find_element(By.CSS_SELECTOR, '[data-item-id^="phone:tel:"]')
                                    phone = p_btn.text
                                    clean_ph = re.sub(r'[^\d]', '', phone)
                                    if clean_ph: wa_link = f"https://wa.me/{clean_ph}"
                                except: pass
                                
                                # الفلتر الصارم: مالقيتيش النمرة؟ دوز
                                if phone == "N/A" or phone == "": continue
                            else:
                                phone = "---" # ما طلبتيهش
                                wa_link = "---"

                            # 🔥 التحكم في الموقع 🔥
                            if w_web: # إذا بغيتي السيت
                                try:
                                    w_btn = driver.find_element(By.CSS_SELECTOR, '[data-item-id="authority"]')
                                    website = w_btn.get_attribute("href")
                                except: pass
                                
                                # الفلتر الصارم: مالقيتيش السيت؟ دوز
                                if website == "N/A" or website == "": continue
                            else:
                                website = "---" # ما طلبتيهش
                            
                            # تجميع
                            row = {
                                "Keyword": kw, "City": city, "Name": name, 
                                "Phone": phone, "WhatsApp": wa_link, "Website": website
                            }
                            all_leads_collected.append(row)
                            valid_leads_count += 1
                            deduct(user)
                            
                            st.session_state.results_df = pd.DataFrame(all_leads_collected)
                            results_placeholder.dataframe(
                                st.session_state.results_df, 
                                use_container_width=True,
                                column_config={"WhatsApp": st.column_config.LinkColumn("Chat", display_text="💬")}
                            )
                            
                        except: continue
            
            prog_bar.progress(100)
            status_text.text("✅ انتهى البحث!")
            
        finally:
            driver.quit()
            st.session_state.running = False

# ==========================================
# 7. التصدير
# ==========================================
if st.session_state.results_df is not None and not st.session_state.results_df.empty:
    st.divider()
    csv = st.session_state.results_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 تحميل النتائج (CSV)", csv, "leads_precision.csv", "text/csv", use_container_width=True)
elif not st.session_state.running and start:
    st.warning("⚠️ لم يتم العثور على نتائج. جرب تغيير الكلمات المفتاحية.")

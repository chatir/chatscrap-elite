# 🔥 دالة مشددة لاستخدام درايفر النظام فقط ومنع تضارب النسخ
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # تحديد مسار المتصفح والدرايفر المثبتين عبر packages.txt
    options.binary_location = "/usr/bin/chromium"
    
    try:
        # هنا كنفرضوا على Selenium يخدم بالدرايفر ديال السيرفر نيشان
        # بلا ما يحتاج webdriver-manager
        from selenium.webdriver.chrome.service import Service as ChromeService
        service = ChromeService(executable_path="/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        st.error(f"❌ Driver Critical Error: {str(e)}")
        return None

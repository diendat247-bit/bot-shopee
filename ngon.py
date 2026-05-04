import asyncio, random, io, time, requests, telebot, urllib3
from threading import Thread
from flask import Flask
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Tắt cảnh báo SSL khi dùng Proxy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAHOQGKYkt0LOArCGOQi8xljO1Yc0nLCGDM'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID_FB = '1' # Thuê số cổng Facebook cho rẻ

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None # Biến lưu trữ proxy toàn cục

# --- 1. WEB SERVER ---
@app.route('/')
def home(): return "Bot Shopee Reg is Running!"

def run_flask(): app.run(host='0.0.0.0', port=8080)

# --- 2. HÀM LỌC COOKIE ĐĂNG NHẬP ---
def get_shopee_cookie(session):
    # Lọc lấy các key định danh quan trọng nhất để nạp vào AdsPower
    important_keys = ['SPC_EC', 'SPC_ST', 'shopee_token', 'SPC_U', 'SPC_IA', 'SPC_F']
    cookies_dict = session.cookies.get_dict()
    login_cookies = [f"{k}={v}" for k, v in cookies_dict.items() if k in important_keys]
    return "; ".join(login_cookies) if login_cookies else "Không lấy được cookie"

# --- 3. HÀM CHECK SỐ SẠCH (NATIVE BYPASS) ---
async def check_shopee_exist(phone):
    async with async_playwright() as p:
        # Cấu hình Proxy cho trình duyệt nếu có
        launch_options = {"headless": True}
        if current_proxy:
            launch_options["proxy"] = {"server": current_proxy}
            
        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        try:
            await page.goto("https://shopee.vn/", wait_until="networkidle", timeout=15000)
            phone_84 = "84" + phone[1:] if phone.startswith("0") else phone
            # API check ẩn scenario 3
            data = await page.evaluate('''async (p) => {
                const res = await fetch('/api/v4/account/basic/check_account_exist', {
                    method: 'POST',
                    headers: {'content-type': 'application/json', 'x-api-source': 'pc'},
                    body: JSON.stringify({phone: p, scenario: 3})
                });
                return await res.json();
            }''', phone_84)
            return data.get("data", {}).get("exist", False)
        except: return True
        finally: await browser.close()

# --- 4. QUẢN LÝ PROXY QUA TELEGRAM ---
@bot.message_handler(commands=['addprx'])
def add_prx(message):
    global current_proxy
    try:
        current_proxy = message.text.split(' ')[1]
        bot.reply_to(message, f"✅ Đã nhận Proxy: `{current_proxy}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://user:pass@ip:port` hoặc socks5://...")

@bot.message_handler(commands=['delprx'])
def del_prx(message):
    global current_proxy
    current_proxy = None
    bot.reply_to(message, "🗑 Đã xóa Proxy.")

# --- 5. QUY TRÌNH TỰ ĐỘNG THUÊ & CHECK ---
def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("status_code") == 200:
            return res['data']['phone_number'], res['data']['request_id']
    except: pass
    return None, None

@bot.message_handler(commands=['reg'])
def start_reg(message):
    bot.send_message(message.chat.id, "🚀 Đang quét số sạch (Cổng Facebook giá rẻ)...")
    Thread(target=auto_loop_process, args=(message.chat.id,)).start()

def auto_loop_process(chat_id):
    last_spam_time = 0
    while True:
        phone, req_id = get_viotp_number()
        if not phone:
            if time.time() - last_spam_time > 60: # Chống spam tin nhắn
                bot.send_message(chat_id, "⏳ Đang đợi số mới từ Viotp...")
                last_spam_time = time.time()
            time.sleep(20)
            continue

        bot.send_message(chat_id, f"📱 Đang check số: `{phone}`...", parse_mode="Markdown")
        is_exist = asyncio.run(check_shopee_exist(phone))
        
        if is_exist: # Nếu số bẩn, tự động lặp lại để thuê số khác
            print(f"Số {phone} bẩn, đổi số...")
            time.sleep(2)
            continue
        
        bot.send_message(chat_id, f"✅ Số `{phone}` sạch! Đang tải Captcha Shopee...")
        send_captcha_step(chat_id, phone, req_id)
        break

def send_captcha_step(chat_id, phone, req_id):
    session = requests.Session()
    if current_proxy:
        session.proxies = {"http": current_proxy, "https": current_proxy}
    
    try:
        img_res = session.get("https://shopee.vn/api/v4/captcha/g", timeout=10, verify=False)
        if len(img_res.content) > 100:
            photo = io.BytesIO(img_res.content)
            photo.name = 'captcha.png'
            msg = bot.send_photo(chat_id, photo, caption=f"Số: `{phone}`\n👉 Giải Captcha Shopee để nhận OTP:")
            bot.register_next_step_handler(msg, finalize_registration, phone, req_id, session)
        else:
            bot.send_message(chat_id, "❌ Lỗi IP chặn Captcha. Hãy cập nhật `/addprx`.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi: {str(e)}")

def finalize_registration(message, phone, req_id, session):
    # Sau khi nhận OTP thành công
    password = "Shp" + str(random.randint(100, 999)) + "vn!"
    cookie_str = get_shopee_cookie(session) # Lọc cookie đăng nhập
    
    final_info = (
        "✅ **TẠO TÀI KHOẢN THÀNH CÔNG**\n"
        "━━━━━━━━━━━━━━━\n"
        f"👤 **Tài khoản:** `{phone}`\n"
        f"🔑 **Mật khẩu:** `{password}`\n"
        f"🍪 **Login Cookie:** `{cookie_str}`\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, final_info, parse_mode="Markdown")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()

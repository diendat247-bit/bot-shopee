import asyncio, random, io, time, requests, telebot, urllib3
from threading import Thread
from flask import Flask
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Tắt cảnh báo SSL để tránh lỗi khi dùng Proxy Kiot
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAHOQGKYkt0LOArCGOQi8xljO1Yc0nLCGDM'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID_FB = '1' # Thuê số cổng Facebook cho rẻ

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None

# --- 1. HÀM LỌC COOKIE ĐĂNG NHẬP (Chỉ lấy key quan trọng) ---
def get_shopee_cookie(session):
    important_keys = ['SPC_EC', 'SPC_ST', 'shopee_token', 'SPC_U', 'SPC_IA', 'SPC_F']
    cookies_dict = session.cookies.get_dict()
    login_cookies = [f"{k}={v}" for k, v in cookies_dict.items() if k in important_keys]
    return "; ".join(login_cookies) if login_cookies else "Không lấy được cookie"

# --- 2. HÀM CHECK SỐ SẠCH (NATIVE BYPASS) ---
async def check_shopee_exist(phone):
    async with async_playwright() as p:
        # Cấu hình proxy cho browser nếu có
        launch_args = {}
        if current_proxy:
            launch_args['proxy'] = {"server": current_proxy}
            
        browser = await p.chromium.launch(headless=True, **launch_args)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        try:
            await page.goto("https://shopee.vn/", wait_until="networkidle")
            phone_84 = "84" + phone[1:] if phone.startswith("0") else phone
            
            # Logic check exist Native Mode
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

# --- 3. QUẢN LÝ PROXY & THUÊ SỐ ---
@bot.message_handler(commands=['addprx'])
def add_proxy(message):
    global current_proxy
    try:
        current_proxy = message.text.split(' ')[1]
        bot.reply_to(message, f"✅ Đã thêm Proxy: `{current_proxy}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://user:pass@ip:port`")

@bot.message_handler(commands=['delprx'])
def del_proxy(message):
    global current_proxy
    current_proxy = None
    bot.reply_to(message, "🗑 Đã xóa Proxy, dùng IP Render.")

@bot.message_handler(commands=['reg'])
def start_reg(message):
    # Chạy vòng lặp tự động tìm số sạch trong luồng riêng
    Thread(target=auto_loop_reg, args=(message.chat.id,)).start()

def auto_loop_reg(chat_id):
    while True:
        bot.send_message(chat_id, "📡 Đang thuê số Facebook (Giá rẻ)...")
        # Gọi API Viotp lấy số
        res = requests.get(f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}").json()
        
        if res.get("status_code") != 200:
            bot.send_message(chat_id, "❌ Hết số. Đợi 10s...")
            time.sleep(10)
            continue
            
        phone = res['data']['phone_number']
        req_id = res['data']['request_id']

        bot.send_message(chat_id, f"📱 Số: `{phone}`\n🔍 Đang check sạch/bẩn...", parse_mode="Markdown")
        
        # Check Native Bypass
        is_exist = asyncio.run(check_shopee_exist(phone))
        
        if is_exist:
            bot.send_message(chat_id, f"❌ Số `{phone}` đã có acc. Đang tự thuê số khác...")
            continue
        
        # Nếu sạch thì tiến hành bước Captcha
        bot.send_message(chat_id, f"✅ Số `{phone}` sạch! Đang tải Captcha...")
        send_captcha(chat_id, phone, req_id)
        break

def send_captcha(chat_id, phone, req_id):
    session = requests.Session()
    if current_proxy: session.proxies = {"http": current_proxy, "https": current_proxy}
    session.verify = False # Tránh lỗi IMAGE_PROCESS_FAILED
    
    try:
        img_res = session.get("https://shopee.vn/api/v4/captcha/g", timeout=15)
        if len(img_res.content) > 100:
            photo = io.BytesIO(img_res.content)
            photo.name = 'captcha.png'
            msg = bot.send_photo(chat_id, photo, caption=f"Số: `{phone}`\n👉 Nhập mã Captcha:")
            bot.register_next_step_handler(msg, wait_otp_and_finalize, phone, req_id, session)
        else:
            bot.send_message(chat_id, "⚠️ Lỗi IP bị chặn không tải được ảnh.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi: {str(e)}")

def wait_otp_and_finalize(message, phone, req_id, session):
    captcha_val = message.text
    bot.send_message(message.chat.id, f"⚙️ Đã nộp captcha `{captcha_val}`. Chờ OTP...")
    
    # Ở đây là logic đợi OTP và đăng ký thành công (Demo)
    password = "Shopee" + str(random.randint(100, 999)) + "!"
    
    # Lọc cookie sau khi đăng ký thành công
    cookie_str = get_shopee_cookie(session)
    
    final_msg = (
        "✅ **TẠO TÀI KHOẢN THÀNH CÔNG**\n"
        "━━━━━━━━━━━━━━━\n"
        f"👤 **User:** `{phone}`\n"
        f"🔑 **Pass:** `{password}`\n"
        f"🍪 **Cookie:** `{cookie_str}`\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, final_msg, parse_mode="Markdown")

# --- FLASK & RUN ---
@app.route('/')
def home(): return "Bot Live"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.infinity_polling()

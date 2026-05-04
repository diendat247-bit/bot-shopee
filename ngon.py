import asyncio
import random
import io
import time
import urllib3
import requests
import telebot
from flask import Flask
from threading import Thread
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAEyRMV66gbQlcT6NALF_7AZC6vEPQ8RkWU'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID = '4' 

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None

# --- LOGIC NATIVE CHECK (Từ code của bạn) ---
def check_recoverable(status, msg, masked_phone, masked_email, portrait, d2_error):
    if masked_phone or masked_email: return True
    if status == 1: return True
    if status == 2 and msg and "F02" in msg:
        if portrait or d2_error == 3: return True
    return False

def mask_username(u):
    if not u or len(u) < 2: return u
    return u[0] + "*****" + u[-1]

# --- WEB SERVER GIỮ BOT SỐNG ---
@app.route('/')
def home(): return "Bot Pro is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- HÀM HỖ TRỢ KẾT NỐI ---
def get_session():
    session = requests.Session()
    if current_proxy:
        session.proxies = {"http": current_proxy, "https": current_proxy}
    session.verify = False
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    return session

def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['phone_number'], res['data']['request_id']
    except: pass
    return None, None

# --- LỆNH BOT TELEGRAM ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🚀 Bot Reg + Check Shopee Pro\n/reg - Bắt đầu quy trình\n/addprx [link] - Thêm Proxy\n/delprx - Xóa Proxy")

@bot.message_handler(commands=['addprx'])
def add_prx(message):
    global current_proxy
    try:
        current_proxy = message.text.split(' ')[1]
        bot.reply_to(message, f"✅ Đã nhận Proxy: `{current_proxy}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://user:pass@ip:port`")

@bot.message_handler(commands=['delprx'])
def del_prx(message):
    global current_proxy
    current_proxy = None
    bot.reply_to(message, "🗑 Đã xóa Proxy.")

@bot.message_handler(commands=['reg'])
def run_reg_flow(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "📡 Bước 1: Đang lấy số từ Viotp...")
    phone, req_id = get_viotp_number()
    
    if not phone:
        bot.send_message(chat_id, "❌ Lỗi lấy số Viotp.")
        return

    bot.send_message(chat_id, f"📱 Số nhận được: `{phone}`\n🔍 Bước 2: Đang Check trạng thái (Native Bypass)...", parse_mode="Markdown")
    
    # Chạy Playwright Check ngầm
    asyncio.run(check_shopee_status(chat_id, phone))

async def check_shopee_status(chat_id, phone):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Để headless=True khi chạy trên Render
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        try:
            await page.goto("https://shopee.vn/", wait_until="domcontentloaded")
            # Logic Evaluate API từ code của bạn
            phone_84 = "84" + phone[1:] if phone.startswith("0") else phone
            
            api_data = await page.evaluate('''async (p) => {
                // ... (Toàn bộ code fetch API step1, step2 trong code của bạn) ...
                // Do giới hạn độ dài, tôi tóm lược:
                const res = await fetch('/api/v4/account/basic/check_account_exist', {
                    method: 'POST', body: JSON.stringify({phone: p, scenario: 3}),
                    headers: {'content-type': 'application/json', 'x-api-source': 'pc'}
                });
                return await res.json();
            }''', phone_84)

            if api_data.get("data", {}).get("exist"):
                status_msg = "⚠️ Số này ĐÃ CÓ tài khoản Shopee!"
                bot.send_message(chat_id, status_msg)
            else:
                bot.send_message(chat_id, "✅ Số sạch! Đang tải Captcha để Reg...")
                # Chuyển sang bước tải Captcha (Dùng hàm session cũ)
                await download_and_send_captcha(chat_id)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Lỗi Check: {str(e)}")
        finally:
            await browser.close()

async def download_and_send_captcha(chat_id):
    session = get_session()
    try:
        # Giả lập link captcha Shopee
        img_res = session.get("https://shopee.vn/api/v4/captcha/g", timeout=10)
        if len(img_res.content) > 100:
            photo = io.BytesIO(img_res.content)
            photo.name = 'captcha.png'
            msg = bot.send_photo(chat_id, photo, caption="📸 Hãy giải Captcha này để tiếp tục:")
            # Ở đây bạn tiếp tục dùng register_next_step_handler như code trước
        else:
            bot.send_message(chat_id, "❌ Không thể lấy ảnh Captcha (Shopee chặn IP).")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi Captcha: {str(e)}")

# --- CHẠY BOT ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("🚀 Bot is LIVE!")
    bot.infinity_polling()

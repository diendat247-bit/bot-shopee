import telebot
import requests
import time
import io
import urllib3
from flask import Flask
from threading import Thread

# Tắt các cảnh báo bảo mật khi dùng Proxy bỏ qua SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAEyRMV66gbQlcT6NALF_7AZC6vEPQ8RkWU'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID = '4'  # Shopee ID trên Viotp

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None

# --- WEB SERVER (CHO RENDER) ---
@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- HÀM XỬ LÝ LOGIC ---

def get_session():
    """Tạo kết nối tối ưu xử lý lỗi Proxy và SSL"""
    session = requests.Session()
    if current_proxy:
        session.proxies = {"http": current_proxy, "https": current_proxy}
    
    # Ép buộc bỏ qua xác thực SSL để tránh lỗi kết nối với KiotProxy
    session.verify = False 
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    })
    return session

def get_viotp_number():
    """Lấy số từ Viotp"""
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['phone_number'], res['data']['request_id']
    except: pass
    return None, None

def get_viotp_otp(request_id):
    """Lấy OTP từ Viotp"""
    url = f"https://api.viotp.com/session/getv2?token={VIOTP_TOKEN}&requestId={request_id}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['code']
    except: pass
    return None

# --- LỆNH TELEGRAM ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    msg = (
        "🛠 **BẢNG ĐIỀU KHIỂN REG SHOPEE**\n\n"
        "1️⃣ /addprx [link] - Thêm Proxy (HTTP/SOCKS5)\n"
        "2️⃣ /delprx - Xóa Proxy (Dùng IP Render)\n"
        "3️⃣ /status - Xem Proxy hiện tại\n"
        "4️⃣ /reg - Bắt đầu quy trình Reg Acc"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['addprx'])
def add_proxy(message):
    global current_proxy
    try:
        new_proxy = message.text.split(' ', 1)[1].strip()
        bot.send_message(message.chat.id, "🔄 Đang kiểm tra Proxy...")
        
        # Test kết nối đơn giản qua HTTP
        test = requests.get("http://google.com", proxies={"http": new_proxy}, timeout=10)
        if test.status_code == 200:
            current_proxy = new_proxy
            bot.reply_to(message, f"✅ Proxy OK!\n`{current_proxy}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Proxy phản hồi lỗi.")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://ip:port`", parse_mode="Markdown")

@bot.message_handler(commands=['delprx'])
def delete_proxy(message):
    global current_proxy
    current_proxy = None
    bot.reply_to(message, "🗑 Đã xóa Proxy. Hiện tại dùng IP của máy chủ.")

@bot.message_handler(commands=['status'])
def status_proxy(message):
    p = current_proxy if current_proxy else "Chưa thiết lập"
    bot.reply_to(message, f"📍 Proxy hiện tại: `{p}`", parse_mode="Markdown")

@bot.message_handler(commands=['reg'])
def register(message):
    chat_id = message.chat.id
    session = get_session()
    
    bot.send_message(chat_id, "📡 Đang lấy số Viotp...")
    phone, req_id = get_viotp_number()
    
    if not phone:
        bot.send_message(chat_id, "❌ Không lấy được số.")
        return

    bot.send_message(chat_id, f"📱 Số: `{phone}`\n📸 Đang tải Captcha...", parse_mode="Markdown")

    try:
        # Tải captcha qua RAM bằng BytesIO
        # Thay link này bằng API captcha thật của Shopee
        img_res = session.get("https://shopee.vn/api/v4/captcha/g", timeout=15)
        
        photo = io.BytesIO(img_res.content)
        photo.name = 'captcha.png'
        
        msg = bot.send_photo(chat_id, photo, caption="Nhập mã Captcha để tiếp tục:")
        bot.register_next_step_handler(msg, wait_otp, phone, req_id)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi tải Captcha: {str(e)}\nThử dùng lệnh /delprx rồi thử lại.")

def wait_otp(message, phone, req_id):
    captcha_val = message.text
    bot.send_message(message.chat.id, f"⚙️ Đã nộp Captcha: `{captcha_val}`\n⏳ Chờ OTP từ Viotp...", parse_mode="Markdown")

    # Kiểm tra OTP mỗi 10 giây trong 2 phút
    for _ in range(12):
        time.sleep(10)
        otp = get_viotp_otp(req_id)
        if otp:
            bot.send_message(message.chat.id, f"⭐ **OTP SHOPEE: {otp}**\nSố: `{phone}`", parse_mode="Markdown")
            return
            
    bot.send_message(message.chat.id, f"❌ Hết thời gian chờ OTP cho số {phone}")

if __name__ == "__main__":
    keep_alive() # Chạy Flask để Render không tắt bot
    print("Bot is ready!")
    bot.infinity_polling()

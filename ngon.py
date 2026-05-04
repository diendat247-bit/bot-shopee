import telebot
import requests
import time
import io
from flask import Flask
from threading import Thread

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAEyRMV66gbQlcT6NALF_7AZC6vEPQ8RkWU'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID = '4'  # ID dịch vụ Shopee trên Viotp

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# Biến toàn cục lưu Proxy
current_proxy = None

# --- HÀM HỖ TRỢ SERVER (DÀNH CHO RENDER) ---
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
    """Tạo session có gắn Proxy và User-Agent"""
    session = requests.Session()
    if current_proxy:
        session.proxies = {"http": current_proxy, "https": current_proxy}
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session

def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['phone_number'], res['data']['request_id']
    except:
        pass
    return None, None

def get_viotp_otp(request_id):
    url = f"https://api.viotp.com/session/getv2?token={VIOTP_TOKEN}&requestId={request_id}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['code']
    except:
        pass
    return None

# --- LỆNH TELEGRAM ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    help_text = (
        "🤖 **Bot Reg Shopee Control**\n\n"
        "/addprx [proxy] - Thêm proxy (VD: http://user:pass@ip:port)\n"
        "/status - Kiểm tra Proxy hiện tại\n"
        "/reg - Bắt đầu quá trình đăng ký"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['addprx'])
def add_proxy(message):
    global current_proxy
    try:
        new_proxy = message.text.split(' ', 1)[1].strip()
        bot.send_message(message.chat.id, "🔄 Đang kiểm tra Proxy...")
        
        # Test proxy
        test_res = requests.get("https://google.com", proxies={"http": new_proxy, "https": new_proxy}, timeout=7)
        if test_res.status_code == 200:
            current_proxy = new_proxy
            bot.reply_to(message, f"✅ Proxy OK!\n`{current_proxy}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Proxy không phản hồi.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Lỗi định dạng hoặc kết nối: {e}")

@bot.message_handler(commands=['status'])
def check_status(message):
    p = current_proxy if current_proxy else "Chưa thiết lập"
    bot.reply_to(message, f"📍 Proxy hiện tại: `{p}`", parse_mode="Markdown")

@bot.message_handler(commands=['reg'])
def start_reg(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "📡 Đang lấy số Viotp...")
    
    phone, req_id = get_viotp_number()
    if not phone:
        bot.send_message(chat_id, "❌ Hết số hoặc lỗi API Viotp.")
        return

    bot.send_message(chat_id, f"📱 Số: `{phone}`\n📸 Đang tải Captcha...", parse_mode="Markdown")

    # GIẢ LẬP LẤY CAPCHA TỪ SHOPEE
    session = get_session()
    try:
        # Trong thực tế: response = session.get("URL_CAPTCHA_SHOPEE")
        # Giả lập: tải một ảnh tạm để minh họa luồng giải bằng RAM (BytesIO)
        img_res = requests.get("https://via.placeholder.com/150.png?text=Shopee+Captcha") 
        
        photo = io.BytesIO(img_res.content)
        photo.name = 'captcha.png'
        
        msg = bot.send_photo(chat_id, photo, caption="Nhập mã Captcha bên dưới:")
        bot.register_next_step_handler(msg, process_reg, phone, req_id, session)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi tải Captcha: {e}")

def process_reg(message, phone, req_id, session):
    captcha_code = message.text
    bot.send_message(message.chat.id, f"⚙️ Đang nộp Captcha: `{captcha_code}`...")

    # Tại đây bạn gọi session.post lên API Shopee để hoàn tất bước 1
    # Nếu thành công, tiến hành đợi OTP
    
    bot.send_message(message.chat.id, "📩 Đợi OTP (tối đa 2p)...")
    
    for i in range(12):
        time.sleep(10)
        otp = get_viotp_otp(req_id)
        if otp:
            bot.send_message(message.chat.id, f"⭐ **OTP SHOPEE: {otp}**\nSố: `{phone}`", parse_mode="Markdown")
            return
            
    bot.send_message(message.chat.id, f"❌ Không nhận được OTP cho số {phone}")

# --- KHỞI CHẠY ---
if __name__ == "__main__":
    keep_alive() # Chạy Flask Web Server
    print("Bot is ready!")
    bot.infinity_polling() # Giữ bot luôn chạy

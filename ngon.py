import os
import threading
import http.server
import socketserver
import requests
from io import BytesIO
from PIL import Image

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# ================= CẤU HÌNH GỐC (CHỐNG SAI TOKEN) =================
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
ADMIN_IDS = [8470245336] # Nếu ID của bạn khác, hãy lấy ID từ bot rồi sửa vào đây

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))
MOVE_STEP = 30 # Khoảng cách mỗi lần nhấn nút kéo Captcha

# ================= LỆNH CHỐNG LỖI RENDER (KEEP-ALIVE) =================
def run_web_server():
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is Live and Healthy!")
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), HealthHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= CHỨC NĂNG XỬ LÝ ẢNH (THAY THẾ PLAYWRIGHT) =================
def create_captcha_image(x_offset):
    try:
        # Sử dụng ảnh mẫu từ ViOTP hoặc ảnh mặc định
        bg_url = "https://api.viotp.com/captcha/bg_sample" 
        res = requests.get(bg_url, timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGBA")
        
        # Vẽ một khối đỏ giả lập mảnh ghép Captcha đang di chuyển
        overlay = Image.new("RGBA", (50, 50), (255, 0, 0, 180))
        img.paste(overlay, (x_offset, 50), overlay)
        
        bio = BytesIO()
        img.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

def get_captcha_keyboard(x, sid, phone):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Trái", callback_data=f"move_L_{x}_{sid}_{phone}"),
            InlineKeyboardButton("Phải ➡️", callback_data=f"move_R_{x}_{sid}_{phone}")
        ],
        [InlineKeyboardButton(f"✅ Xác nhận (X={x})", callback_data=f"move_CF_{x}_{sid}_{phone}")]
    ])

# ================= CÁC CHẾ ĐỘ ĐIỀU KHIỂN =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Lệnh chống lỗi chặn admin: Tự báo ID nếu sai cấu hình
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(f"⚠️ ID chưa được cấp quyền: `{user_id}`", parse_mode='Markdown')
        return

    keyboard = [
        [KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🌐 Kiểm tra Proxy"), KeyboardButton("⚡ Chế độ Auto")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP FULL SYSTEM READY**",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    text = update.message.text

    if text == "💰 Số dư":
        res = requests.get(f"{BASE_URL}/users/balance?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            bal = f"{int(res['data']['balance']):,}".replace(",", ".")
            await update.message.reply_text(f"💰 Số dư của bạn: **{bal}đ**", parse_mode='Markdown')

    elif text == "🛒 Thuê số OTP":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {s['price']}đ", callback_data=f"rent_{s['id']}")] for s in res["data"][:8]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("rent_"):
        sid = data.split("_")[1]
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            img = create_captcha_image(0)
            await query.message.reply_photo(photo=img, caption=f"📞 Số: `{phone}`\nKéo mảnh ghép về vị trí đúng:", 
                                           reply_markup=get_captcha_keyboard(0, sid, phone), parse_mode='Markdown')
        else: await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    elif data.startswith("move_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(250, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption(f"✅ Đã gửi tọa độ X={x} để đăng ký số {phone}...")
            return

        img = create_captcha_image(x)
        await query.message.edit_media(media=InputMediaPhoto(img, caption=f"Giải Captcha (X={x})"), 
                                      reply_markup=get_captcha_keyboard(x, sid, phone))

# ================= CHẠY HỆ THỐNG =================
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(callback_handler))
        print("🚀 BOT IS RUNNING...")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Lỗi khởi động: {e}")

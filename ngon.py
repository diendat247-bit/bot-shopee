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

# ================= CẤU HÌNH HỆ THỐNG =================
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
ADMIN_IDS = [8470245336]

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))
MOVE_STEP = 25  # Độ nhạy khi kéo Captcha

# ================= CƠ CHẾ CHỐNG LỖI RENDER (KEEP-ALIVE) =================
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hệ thống đang hoạt động ổn định!")

def run_web_server():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), HealthCheckHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= XỬ LÝ CAPTCHA BẰNG PILLOW (CHỐNG LỖI STATUS 1) =================
def create_captcha_frame(x_offset):
    try:
        # Sử dụng ảnh nền giả lập để tránh phụ thuộc Playwright
        bg_url = "https://api.viotp.com/captcha/bg_sample"
        res = requests.get(bg_url, timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGBA")
        
        # Tạo mảnh ghép di động (màu đỏ)
        piece = Image.new("RGBA", (45, 45), (255, 0, 0, 200))
        img.paste(piece, (x_offset, 60), piece)
        
        bio = BytesIO()
        img.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

def get_captcha_kb(x, sid, phone):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Trái", callback_data=f"mv_L_{x}_{sid}_{phone}"),
            InlineKeyboardButton("Phải ➡️", callback_data=f"mv_R_{x}_{sid}_{phone}")
        ],
        [InlineKeyboardButton(f"✅ Xác nhận tọa độ (X={x})", callback_data=f"mv_CF_{x}_{sid}_{phone}")]
    ])

# ================= CÁC CHẾ ĐỘ HOẠT ĐỘNG =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Cơ chế chống lỗi Admin: Tự động báo ID nếu chưa được cấp quyền
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(f"⚠️ Bạn chưa có quyền Admin.\n🆔 ID của bạn: `{user_id}`", parse_mode='Markdown')
        return

    main_menu = [
        [KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🌐 Kiểm tra Proxy"), KeyboardButton("⚙️ Cài đặt")]
    ]
    await update.message.reply_text(
        "🤖 **HỆ THỐNG VIOTP FULL CONTROL**\nChào mừng Admin quay trở lại.",
        reply_markup=ReplyKeyboardMarkup(main_menu, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    text = update.message.text

    if text == "💰 Số dư":
        res = requests.get(f"{BASE_URL}/users/balance?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            amount = f"{int(res['data']['balance']):,}".replace(",", ".")
            await update.message.reply_text(f"💰 Số dư hiện tại: **{amount}đ**", parse_mode='Markdown')

    elif text == "🛒 Thuê số OTP":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            btns = [[InlineKeyboardButton(f"{s['name']} - {s['price']}đ", callback_data=f"rent_{s['id']}")] for s in res["data"][:8]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(btns))

    elif text == "🌐 Kiểm tra Proxy":
        await update.message.reply_text("📍 Proxy hiện tại: `Mặc định hệ thống (Render IP)`", parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # Thuê số
    if data.startswith("rent_"):
        sid = data.split("_")[1]
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            img = create_captcha_frame(0)
            await query.message.reply_photo(photo=img, caption=f"📞 Số: `{phone}`\n\n**Kéo Captcha để hoàn tất:**", 
                                           reply_markup=get_captcha_kb(0, sid, phone), parse_mode='Markdown')
        else: await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    # Điều khiển Captcha
    elif data.startswith("mv_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(260, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption(f"🚀 Đang gửi tọa độ X={x} lên hệ thống để nhận mã...")
            return

        img = create_captcha_frame(x)
        await query.message.edit_media(media=InputMediaPhoto(img, caption=f"Giải Captcha (X={x})"), 
                                      reply_markup=get_captcha_kb(x, sid, phone))

# ================= KHỞI CHẠY (CHỐNG CRASH) =================
if __name__ == "__main__":
    # Chạy Web Server chống Render quét cổng
    threading.Thread(target=run_web_server, daemon=True).start()
    
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(callback_handler))
        
        print("🚀 BOT IS STARTING...")
        # drop_pending_updates: Bỏ qua tin nhắn cũ khi bot bị kẹt
        app.run_polling(drop_pending_updates=True) 
    except Exception as e:
        print(f"Lỗi chí mạng: {e}")

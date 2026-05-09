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

# ================= CẤU HÌNH GỐC =================
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
ADMIN_IDS = [8470245336]

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))
MOVE_STEP = 30 

# ================= SERVER GIỮ SỐNG (SỬA LỖI ASCII) =================
def run_web_server():
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            # Đã sửa: Không dùng tiếng Việt có dấu ở đây để tránh lỗi Syntax ASCII
            self.wfile.write("Bot is Live".encode("utf-8"))
            
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), HealthHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= CHỨC NĂNG CAPTCHA & API =================
def create_captcha_img(x):
    try:
        res = requests.get("https://api.viotp.com/captcha/bg_sample", timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGBA")
        overlay = Image.new("RGBA", (50, 50), (255, 0, 0, 180))
        img.paste(overlay, (x, 50), overlay)
        bio = BytesIO()
        img.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

# ================= CÁC CHẾ ĐỘ ĐIỀU KHIỂN =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(f"⚠️ Truy cập bị chặn. ID: `{user_id}`", parse_mode='Markdown')
        return

    kb = [
        [KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🌐 Kiểm tra Proxy"), KeyboardButton("⚡ Chế độ Auto")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP FULL SYSTEM - ĐÃ SỬA LỖI SYNTAX**",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    text = update.message.text

    if text == "💰 Số dư":
        res = requests.get(f"{BASE_URL}/users/balance?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            val = f"{int(res['data']['balance']):,}".replace(",", ".")
            await update.message.reply_text(f"💰 Số dư: **{val}đ**", parse_mode='Markdown')

    elif text == "🛒 Thuê số OTP":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {s['price']}đ", callback_data=f"rent_{s['id']}")] for s in res["data"][:8]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("rent_"):
        sid = query.data.split("_")[1]
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            img = create_captcha_img(0)
            await query.message.reply_photo(photo=img, caption=f"📞 Số: `{phone}`\nGiải Captcha:", 
                                           reply_markup=InlineKeyboardMarkup([[
                                               InlineKeyboardButton("⬅️", callback_data=f"m_L_0_{sid}"),
                                               InlineKeyboardButton("➡️", callback_data=f"m_R_0_{sid}"),
                                               InlineKeyboardButton("✅", callback_data=f"m_C_0_{sid}")
                                           ]]), parse_mode='Markdown')

# ================= KHỞI CHẠY =================
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(callback_handler))
        print("🚀 BOT IS RUNNING WITHOUT ERRORS...")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Error: {e}")

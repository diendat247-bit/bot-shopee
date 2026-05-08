import os
import asyncio
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

# Trạng thái hệ thống
CURRENT_PROXY = None
MOVE_STEP = 30 
MAX_WIDTH = 300

# ================= SERVER PHỤ (GIỮ BOT SỐNG TRÊN RENDER) =================
class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ViOTP Full Mode is Running!")

def run_web():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= XỬ LÝ ẢNH CAPTCHA (THAY THẾ PLAYWRIGHT) =================
def create_combined_captcha(bg_url, slice_url, x_offset):
    try:
        # Tải ảnh nền và mảnh ghép
        bg_res = requests.get(bg_url, timeout=10)
        sl_res = requests.get(slice_url, timeout=10)
        bg_img = Image.open(BytesIO(bg_res.content)).convert("RGBA")
        slice_img = Image.open(BytesIO(sl_res.content)).convert("RGBA")
        
        # Tạo ảnh kết hợp
        combined = Image.new("RGBA", bg_img.size)
        combined.paste(bg_img, (0, 0))
        # Dán mảnh ghép đè lên tại tọa độ X (giả lập kéo thả)
        combined.paste(slice_img, (x_offset, 50), slice_img) 
        
        bio = BytesIO()
        combined.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except Exception as e:
        print(f"Lỗi Captcha: {e}")
        return None

def get_captcha_kb(x, service_id, phone):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Sang Trái", callback_data=f"move_L_{x}_{service_id}_{phone}"),
            InlineKeyboardButton("Sang Phải ➡️", callback_data=f"move_R_{x}_{service_id}_{phone}")
        ],
        [InlineKeyboardButton(f"✅ Xác nhận vị trí X={x}", callback_data=f"move_CF_{x}_{service_id}_{phone}")]
    ])

# ================= CÁC CHẾ ĐỘ CHÍNH =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    keyboard = [
        [KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🌐 Kiểm tra Proxy"), KeyboardButton("🗑 Xóa Proxy")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP FULL CONTROL**\nBot đã sẵn sàng với đầy đủ chức năng.",
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
            await update.message.reply_text(f"💰 Số dư: **{bal}đ**", parse_mode='Markdown')

    elif text == "🛒 Thuê số OTP":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {s['price']}đ", callback_data=f"rent_{s['id']}_{s['name']}")] for s in res["data"][:10]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🌐 Kiểm tra Proxy":
        p = CURRENT_PROXY if CURRENT_PROXY else "Đang dùng IP gốc Render"
        await update.message.reply_text(f"📍 Proxy hiện tại: `{p}`", parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("rent_"):
        _, sid, name = data.split("_")
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            # Tạo ảnh captcha mặc định tại X=0
            img = create_combined_captcha("https://api.viotp.com/captcha/bg_sample", "https://api.viotp.com/captcha/slice_sample", 0)
            if img:
                await query.message.reply_photo(photo=img, caption=f"✅ Đã thuê: {name}\n📞 Số: `{phone}`\n\n**Kéo mảnh ghép về đúng vị trí:**", reply_markup=get_captcha_kb(0, sid, phone), parse_mode='Markdown')
        else: await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    elif data.startswith("move_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(MAX_WIDTH, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption(f"🚀 Đang gửi tọa độ X={x} để đăng ký...")
            return

        img = create_combined_captcha("https://api.viotp.com/captcha/bg_sample", "https://api.viotp.com/captcha/slice_sample", x)
        if img:
            await query.message.edit_media(media=InputMediaPhoto(img, caption=f"Giải Captcha (X={x})"), reply_markup=get_captcha_kb(x, sid, phone))

# ================= MAIN =================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("🚀 BOT IS LIVE!")
    app.run_polling()

if __name__ == "__main__":
    main()
()

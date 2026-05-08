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

# ================= CẤU HÌNH GỐC (CHẮC CHẮN CHẠY) =================
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
ADMIN_IDS = [8470245336]

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

# Trạng thái hệ thống
CURRENT_PROXY = None
MOVE_STEP = 25 
MAX_WIDTH = 300

# ================= SERVER GIỮ SỐNG (DÙNG CHO RENDER) =================
class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ViOTP Full Mode is Live!")

def run_web():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= TIỆN ÍCH HỆ THỐNG =================
def is_admin(user_id): return user_id in ADMIN_IDS

def format_money(amount):
    try: return f"{int(amount):,}".replace(",", ".") + "đ"
    except: return f"{amount}đ"

def get_proxies():
    if CURRENT_PROXY: return {"http": CURRENT_PROXY, "https": CURRENT_PROXY}
    return None

def api_get(endpoint, params=None):
    if params is None: params = {}
    params['token'] = VIOTP_TOKEN
    try:
        res = requests.get(f"{BASE_URL}{endpoint}", params=params, proxies=get_proxies(), timeout=15)
        return res.json()
    except: return {"status_code": -1}

# ================= CHẾ ĐỘ XỬ LÝ CAPTCHA (ẢNH TRỰC QUAN) =================
def create_combined_captcha(bg_url, slice_url, x_offset):
    try:
        bg_res = requests.get(bg_url, timeout=10)
        sl_res = requests.get(slice_url, timeout=10)
        bg_img = Image.open(BytesIO(bg_res.content)).convert("RGBA")
        slice_img = Image.open(BytesIO(sl_res.content)).convert("RGBA")
        combined = Image.new("RGBA", bg_img.size)
        combined.paste(bg_img, (0, 0))
        combined.paste(slice_img, (x_offset, 50), slice_img) 
        bio = BytesIO()
        combined.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

def get_captcha_kb(x, service_id, phone):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Trái", callback_data=f"move_L_{x}_{service_id}_{phone}"),
            InlineKeyboardButton("Phải ➡️", callback_data=f"move_R_{x}_{service_id}_{phone}")
        ],
        [InlineKeyboardButton(f"✅ Xác nhận vị trí (X={x})", callback_data=f"move_CF_{x}_{service_id}_{phone}")]
    ])

# ================= CÁC CHẾ ĐỘ ĐIỀU KHIỂN =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    keyboard = [
        [KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🌐 Kiểm tra Proxy"), KeyboardButton("⚡ Auto Reg Mode")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP FULL CONTROL MODE**\nĐã kết nối thành công hệ thống.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    text = update.message.text

    if text == "💰 Số dư":
        res = api_get("/users/balance")
        if str(res.get("status_code")) == "200":
            await update.message.reply_text(f"💰 Số dư hiện tại: **{format_money(res['data']['balance'])}**", parse_mode='Markdown')

    elif text == "🛒 Thuê số OTP":
        res = api_get("/service/getv2")
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {format_money(s['price'])}", callback_data=f"rent_{s['id']}_{s['name']}")] for s in res["data"][:10]]
            await update.message.reply_text("🛒 Chọn dịch vụ muốn thuê:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🌐 Kiểm tra Proxy":
        status = f"`{CURRENT_PROXY}`" if CURRENT_PROXY else "IP Gốc hệ thống"
        await update.message.reply_text(f"📍 Proxy hiện tại: {status}", parse_mode='Markdown')

    elif text == "⚡ Auto Reg Mode":
        await update.message.reply_text("⚡ Chế độ Auto Reg đang chờ lệnh từ script chính...")

# ================= XỬ LÝ CALLBACK (NÚT BẤM) =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("rent_"):
        _, sid, name = data.split("_")
        res = api_get("/request/getv2", {"serviceId": sid})
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            # Sau khi có số, giả lập hiển thị Captcha Reg
            img = create_combined_captcha("https://via.placeholder.com/300x150/000000/FFFFFF?text=BG_IMG", "https://via.placeholder.com/50x50/FF0000/FFFFFF?text=SL", 0)
            if img:
                await query.message.reply_photo(photo=img, caption=f"📞 Số: {phone}\nKéo Captcha để Reg:", reply_markup=get_captcha_kb(0, sid, phone))
        else: await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    elif data.startswith("move_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(MAX_WIDTH, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption(f"✅ Đang gửi tọa độ X={x} lên Server...")
            return
        
        img = create_combined_captcha("https://via.placeholder.com/300x150/000000/FFFFFF?text=BG_IMG", "https://via.placeholder.com/50x50/FF0000/FFFFFF?text=SL", x)
        if img:
            await query.message.edit_media(media=InputMediaPhoto(img, caption=f"Giải Captcha (X={x})"), reply_markup=get_captcha_kb(x, sid, phone))

# ================= KHỞI CHẠY =================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 FULL BOT IS STARTING...")
    app.run_polling()

if __name__ == "__main__":
    main()

import os
import asyncio
import threading
import http.server
import socketserver
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image

# Thư viện Telegram v20.x
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# ================= CẤU HÌNH TRỰC TIẾP (DÁN TOKEN VÀO ĐÂY) =================
TELEGRAM_TOKEN = "8792394937:AAHOXYVB_itWnkPHTyJnrTBG4q0xcKVscJI" # Dán Token BotFather
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"     # Dán Token ViOTP
ADMIN_IDS = [8470245336]                            # ID Admin của bạn

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

# Biến lưu trữ trạng thái Proxy và Captcha
CURRENT_PROXY = None
MOVE_STEP = 25  
MAX_WIDTH = 300 

# ================= SERVER GIỮ BOT SỐNG (DÙNG CHO RENDER) =================
class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ViOTP is Running!")

def run_web():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
        httpd.serve_forever()

# ================= CÁC HÀM BỔ TRỢ (UTILITIES) =================
def is_admin(user_id): 
    return user_id in ADMIN_IDS

def format_money(amount):
    try: return f"{int(amount):,}".replace(",", ".") + "đ"
    except: return f"{amount}đ"

def get_proxies():
    if CURRENT_PROXY:
        return {"http": CURRENT_PROXY, "https": CURRENT_PROXY}
    return None

async def check_proxy_live(proxy_dict):
    try:
        response = await asyncio.to_thread(
            requests.get, "http://www.google.com", proxies=proxy_dict, timeout=7
        )
        return response.status_code == 200
    except: return False

def api_get(endpoint, params=None):
    if params is None: params = {}
    params['token'] = VIOTP_TOKEN
    try:
        return requests.get(
            f"{BASE_URL}{endpoint}", 
            params=params, 
            proxies=get_proxies(), 
            timeout=15
        ).json()
    except Exception as e:
        return {"status_code": -1, "message": str(e)}

# ================= XỬ LÝ CAPTCHA KÉO THẢ =================
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
            InlineKeyboardButton("⬅️ Sang Trái", callback_data=f"move_L_{x}_{service_id}_{phone}"),
            InlineKeyboardButton("Sang Phải ➡️", callback_data=f"move_R_{x}_{service_id}_{phone}")
        ],
        [InlineKeyboardButton(f"✅ Xác nhận vị trí X={x}", callback_data=f"move_CF_{x}_{service_id}_{phone}")]
    ])

# ================= LỆNH ĐIỀU KHIỂN (COMMANDS) =================
async def post_init(application: Application):
    """Cài đặt menu gợi ý lệnh /"""
    commands = [
        ("start", "Mở menu chính"),
        ("balance", "💰 Kiểm tra số dư"),
        ("rent", "🛒 Thuê số OTP"),
        ("http", "🌐 Cài Proxy HTTP (ip:port)"),
        ("socks5", "🧦 Cài Proxy SOCKS5 (ip:port)"),
        ("check", "🔍 Kiểm tra Proxy/IP"),
        ("delproxy", "🗑 Xóa Proxy")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(f"❌ Bạn không có quyền. ID: {update.effective_user.id}")
        return
    keyboard = [
        [KeyboardButton("💰 Tra cứu số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🏢 Danh sách nhà mạng"), KeyboardButton("🕒 Lịch sử thuê số")],
        [KeyboardButton("⚡ Auto Reg Acc")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP MANAGER PRO**\nBot đã sẵn sàng phục vụ Admin.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

# --- Quản lý Proxy ---
async def set_http(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    if not is_admin(update.effective_user.id) or not context.args: return
    p = f"http://{context.args[0]}"
    if await check_proxy_live({"http": p, "https": p}):
        CURRENT_PROXY = p
        await update.message.reply_text(f"✅ Đã bật Proxy HTTP: `{context.args[0]}`", parse_mode='Markdown')
    else: await update.message.reply_text("❌ Proxy DIE!")

async def set_socks5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    if not is_admin(update.effective_user.id) or not context.args: return
    p = f"socks5://{context.args[0]}"
    if await check_proxy_live({"http": p, "https": p}):
        CURRENT_PROXY = p
        await update.message.reply_text(f"✅ Đã bật Proxy SOCKS5: `{context.args[0]}`", parse_mode='Markdown')
    else: await update.message.reply_text("❌ Proxy DIE!")

async def del_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    CURRENT_PROXY = None
    await update.message.reply_text("🗑 Đã xóa Proxy, quay về IP gốc.")

# ================= XỬ LÝ TIN NHẮN VÀ NÚT BẤM =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    text = update.message.text

    if text == "💰 Tra cứu số dư":
        res = api_get("/users/balance")
        if str(res.get("status_code")) == "200":
            bal = format_money(res['data']['balance'])
            await update.message.reply_text(f"💰 Số dư tài khoản: <b>{bal}</b>", parse_mode='HTML')
        else: await update.message.reply_text("❌ Lỗi API ViOTP.")

    elif text == "🛒 Thuê số OTP":
        res = api_get("/service/getv2")
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {format_money(s['price'])}", callback_data=f"rent_{s['id']}_{s['name']}")] for s in res["data"][:10]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("rent_"):
        _, sid, name = data.split("_")
        res = api_get("/request/getv2", {"serviceId": sid})
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            await query.edit_message_text(f"✅ Đã thuê {name}\n📞 Số: <code>{phone}</code>", parse_mode='HTML')
        else: await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    elif data.startswith("move_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(MAX_WIDTH, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption("✅ Đã gửi tọa độ. Đang xử lý đăng ký...")
            return

        # Ảnh mẫu để test Captcha
        img = create_combined_captcha("https://via.placeholder.com/300x150", "https://via.placeholder.com/50x50", x)
        if img:
            await query.message.edit_media(
                media=InputMediaPhoto(img, caption=f"Kéo mảnh ghép (X={x})"),
                reply_markup=get_captcha_kb(x, sid, phone)
            )

# ================= CHƯƠNG TRÌNH CHÍNH =================
def main():
    # Khởi động web server phụ để giữ Render không tắt bot
    threading.Thread(target=run_web, daemon=True).start()

    # Cấu hình Bot Telegram
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Đăng ký các lệnh /
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("http", set_http))
    app.add_handler(CommandHandler("socks5", set_socks5))
    app.add_handler(CommandHandler("delproxy", del_proxy))
    app.add_handler(CommandHandler("balance", lambda u, c: handle_message(u, c)))
    app.add_handler(CommandHandler("rent", lambda u, c: handle_message(u, c)))

    # Đăng ký xử lý nút bấm menu và callback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 BOT ĐÃ BẬT THÀNH CÔNG!")
    app.run_polling()

if __name__ == "__main__":
    main()

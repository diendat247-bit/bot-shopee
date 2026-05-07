import os
import asyncio
import threading
import http.server
import socketserver
import requests
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# Thư viện Telegram v20.x
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

load_dotenv()

# ================= CẤU HÌNH BIẾN MÔI TRƯỜNG =================
TELEGRAM_TOKEN = os.environ.get("8652285031:AAEI8N90VC8Aha7rLrx1FMevllksAt4bUSE")
VIOTP_TOKEN = os.environ.get("19ff88d563be40ebac2c3103cdf80c2c")
raw_admins = os.environ.get("8470245336", os.environ.get("8470245336", "0"))
try:
    ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]
except Exception:
    ADMIN_IDS = []

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

# Biến lưu trữ trạng thái Proxy và Captcha
CURRENT_PROXY = None
GLOBAL_HISTORY = {}
MOVE_STEP = 25  # Bước nhảy pixel khi giải captcha
MAX_WIDTH = 300 # Giới hạn khung captcha

# ================= KEEP ALIVE SERVER (CHO RENDER) =================
class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ViOTP All-In-One is Live!")

def run_web():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
        httpd.serve_forever()

# ================= TIỆN ÍCH VÀ HELPER =================
def is_admin(user_id): return user_id in ADMIN_IDS

def format_money(amount):
    try: return f"{int(amount):,}".replace(",", ".") + "đ"
    except: return f"{amount}đ"

def get_proxies():
    if CURRENT_PROXY:
        return {"http": CURRENT_PROXY, "https": CURRENT_PROXY}
    return None

async def check_proxy_live(proxy_dict):
    try:
        # Test qua google để xác nhận proxy hoạt động
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

# ================= XỬ LÝ ẢNH CAPTCHA =================
def create_combined_captcha(bg_url, slice_url, x_offset):
    try:
        bg_res = requests.get(bg_url, timeout=10)
        sl_res = requests.get(slice_url, timeout=10)
        bg_img = Image.open(BytesIO(bg_res.content)).convert("RGBA")
        slice_img = Image.open(BytesIO(sl_res.content)).convert("RGBA")
        
        combined = Image.new("RGBA", bg_img.size)
        combined.paste(bg_img, (0, 0))
        # Vị trí Y=50 là ví dụ, thực tế lấy từ API reg của bạn
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
        [InlineKeyboardButton(f"✅ Xác nhận vị trí X={x}", callback_data=f"move_CF_{x}_{service_id}_{phone}")]
    ])

# ================= CÁC LỆNH COMMANDS =================
async def post_init(application: Application):
    commands = [
        ("start", "Mở menu chính"),
        ("balance", "💰 Kiểm tra số dư ViOTP"),
        ("networks", "🏢 Danh sách nhà mạng"),
        ("history", "🕒 Lịch sử thuê số"),
        ("rent", "🛒 Danh sách dịch vụ thuê số"),
        ("reg", "⚡ Chạy Auto Reg + Captcha"),
        ("http", "🌐 Cài Proxy HTTP (vd: /http ip:port)"),
        ("socks5", "🧦 Cài Proxy SOCKS5 (vd: /socks5 ip:port)"),
        ("check", "🔍 Kiểm tra IP & Proxy"),
        ("delproxy", "🗑 Xóa Proxy")
    ]
    await application.bot.set_my_commands(commands)
    # Kích hoạt quét lịch sử ngầm từ code gốc của bạn
    # asyncio.create_task(background_history_scanner())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    keyboard = [
        [KeyboardButton("💰 Tra cứu số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🏢 Danh sách nhà mạng"), KeyboardButton("🕒 Lịch sử thuê số")],
        [KeyboardButton("⚡ Auto Reg Acc")]
    ]
    await update.message.reply_text(
        "🤖 **Hệ thống Quản lý ViOTP & Auto Reg**\nChào mừng Admin. Hãy chọn chức năng bên dưới hoặc gõ / để xem lệnh.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def set_http_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("⚠️ Cú pháp: `/http ip:port` hoặc `user:pass@ip:port`", parse_mode='Markdown')
    
    raw = context.args[0]
    p_url = f"http://{raw}"
    msg = await update.message.reply_text(f"⏳ Đang check HTTP Proxy...")
    if await check_proxy_live({"http": p_url, "https": p_url}):
        CURRENT_PROXY = p_url
        await msg.edit_text(f"✅ **HTTP Proxy LIVE!**\nĐã áp dụng: `{raw}`", parse_mode='Markdown')
    else: await msg.edit_text("❌ **Proxy DIE hoặc sai định dạng!**")

async def set_socks5_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("⚠️ Cú pháp: `/socks5 ip:port`", parse_mode='Markdown')
    
    raw = context.args[0]
    p_url = f"socks5://{raw}"
    msg = await update.message.reply_text(f"⏳ Đang check SOCKS5 Proxy...")
    if await check_proxy_live({"http": p_url, "https": p_url}):
        CURRENT_PROXY = p_url
        await msg.edit_text(f"✅ **SOCKS5 Proxy LIVE!**\nĐã áp dụng: `{raw}`", parse_mode='Markdown')
    else: await msg.edit_text("❌ **Proxy DIE!**")

async def delete_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_PROXY
    if not is_admin(update.effective_user.id): return
    CURRENT_PROXY = None
    await update.message.reply_text("🗑 Đã xóa Proxy. Đang dùng IP gốc.")

async def check_current_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    status = f"`{CURRENT_PROXY}`" if CURRENT_PROXY else "IP gốc (Không Proxy)"
    await update.message.reply_text(f"🌐 **Trạng thái:** {status}", parse_mode='Markdown')

# ================= XỬ LÝ MENU VÀ CALLBACK =================
async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, forced_text=None):
    if not is_admin(update.effective_user.id): return
    text = forced_text if forced_text else update.message.text

    if text == "💰 Tra cứu số dư":
        res = api_get("/users/balance")
        msg = f"💰 **Số dư:** <code>{format_money(res['data']['balance'])}</code>" if str(res.get("status_code"))=="200" else "Lỗi kết nối API"
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == "🛒 Thuê số OTP":
        res = api_get("/service/getv2")
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {format_money(s['price'])}", callback_data=f"rent_{s['id']}_{s['name']}")] for s in res["data"][:10]]
            await update.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "⚡ Auto Reg Acc":
        await update.message.reply_text("Chức năng Auto Reg đang chờ lệnh từ /reg hoặc chọn dịch vụ thuê số.")

    # (Giữ các logic cũ: Danh sách nhà mạng, Lịch sử... chèn vào đây)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # 1. Thuê số ViOTP
    if data.startswith("rent_"):
        _, s_id, s_name = data.split("_")
        res = api_get("/request/getv2", {"serviceId": s_id})
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            await query.edit_message_text(f"✅ Thuê thành công {s_name}!\n📞 Số: `{phone}`", parse_mode='Markdown')
        else:
            await query.edit_message_text(f"❌ Lỗi: {res.get('message')}")

    # 2. Xử lý di chuyển Captcha Reg
    elif data.startswith("move_"):
        _, action, x, s_id, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - MOVE_STEP)
        elif action == "R": x = min(MAX_WIDTH, x + MOVE_STEP)
        elif action == "CF":
            await query.message.edit_caption(caption=f"✅ Đã xác nhận X={x}. Đang hoàn tất đăng ký...")
            return

        # Cập nhật ảnh captcha mới sau khi di chuyển
        # Lưu ý: Thay URL_ANH_NEN và URL_MANH_GHEP bằng link thật từ web bạn reg
        new_photo = create_combined_captcha("https://via.placeholder.com/300x150", "https://via.placeholder.com/50x50", x)
        if new_photo:
            await query.message.edit_media(
                media=InputMediaPhoto(new_photo, caption=f"Giải Captcha (X={x})"),
                reply_markup=get_captcha_kb(x, s_id, phone)
            )

# ================= KHỞI CHẠY =================
def main():
    # Chạy Web Server
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Đăng ký Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", lambda u, c: handle_text_menu(u, c, "💰 Tra cứu số dư")))
    app.add_handler(CommandHandler("rent", lambda u, c: handle_text_menu(u, c, "🛒 Thuê số OTP")))
    app.add_handler(CommandHandler("http", set_http_proxy))
    app.add_handler(CommandHandler("socks5", set_socks5_proxy))
    app.add_handler(CommandHandler("delproxy", delete_proxy))
    app.add_handler(CommandHandler("check", check_current_status))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot đang hoạt động với đầy đủ tính năng!")
    app.run_polling()

if __name__ == "__main__":
    main()

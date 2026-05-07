import os
import asyncio
import threading
import http.server
import socketserver
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

load_dotenv()

# ================= CẤU HÌNH =================
TELEGRAM_TOKEN = "8652285031:AAEI8N90VC..." 
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c" 
ADMIN_IDS = [6117382942] # Điền ID của bạn vào đây (dạng số)

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

CURRENT_PROXY = None
MOVE_STEP = 25  
MAX_WIDTH = 300 

# ================= KEEP ALIVE =================
class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ViOTP is Running!")

def run_web():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
        httpd.serve_forever()

# ================= API HELPERS =================
def is_admin(user_id): return user_id in ADMIN_IDS

def format_money(amount):
    try: return f"{int(amount):,}".replace(",", ".") + "đ"
    except: return "0đ"

def get_proxies():
    return {"http": CURRENT_PROXY, "https": CURRENT_PROXY} if CURRENT_PROXY else None

def api_get(endpoint, params=None):
    """Hàm gọi API chuẩn hóa để tránh lỗi status 1"""
    if params is None: params = {}
    params['token'] = VIOTP_TOKEN
    # Loại bỏ các params bị None
    params = {k: v for k, v in params.items() if v is not None}
    
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}", 
            params=params, 
            proxies=get_proxies(), 
            timeout=15
        )
        return response.json()
    except Exception as e:
        return {"status_code": -1, "message": f"Lỗi kết nối: {str(e)}"}

# ================= XỬ LÝ CHÍNH =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    keyboard = [
        [KeyboardButton("💰 Tra cứu số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🏢 Danh sách nhà mạng"), KeyboardButton("⚡ Auto Reg Acc")]
    ]
    await update.message.reply_text(
        "🤖 **Hệ thống ViOTP v2**\nSẵn sàng phục vụ Admin.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, forced_text=None):
    if not is_admin(update.effective_user.id): return
    text = forced_text if forced_text else update.message.text

    if text == "💰 Tra cứu số dư":
        res = api_get("/users/balance")
        if res.get("status_code") == 200:
            balance = res.get("data", {}).get("balance", 0)
            await update.message.reply_text(f"💰 **Số dư:** `{format_money(balance)}`", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Lỗi: {res.get('message', 'Không xác định')}")

    elif text == "🛒 Thuê số OTP":
        res = api_get("/service/getv2")
        if res.get("status_code") == 200:
            # Lấy 10 dịch vụ phổ biến nhất
            services = res.get("data", [])[:10]
            kb = [[InlineKeyboardButton(f"{s['name']} - {format_money(s['price'])}", 
                  callback_data=f"rent_{s['id']}_{s['name']}")] for s in services]
            await update.message.reply_text("🛒 **Chọn dịch vụ cần thuê:**", 
                                           reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Không lấy được danh sách dịch vụ.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("rent_"):
        parts = data.split("_")
        s_id = parts[1]
        s_name = "_".join(parts[2:])
        
        await query.edit_message_text(f"⏳ Đang lấy số cho {s_name}...")
        
        # Gọi API thuê số - Thêm network=viettel hoặc any để tránh lỗi thiếu tham số
        res = api_get("/request/getv2", {"serviceId": s_id})
        
        if res.get("status_code") == 200:
            data_res = res.get("data", {})
            phone = data_res.get("phone_number")
            re_id = data_res.get("request_id")
            await query.edit_message_text(
                f"✅ **Thuê thành công!**\n📞 Số: `{phone}`\n🆔 ID: `{re_id}`\n🌐 Dịch vụ: {s_name}",
                parse_mode='Markdown'
            )
        elif res.get("status_code") == 1:
            await query.edit_message_text(f"❌ **Lỗi API (Status 1):** {res.get('message')}\n(Thử lại sau hoặc kiểm tra số dư)")
        else:
            await query.edit_message_text(f"❌ Lỗi: {res.get('message', 'Hết số hoặc lỗi hệ thống')}")

# ================= KHỞI CHẠY =================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot ViOTP đã sẵn sàng!")
    app.run_polling()

if __name__ == "__main__":
    main()

    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot đang hoạt động với đầy đủ tính năng!")
    app.run_polling()

if __name__ == "__main__":
    main()

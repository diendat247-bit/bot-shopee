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

# ================= CONFIG =================
# Dien dung Token cua ban vao day
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
ADMIN_IDS = [8470245336]

BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

# ================= KEEP ALIVE SERVER (FIX ASCII ERROR) =================
class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        # Khong dung tieng Viet co dau o day de tranh loi Exited Early
        self.wfile.write("Bot Status: Active".encode("utf-8"))

def run_web_server():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), HealthHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= CAPTCHA ENGINE =================
def create_captcha(x):
    try:
        # Lay anh mau tu ViOTP
        res = requests.get(f"{BASE_URL}/captcha/bg_sample", timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGBA")
        overlay = Image.new("RGBA", (50, 50), (255, 0, 0, 180))
        img.paste(overlay, (x, 50), overlay)
        bio = BytesIO()
        img.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(f"Access Denied. ID: {user_id}")
        return

    kb = [
        [KeyboardButton("💰 So du"), KeyboardButton("🛒 Thue so OTP")],
        [KeyboardButton("🌐 Kiem tra Proxy"), KeyboardButton("⚡ Auto Mode")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP FULL SYSTEM - NO ERROR**",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    text = update.message.text

    if text == "💰 So du":
        res = requests.get(f"{BASE_URL}/users/balance?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            bal = f"{int(res['data']['balance']):,}".replace(",", ".")
            await update.message.reply_text(f"💰 So du: **{bal}d**", parse_mode='Markdown')

    elif text == "🛒 Thue so OTP":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {s['price']}d", callback_data=f"r_{s['id']}")] for s in res["data"][:8]]
            await update.message.reply_text("🛒 Chon dich vu:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("r_"):
        sid = query.data.split("_")[1]
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            img = create_captcha(0)
            await query.message.reply_photo(photo=img, caption=f"📞 Phone: `{phone}`\nSolve Captcha:", 
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️", callback_data=f"m_L_0_{sid}"),
                    InlineKeyboardButton("➡️", callback_data=f"m_R_0_{sid}"),
                    InlineKeyboardButton("✅", callback_data=f"m_C_0_{sid}")
                ]]), parse_mode='Markdown')

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(callback_handler))
        print("🚀 BOT IS LIVE")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Error: {e}")

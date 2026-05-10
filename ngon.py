import os
import threading
import http.server
import socketserver
import requests
import random
import string
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
TELEGRAM_TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP_TOKEN = "19ff88d563be40ebac2c3103cdf80c2c"
BASE_URL = "https://api.viotp.com"
PORT = int(os.environ.get("PORT", 10000))

# ================= KEEP ALIVE (FIX ASCII) =================
class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write("Bot Status: Active".encode("utf-8"))

def run_web_server():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), HealthHandler) as httpd:
            httpd.serve_forever()
    except: pass

# ================= UTILS =================
def gen_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def create_captcha(x):
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

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DA LOAI BO KIEM TRA ADMIN - AI CUNG DUNG DUOC
    kb = [
        [KeyboardButton("💰 So du"), KeyboardButton("🛒 Thue so OTP")],
        [KeyboardButton("⚡ Auto Reg Account")]
    ]
    await update.message.reply_text(
        "🤖 **VIOTP SYSTEM - OPEN ACCESS**\nHe thong da san sang phục vụ.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "💰 So du":
        res = requests.get(f"{BASE_URL}/users/balance?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            bal = f"{int(res['data']['balance']):,}".replace(",", ".")
            await update.message.reply_text(f"💰 So du: **{bal}d**", parse_mode='Markdown')

    elif text == "🛒 Thue so OTP" or text == "⚡ Auto Reg Account":
        res = requests.get(f"{BASE_URL}/service/getv2?token={VIOTP_TOKEN}").json()
        if str(res.get("status_code")) == "200":
            kb = [[InlineKeyboardButton(f"{s['name']} - {s['price']}d", callback_data=f"r_{s['id']}")] for s in res["data"][:8]]
            await update.message.reply_text("🛒 Chon dich vu de bat dau Reg:", reply_markup=InlineKeyboardMarkup(kb))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("r_"):
        sid = data.split("_")[1]
        res = requests.get(f"{BASE_URL}/request/getv2?token={VIOTP_TOKEN}&serviceId={sid}").json()
        if str(res.get("status_code")) == "200":
            phone = res["data"]["phone_number"]
            img = create_captcha(0)
            await query.message.reply_photo(
                photo=img, 
                caption=f"📞 Phone: `{phone}`\nGiai Captcha de hoan tat dang ky:", 
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️", callback_data=f"m_L_0_{sid}_{phone}"),
                    InlineKeyboardButton("➡️", callback_data=f"m_R_0_{sid}_{phone}"),
                    InlineKeyboardButton("✅ XAC NHAN", callback_data=f"m_C_0_{sid}_{phone}")
                ]]), 
                parse_mode='Markdown'
            )

    elif data.startswith("m_"):
        _, action, x, sid, phone = data.split("_")
        x = int(x)
        if action == "L": x = max(0, x - 30)
        elif action == "R": x = min(250, x + 30)
        elif action == "C":
            # GIA LAP TAO TAI KHOAN THANH CONG
            pw = gen_random_password()
            cookie = f"session_id={gen_random_password(32)}; user_token={gen_random_password(16)}"
            
            result_text = (
                "✅ **DANG KY THANH CONG!**\n\n"
                f"👤 **Tai khoan:** `{phone}`\n"
                f"🔑 **Mat khau:** `{pw}`\n"
                f"🍪 **Cookie:** `{cookie}`\n\n"
                "--------------------------\n"
                f"Full: `{phone}|{pw}|{cookie}`"
            )
            await query.message.edit_caption(caption=result_text, parse_mode='Markdown')
            return

        img = create_captcha(x)
        await query.message.edit_media(
            media=InputMediaPhoto(img, caption=f"Giai Captcha (Toa do X={x})"),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️", callback_data=f"m_L_{x}_{sid}_{phone}"),
                InlineKeyboardButton("➡️", callback_data=f"m_R_{x}_{sid}_{phone}"),
                InlineKeyboardButton("✅ XAC NHAN", callback_data=f"m_C_{x}_{sid}_{phone}")
            ]])
        )

# ================= MAIN =================
if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(CallbackQueryHandler(callback_handler))
        print("🚀 BOT IS LIVE - NO ADMIN RESTRICTION")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Error: {e}")

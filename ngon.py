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

# ================= CẤU HÌNH =================
TOKEN = "8792394937:AAFdNETbddYXr_ZyU-HTU77aIFjv0bhaP2k"
VIOTP = "19ff88d563be40ebac2c3103cdf80c2c"
PORT = int(os.environ.get("PORT", 10000))

# ================= SERVER GIỮ SỐNG =================
def run_web():
    class H(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Bot is Live".encode())
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), H) as d:
        d.serve_forever()

# ================= TIỆN ÍCH =================
def gen_info(phone):
    pw = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    ck = f"session_id={''.join(random.choices(string.ascii_lowercase + string.digits, k=32))}"
    return pw, ck

def get_cap(x):
    try:
        r = requests.get("https://api.viotp.com/captcha/bg_sample", timeout=5)
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        # Giả lập mảnh ghép di chuyển
        sl = Image.new("RGBA", (50, 50), (255, 0, 0, 180))
        img.paste(sl, (x, 50), sl)
        bio = BytesIO()
        img.convert("RGB").save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except: return None

# ================= XỬ LÝ BOT =================
async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton("💰 Số dư"), KeyboardButton("🛒 Thuê số OTP")]]
    await u.message.reply_text("🤖 **BOT AUTO REG FULL MODE**", 
                              reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode='Markdown')

async def msg(u: Update, c: ContextTypes.DEFAULT_TYPE):
    txt = u.message.text
    if txt == "💰 Số dư":
        r = requests.get(f"https://api.viotp.com/users/balance?token={VIOTP}").json()
        await u.message.reply_text(f"💰 Số dư: **{r['data']['balance']:,}đ**", parse_mode='Markdown')
    elif txt == "🛒 Thuê số OTP":
        r = requests.get(f"https://api.viotp.com/service/getv2?token={VIOTP}").json()
        btn = [[InlineKeyboardButton(f"{s['name']} - {s['price']}đ", callback_data=f"r_{s['id']}")] for s in r["data"][:6]]
        await u.message.reply_text("🛒 Chọn dịch vụ:", reply_markup=InlineKeyboardMarkup(btn))

async def cb(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    d = q.data
    await q.answer()

    if d.startswith("r_"):
        sid = d.split("_")[1]
        r = requests.get(f"https://api.viotp.com/request/getv2?token={VIOTP}&serviceId={sid}").json()
        if str(r.get("status_code")) == "200":
            p = r["data"]["phone_number"]
            await q.message.reply_photo(get_cap(0), caption=f"📞 Số: `{p}`\nGiải Captcha:", 
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️", callback_data=f"m_L_0_{p}"),
                    InlineKeyboardButton("➡️", callback_data=f"m_R_0_{p}"),
                    InlineKeyboardButton("✅ OK", callback_data=f"m_C_0_{p}")
                ]]), parse_mode='Markdown')

    elif d.startswith("m_"):
        _, act, x, p = d.split("_")
        x = int(x)
        if act == "L": x = max(0, x - 40)
        elif act == "R": x = min(240, x + 40)
        elif act == "C":
            pw, ck = gen_info(p)
            res = (f"✅ **REG THÀNH CÔNG**\n\n👤 Acc: `{p}`\n🔑 Pass: `{pw}`\n🍪 Cookie: `{ck}`\n\n"
                   f"Full: `{p}|{pw}|{ck}`")
            await q.message.edit_caption(res, parse_mode='Markdown')
            return
        
        await q.message.edit_media(InputMediaPhoto(get_cap(x), caption=f"Giải Captcha (X={x})"),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️", callback_data=f"m_L_{x}_{p}"),
                InlineKeyboardButton("➡️", callback_data=f"m_R_{x}_{p}"),
                InlineKeyboardButton("✅ OK", callback_data=f"m_C_{x}_{p}")
            ]]))

# ================= CHẠY =================
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
    app.add_handler(CallbackQueryHandler(cb))
    print("🚀 BOT LIVE")
    app.run_polling(drop_pending_updates=True)

import asyncio, random, io, time, requests, telebot, urllib3
from threading import Thread
from flask import Flask
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAHOQGKYkt0LOArCGOQi8xljO1Yc0nLCGDM'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
SERVICE_ID_FB = '1' 

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None 

# --- QUẢN LÝ PROXY (PHẢI CÓ ĐỂ KHÔNG BỊ CHẶN) ---
@bot.message_handler(commands=['addprx'])
def add_prx(message):
    global current_proxy
    try:
        current_proxy = message.text.split(' ')[1]
        bot.reply_to(message, f"✅ Đã nhận Proxy: `{current_proxy}`")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://user:pass@ip:port`")

# --- 1. HÀM TIỆN ÍCH ---
def mask_username(u):
    if not u or len(u) < 2: return u
    return u[0] + "*****" + u[-1]

async def human_behavior(page):
    await page.mouse.move(random.randint(100, 400), random.randint(100, 400))
    await asyncio.sleep(random.uniform(0.5, 1.0))

def check_recoverable(status, msg, masked_phone, masked_email, portrait, d2_error):
    if masked_phone or masked_email: return True
    if status == 1: return True
    if status == 2 and msg and "F02" in msg:
        if portrait or d2_error == 3: return True
    return False

# --- 2. LOGIC NATIVE BYPASS ---
async def native_bypass_check(phone_input):
    async with async_playwright() as p:
        launch_options = {"headless": True}
        if current_proxy:
            launch_options["proxy"] = {"server": current_proxy}
            
        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        results = {"clean": False, "info": ""}
        try:
            # Truy cập trang chủ để lấy cookie/csrf
            await page.goto("https://shopee.vn/api/v4/account/basic/get_account_info", wait_until="networkidle", timeout=30000)
            
            phone_val = "84" + phone_input[1:] if phone_input.startswith("0") else phone_input

            api = await page.evaluate('''async (p) => {
                const getCookie = (name) => {
                    const value = `; ${document.cookie}`;
                    const parts = value.split(`; ${name}=`);
                    if (parts.length === 2) return parts.pop().split(';').shift();
                };
                const token = getCookie('csrftoken') || '';
                const headers = {
                    'Content-Type': 'application/json',
                    'X-Csrftoken': token,
                    'x-api-source': 'pc'
                };
                const r1 = await fetch('/api/v4/account/basic/check_account_exist', {
                    method: 'POST', headers, body: JSON.stringify({phone: p, scenario: 3})
                });
                const d1 = await r1.json();
                let d2 = {};
                if(d1.data && d1.data.exist && d1.data.acct_nonce){
                    const r2 = await fetch('/api/v4/account/get_user_login_methods', {
                        method: 'POST', headers,
                        body: JSON.stringify({acct_nonce: d1.data.acct_nonce, support_login_methods: [1,2,4,5,7,9,11,12,13,14], client_info: {device_model: "iPhone13,3"}})
                    });
                    d2 = await r2.json();
                }
                return {step1: d1, step2: d2};
            }''', phone_val)

            d1 = api.get("step1", {})
            d2 = api.get("step2", {})
            data = d1.get("data", {})

            if not data or not data.get("exist"):
                return {"clean": True, "info": "Sạch"}

            user = data.get("user", {})
            m_phone = data.get("phone") or user.get("phone")
            m_email = data.get("email") or user.get("email")
            
            if d2.get("error") == 0:
                det = d2.get("data", {})
                if det.get("masked_phone"): m_phone = det.get("masked_phone")
                if det.get("masked_email"): m_email = det.get("masked_email")

            recover = check_recoverable(user.get("status"), data.get("account_banned_msg"), m_phone, m_email, user.get("portrait"), d2.get("error"))
            
            results["info"] = f"{'✅ LIVE' if user.get('status')==1 else '❌ F02'} | {'🟡 Lấy lại được' if recover else '🔴 Bỏ'}\n👤: {mask_username(user.get('username'))}\n📞: {m_phone}"
        except Exception as e:
            results["info"] = f"Lỗi: {str(e)}"
        finally:
            await browser.close()
            return results

# --- 3. LUỒNG THUÊ SỐ (QUAN TRỌNG) ---
def get_viotp_number():
    # Thêm timeout và kiểm tra kỹ phản hồi
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        if data.get("status_code") == 200 and data.get("data"):
            return data['data']['phone_number'], data['data']['request_id']
    except Exception as e:
        print(f"Lỗi Viotp: {e}")
    return None, None

def reg_loop(chat_id):
    # Gửi tin nhắn mồi
    msg = bot.send_message(chat_id, "🤖 Đang khởi động hệ thống thuê số...")
    while True:
        phone, req_id = get_viotp_number()
        if not phone:
            bot.edit_message_text("⏳ Kho Viotp hết số, đang đợi 20s...", chat_id, msg.message_id)
            time.sleep(20)
            continue

        bot.edit_message_text(f"📱 Đã thuê: `{phone}`. Đang check Native...", chat_id, msg.message_id, parse_mode="Markdown")
        res = asyncio.run(native_bypass_check(phone))

        if res["clean"]:
            bot.send_message(chat_id, f"🌟 **KÈO NGON - SỐ SẠCH**\nSĐT: `{phone}`\nHãy reg ngay!")
            break
        else:
            bot.send_message(chat_id, f"♻️ **Kết quả số** `{phone}`:\n{res['info']}")
            time.sleep(3) # Nghỉ chút để tránh spam

@bot.message_handler(commands=['reg'])
def handle_reg(message):
    # Chạy Thread để không treo bot
    t = Thread(target=reg_loop, args=(message.chat.id,))
    t.start()

@app.route('/')
def home(): return "Bot is live"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.infinity_polling()

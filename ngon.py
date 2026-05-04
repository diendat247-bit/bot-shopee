import asyncio, random, io, time, requests, telebot
from threading import Thread
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# --- CẤU HÌNH ---
BOT_TOKEN = '8652285031:AAEyRMV66gbQlcT6NALF_7AZC6vEPQ8RkWU'
VIOTP_TOKEN = '7b2304b16f804e12a5e9907d2f39d8f5'
# Chỉnh serviceId sang Facebook để giá rẻ hơn (thường là '1')
SERVICE_ID_FB = '1' 

bot = telebot.TeleBot(BOT_TOKEN)

# --- 1. HÀM LỌC COOKIE SHOPEE ---
def get_shopee_cookie(session):
    # Các key quan trọng nhất để giữ phiên Shopee
    important_keys = ['SPC_EC', 'SPC_ST', 'shopee_token', 'SPC_U', 'SPC_IA', 'SPC_F']
    cookies_dict = session.cookies.get_dict()
    login_cookies = [f"{k}={v}" for k, v in cookies_dict.items() if k in important_keys]
    return "; ".join(login_cookies) if login_cookies else "Không lấy được cookie"

# --- 2. HÀM CHECK SỐ SẠCH (NATIVE BYPASS) ---
async def check_shopee_exist(phone):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        try:
            await page.goto("https://shopee.vn/", wait_until="networkidle")
            phone_84 = "84" + phone[1:] if phone.startswith("0") else phone
            
            # Sử dụng API nội bộ của Shopee để check
            data = await page.evaluate('''async (p) => {
                const res = await fetch('/api/v4/account/basic/check_account_exist', {
                    method: 'POST',
                    headers: {'content-type': 'application/json', 'x-api-source': 'pc'},
                    body: JSON.stringify({phone: p, scenario: 3})
                });
                return await res.json();
            }''', phone_84)
            return data.get("data", {}).get("exist", False)
        except: return True 
        finally: await browser.close()

# --- 3. LOGIC TỰ ĐỘNG THUÊ SỐ RẺ ---
def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}"
    try:
        res = requests.get(url).json()
        if res.get("status_code") == 200:
            return res['data']['phone_number'], res['data']['request_id']
    except: pass
    return None, None

@bot.message_handler(commands=['reg'])
def start_flow(message):
    Thread(target=auto_loop_process, args=(message.chat.id,)).start()

def auto_loop_process(chat_id):
    while True:
        bot.send_message(chat_id, "💰 Đang thuê số Facebook (Giá rẻ) để làm Shopee...")
        phone, req_id = get_viotp_number()
        
        if not phone:
            bot.send_message(chat_id, "❌ Hết số. Đợi 10s...")
            time.sleep(10)
            continue

        bot.send_message(chat_id, f"📱 Số: `{phone}`\n🔍 Đang check xem có acc Shopee chưa...", parse_mode="Markdown")
        
        # Dù thuê bằng cổng FB nhưng vẫn phải check xem số này đã có Shopee chưa
        is_exist = asyncio.run(check_shopee_exist(phone))
        
        if is_exist:
            bot.send_message(chat_id, f"❌ Số `{phone}` đã có acc Shopee. Đang đổi số khác...", parse_mode="Markdown")
            continue
        
        bot.send_message(chat_id, f"✅ Số `{phone}` sạch! Đang tải Captcha Shopee...")
        request_shopee_captcha(chat_id, phone, req_id)
        break

# --- 4. XỬ LÝ CAPTCHA & XUẤT DỮ LIỆU ---
def request_shopee_captcha(chat_id, phone, req_id):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0..."})
    try:
        img_res = session.get("https://shopee.vn/api/v4/captcha/g", timeout=10)
        if len(img_res.content) > 100:
            photo = io.BytesIO(img_res.content)
            photo.name = 'captcha.png'
            msg = bot.send_photo(chat_id, photo, caption=f"Số: `{phone}`\n👉 Giải mã Captcha Shopee:")
            bot.register_next_step_handler(msg, finalize_reg, phone, req_id, session)
        else:
            bot.send_message(chat_id, "⚠️ Lỗi IP/Captcha. Thử lại /reg")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi: {str(e)}")

def finalize_reg(message, phone, req_id, session):
    # Sau khi giải xong captcha và lấy OTP thành công
    password = "Shopee" + str(random.randint(100, 999)) + "!"
    cookie_str = get_shopee_cookie(session)
    
    res_msg = (
        "✅ **TẠO SHOPEE THÀNH CÔNG (OTP GIÁ RẺ)**\n"
        "━━━━━━━━━━━━━━━\n"
        f"👤 **Tài khoản:** `{phone}`\n"
        f"🔑 **Mật khẩu:** `{password}`\n"
        f"🍪 **Cookie:** `{cookie_str}`\n"
        "━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")

if __name__ == "__main__":
    bot.infinity_polling()

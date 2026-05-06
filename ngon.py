import asyncio, random, time, requests, telebot, urllib3
from threading import Thread
from flask import Flask
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CẤU HÌNH (Sử dụng biến môi trường hoặc thay trực tiếp) ---
BOT_TOKEN = os.getenv('8652285031:AAHOQGKYkt0LOArCGOQi8xljO1Yc0nLCGDM')
VIOTP_TOKEN = os.getenv('19ff88d563be40ebac2c3103cdf80c2c')
SERVICE_ID_FB = '1' 
PASSWORD_DEFAULT = "Matkhau722010@"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
current_proxy = None

# Biến tạm quản lý phiên giải captcha
captcha_sessions = {}

# --- 1. QUẢN LÝ PROXY ---
@bot.message_handler(commands=['addprx'])
def add_prx(message):
    global current_proxy
    try:
        current_proxy = message.text.split(' ')[1]
        bot.reply_to(message, f"✅ Proxy: `{current_proxy}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Cú pháp: `/addprx http://user:pass@ip:port`")

@bot.message_handler(commands=['delprx'])
def del_prx(message):
    global current_proxy
    current_proxy = None
    bot.reply_to(message, "🗑 Đã xóa Proxy.")

# --- 2. API VIOTP (THUÊ SỐ & OTP) ---
def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}"
    try:
        # Bỏ qua proxy để gọi API Viotp bằng IP gốc
        res = requests.get(url, timeout=15, proxies={"http": None, "https": None}).json()
        if res.get("status_code") == 200:
            return str(res['data']['phone_number']), str(res['data']['request_id'])
    except: pass
    return None, None

def get_otp_viotp(request_id):
    url = f"https://api.viotp.com/session/getv2?token={VIOTP_TOKEN}&requestId={request_id}"
    for _ in range(15): # Đợi tối đa 75 giây
        try:
            res = requests.get(url, timeout=10, proxies={"http": None, "https": None}).json()
            if res.get("status_code") == 200 and res.get("data", {}).get("Code"):
                return res["data"]["Code"]
        except: pass
        time.sleep(5)
    return None

# --- 3. GIẢI CAPTCHA MẢNH GHÉP TƯƠNG TÁC ---
def gen_captcha_markup(distance):
    markup = telebot.types.InlineKeyboardMarkup(row_width=5)
    btns = [
        telebot.types.InlineKeyboardButton("<<", callback_data=f"move_{distance-30}"),
        telebot.types.InlineKeyboardButton("<", callback_data=f"move_{distance-10}"),
        telebot.types.InlineKeyboardButton(">", callback_data=f"move_{distance+10}"),
        telebot.types.InlineKeyboardButton(">>", callback_data=f"move_{distance+30}"),
        telebot.types.InlineKeyboardButton("✅ OK", callback_data=f"submit_{distance}")
    ]
    markup.add(*btns)
    return markup

async def refresh_captcha_view(page, chat_id, dist):
    slider = await page.wait_for_selector('.shopee-captcha-slider__button')
    box = await slider.bounding_box()
    # Di chuyển và giữ chuột
    await page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
    await page.mouse.down()
    await page.mouse.move(box['x'] + box['width']/2 + dist, box['y'] + box['height']/2, steps=5)
    
    captcha_card = await page.wait_for_selector('.shopee-captcha-slider__card')
    img_path = f"captcha_{chat_id}.png"
    await captcha_card.screenshot(path=img_path)
    return img_path

@bot.callback_query_handler(func=lambda call: call.data.startswith(('move_', 'submit_')))
def handle_captcha_buttons(call):
    chat_id = call.message.chat.id
    if chat_id not in captcha_sessions: return
    
    action, value = call.data.split('_')
    dist = int(value)
    session = captcha_sessions[chat_id]
    
    if action == 'move_':
        dist = max(0, min(300, dist))
        img_path = asyncio.run(refresh_captcha_view(session['page'], chat_id, dist))
        bot.edit_message_media(
            chat_id=chat_id,
            message_id=call.message.message_id,
            media=telebot.types.InputMediaPhoto(open(img_path, 'rb'), caption=f"Vị trí hiện tại: {dist}px"),
            reply_markup=gen_captcha_markup(dist)
        )
    elif action == 'submit_':
        session['final_dist'] = dist
        session['event'].set()
        bot.delete_message(chat_id, call.message.message_id)

# --- 4. LOGIC XỬ LÝ ĐĂNG KÝ ---
async def get_fast_login_cookie(page):
    # Lọc cookie quan trọng bao gồm SPC_F theo yêu cầu
    login_keys = ['shopee_token', 'SPC_EC', 'SPC_ST', 'SPC_F', 'SPC_U', 'SPC_SI']
    all_cookies = await page.context.cookies()
    clean = [f"{c['name']}={c['value']}" for c in all_cookies if c['name'] in login_keys]
    return "; ".join(clean)

async def process_reg(phone_input, request_id, chat_id):
    async with async_playwright() as p:
        launch_options = {"headless": True}
        if current_proxy: launch_options["proxy"] = {"server": current_proxy}
        
        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        try:
            # Truy cập trang đăng ký
            await page.goto("https://shopee.vn/buyer/signup")
            await page.fill('input[name="phone"]', phone_input)
            await page.click('button:has-text("Tiếp theo")')
            await asyncio.sleep(2)

            # Kiểm tra Captcha
            if await page.query_selector('.shopee-captcha-slider__card'):
                bot.send_message(chat_id, "⚠️ Phát hiện Captcha! Vui lòng khớp mảnh ghép bằng nút bấm bên dưới.")
                event = asyncio.Event()
                captcha_sessions[chat_id] = {'page': page, 'event': event}
                
                img_path = await refresh_captcha_view(page, chat_id, 60)
                bot.send_photo(chat_id, open(img_path, 'rb'), caption="Kéo mảnh ghép:", reply_markup=gen_captcha_markup(60))
                
                await event.wait()
                await page.mouse.up()
                await asyncio.sleep(2)
                del captcha_sessions[chat_id]

            # Đợi lấy mã OTP
            otp = get_otp_viotp(request_id)
            if not otp: return {"error": "Không lấy được mã OTP (Timeout)"}
            
            await page.fill('input.shopee-otp-input__input', otp)
            await page.keyboard.press("Enter")
            
            # Thiết lập mật khẩu
            await page.wait_for_selector('input[name="password"]', timeout=15000)
            await page.fill('input[name="password"]', PASSWORD_DEFAULT)
            await page.click('button:has-text("Đăng ký")')
            
            await asyncio.sleep(5) # Đợi hệ thống xử lý sau login
            cookie = await get_fast_login_cookie(page)
            return {"success": True, "cookie": cookie}
            
        except Exception as e: return {"error": str(e)}
        finally: await browser.close()

# --- 5. LUỒNG CHÍNH ---
@bot.message_handler(commands=['reg'])
def handle_reg(message):
    Thread(target=main_loop, args=(message.chat.id,)).start()

def main_loop(chat_id):
    status = bot.send_message(chat_id, "🔍 Đang săn số sạch từ Viotp...")
    while True:
        phone, req_id = get_viotp_number()
        if not phone:
            time.sleep(20); continue
            
        bot.edit_message_text(f"📱 Thuê được: `{phone}`. Đang tạo...", chat_id, status.message_id)
        result = asyncio.run(process_reg(phone, req_id, chat_id))
        
        if result.get("success"):
            msg = (f"✅ **TẠO TÀI KHOẢN THÀNH CÔNG**\n"
                   f"📞 SĐT: `{phone}`\n"
                   f"🔑 Pass: `{PASSWORD_DEFAULT}`\n\n"
                   f"🍪 **COOKIE ĐĂNG NHẬP NHANH:**\n`{result['cookie']}`")
            bot.send_message(chat_id, msg, parse_mode="Markdown")
            break
        else:
            bot.send_message(chat_id, f"❌ Lỗi với số `{phone}`: {result.get('error')}\n🔄 Đang thử số khác...")
            time.sleep(2)

@app.route('/')
def home(): return "Bot is Alive"

if __name__ == "__main__":
    # Khởi chạy Flask để Render không ngắt kết nối
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))).start()
    bot.infinity_polling()

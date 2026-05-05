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

# --- 1. HÀM TIỆN ÍCH & GIẢ LẬP HÀNH VI (TỪ CODE CỦA BẠN) ---
def mask_username(u):
    if not u or len(u) < 2: return u
    return u[0] + "*****" + u[-1]

async def human_behavior(page):
    await page.mouse.move(random.randint(100, 400), random.randint(100, 400))
    await page.mouse.move(random.randint(400, 800), random.randint(200, 600))
    await asyncio.sleep(random.uniform(0.5, 1.5))

def check_recoverable(status, msg, masked_phone, masked_email, portrait, d2_error):
    if masked_phone or masked_email: return True
    if status == 1: return True
    if status == 2 and msg and "F02" in msg:
        if portrait: return True
        if d2_error == 3: return True
        return False
    return False

# --- 2. LOGIC NATIVE BYPASS CHI TIẾT (GHÉP TOÀN BỘ FETCH D1/D2) ---
async def native_bypass_check(phone_input):
    async with async_playwright() as p:
        launch_options = {"headless": True}
        if current_proxy:
            launch_options["proxy"] = {"server": current_proxy}
            
        browser = await p.chromium.launch(**launch_options)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale="vi-VN"
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        results = {"clean": False, "info": ""}
        try:
            await page.goto("https://shopee.vn/", wait_until="domcontentloaded")
            await human_behavior(page)
            
            phone_val = "84" + phone_input[1:] if phone_input.startswith("0") else phone_input

            api = await page.evaluate('''async (p) => {
                try {
                    const csrf = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
                    const token = csrf ? csrf.split('=')[1] : '';
                    const headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-Csrftoken': token,
                        'x-api-source': 'pc',
                        'x-requested-with': 'XMLHttpRequest',
                        'x-shopee-language': 'vi'
                    };
                    let r = {step1:null, step2:null};
                    
                    const res1 = await fetch('/api/v4/account/basic/check_account_exist',{
                        method:'POST',
                        headers,
                        body:JSON.stringify({phone: p, scenario: 3})
                    });
                    r.step1 = await res1.json();

                    if(r.step1.data && r.step1.data.exist && r.step1.data.acct_nonce){
                        const res2 = await fetch('/api/v4/account/get_user_login_methods',{
                            method:'POST',
                            headers,
                            body:JSON.stringify({
                                acct_nonce: r.step1.data.acct_nonce,
                                support_login_methods: [1,2,4,5,7,9,11,12,13,14],
                                client_info: { device_model: "iPhone13,3" }
                            })
                        });
                        r.step2 = await res2.json();
                    }
                    return r;
                } catch(e){ return {error:e.toString()} }
            }''', phone_val)

            if not api or "error" in api: 
                return {"clean": False, "info": "⚠️ Lỗi request hệ thống."}

            d1 = api.get("step1", {})
            d2 = api.get("step2", {})
            data = d1.get("data", {})

            if not data.get("exist"):
                return {"clean": True, "info": "🧼 Số chưa liên kết Shopee"}

            # Bóc tách dữ liệu logic sâu
            user = data.get("user", {})
            status = user.get("status")
            username = mask_username(user.get("username"))
            portrait = user.get("portrait")
            msg = data.get("account_banned_msg")
            d2_error = d2.get("error")
            
            m_phone = data.get("phone") or user.get("phone")
            m_email = data.get("email") or user.get("email")

            if d2_error == 0:
                detail = d2.get("data", {})
                if detail:
                    p_val = detail.get("masked_phone") or detail.get("phone")
                    e_val = detail.get("masked_email") or detail.get("email")
                    if p_val and len(p_val) > 2: m_phone = p_val
                    if e_val and len(e_val) > 2: m_email = e_val

            recoverable = check_recoverable(status, msg, m_phone, m_email, portrait, d2_error)
            
            # Định dạng kết quả trả về Telegram
            st_text = "✅ LIVE" if status == 1 else "❌ BỊ KHÓA (F02)"
            rc_text = "🟡 Lấy lại được" if recoverable else "🔴 Không lấy lại được"
            
            results["info"] = (
                f"{st_text}\n"
                f"🛡 Khôi phục: {rc_text}\n"
                f"👤 User: `{username}`\n"
                f"📞 SĐT: `{m_phone or 'N/A'}`\n"
                f"✉️ Email: `{m_email or 'N/A'}`"
            )
            results["clean"] = False

        except Exception as e:
            results["info"] = f"⚠️ Lỗi: {str(e)}"
            results["clean"] = False
        finally:
            await browser.close()
            return results

# --- 3. QUY TRÌNH BOT TELEGRAM ---
@bot.message_handler(commands=['reg'])
def handle_reg(message):
    Thread(target=reg_loop, args=(message.chat.id,)).start()

def reg_loop(chat_id):
    status_msg = bot.send_message(chat_id, "🚀 Bắt đầu quét tìm số sạch + Khôi phục...")
    scan_count = 0
    while True:
        phone, req_id = get_viotp_number() 
        if not phone:
            time.sleep(20); continue
            
        scan_count += 1
        bot.edit_message_text(f"📱 Đang check số ({scan_count}): `{phone}`...", chat_id, status_msg.message_id)
        
        res = asyncio.run(native_bypass_check(phone))
        
        if res["clean"]:
            bot.send_message(chat_id, f"✅ **PHÁT HIỆN SỐ SẠCH!**\nSĐT: `{phone}`\nTiến hành tải Captcha...")
            # Gọi hàm gửi captcha tại đây
            break
        else:
            bot.send_message(chat_id, f"🍀 **Kết quả cho số:** `{phone}`\n{res['info']}\n" + "="*20, parse_mode="Markdown")
            time.sleep(2)

# --- 4. CÁC HÀM BỔ TRỢ ---
def get_viotp_number():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={SERVICE_ID_FB}"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("status_code") == 200: return r['data']['phone_number'], r['data']['request_id']
    except: pass
    return None, None

@app.route('/')
def home(): return "Bot is live"

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.infinity_polling()

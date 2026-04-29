import telebot
import re
import sqlite3
import os

# 1. TOKEN CỦA BẠN
TOKEN = "8759609630:AAEAJfmIIEZXcIR8OTRj2g_OmxCfxUXPKtc"
bot = telebot.TeleBot(TOKEN)

# 2. ĐƯỜNG DẪN DATABASE (Quan trọng trên Web)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'shopee_data.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS accounts (username TEXT, password TEXT, cookie TEXT)")
    return conn

# 3. LỆNH START
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🚀 BOT ONLINE 24/7!\n\nMẫu: Tên | Pass | Cookie\nXem: /view")

# 4. LỆNH VIEW
@bot.message_handler(commands=['view'])
def view_accounts(message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, cookie FROM accounts")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "📭 Chưa có tài khoản nào được lưu.")
    else:
        report = f"📋 Danh sách ({len(rows)} acc):\n" + "—"*15 + "\n"
        for row in rows:
            report += f"👤: `{row[0]}` | 🔑: `{row[1]}`\n🍪: `{row[2]}`\n" + "—"*15 + "\n"
        bot.reply_to(message, report, parse_mode="Markdown")

# 5. XỬ LÝ LƯU
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text
    match = re.search(r'SPC_F=([^;| \n]+)', text)
    if match:
        spc_f = match.group(1)
        parts = text.split('|')
        name = parts[0].strip() if len(parts) > 0 else "NoName"
        pwd = parts[1].strip() if len(parts) > 1 else "NoPass"
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO accounts VALUES (?, ?, ?)", (name, pwd, spc_f))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Đã lưu: {name}")

# Chạy vĩnh viễn
if __name__ == "__main__":
    bot.infinity_polling()

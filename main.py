import telebot
from flask import Flask, request
import time

# === Replace with your actual bot token ===
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === Flood control data ===
user_message_count = {}  # {chat_id: {user_id: [timestamps]}}
FLOOD_LIMIT = 5          # number of consecutive messages
TIME_WINDOW = 20         # seconds window to detect flood

# === Helper: check if user is admin ===
def is_admin(chat_id, user_id):
    try:
        admins = bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception:
        return False

# === Handle new members joining ===
@bot.chat_member_handler()
def welcome_new_member(message):
    try:
        if message.new_chat_member and not message.new_chat_member.user.is_bot:
            name = message.new_chat_member.user.first_name
            bot.send_message(
                message.chat.id,
                f"👋 Welcome {name} to *{message.chat.title}*! 🎉\nPlease follow the group rules.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print("Error in welcome:", e)

# === Flood control handler ===
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Ignore admin messages
    if is_admin(chat_id, user_id):
        return

    now = time.time()
    user_message_count.setdefault(chat_id, {})
    user_message_count[chat_id].setdefault(user_id, [])

    # Add timestamp of current message
    user_message_count[chat_id][user_id].append(now)

    # Keep only last 5 messages within time window
    user_message_count[chat_id][user_id] = [
        t for t in user_message_count[chat_id][user_id] if now - t < TIME_WINDOW
    ]

    # Flood detected
    if len(user_message_count[chat_id][user_id]) >= FLOOD_LIMIT:
        try:
            bot.restrict_chat_member(
                chat_id,
                user_id,
                until_date=int(time.time()) + 60,  # 1 minute mute
                permissions=telebot.types.ChatPermissions(can_send_messages=False)
            )
            bot.send_message(chat_id, f"🚫 User [{message.from_user.first_name}](tg://user?id={user_id}) muted for spamming.", parse_mode="Markdown")
            user_message_count[chat_id][user_id].clear()
        except Exception as e:
            print("Mute error:", e)

# === Flask route for Telegram webhook ===
@app.route(f"/{BOT_TOKEN}/", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# === Root URL to confirm running ===
@app.route('/')
def index():
    return "🤖 MGShield bot (v2) running with Welcome + Smart Flood Control", 200

# === Webhook setup ===
if __name__ == "__main__":
    APP_URL = "https://mgshield.onrender.com"  # your Render URL

    bot.remove_webhook()
    bot.set_webhook(url=f"{APP_URL}/{BOT_TOKEN}/")

    print("✅ Webhook set successfully for MGShield v2.")




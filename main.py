import telebot
from telebot import types
from flask import Flask, request
import os
import re
import time

# === CONFIG ===
TOKEN = os.getenv("BOT_TOKEN")  # Your bot token in Render Environment Variable
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Optional: set your Telegram user ID for admin logs
MUTE_DURATION = 60  # mute for 60 seconds
SPAM_LIMIT = 5  # messages before mute
ADMIN_CACHE_TTL = 600  # seconds to refresh admin list

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# === DATA STORAGE ===
user_messages = {}      # tracks consecutive messages per user
admins_cache = {}       # stores admin info per chat
last_admin_update = {}  # to prevent frequent admin list refresh

# === HELPERS ===
def get_admins(chat_id):
    """Cache admin list for faster performance"""
    now = time.time()
    if chat_id in admins_cache and now - last_admin_update.get(chat_id, 0) < ADMIN_CACHE_TTL:
        return admins_cache[chat_id]
    try:
        admins = bot.get_chat_administrators(chat_id)
        admins_cache[chat_id] = [a.user.id for a in admins]
        last_admin_update[chat_id] = now
        return admins_cache[chat_id]
    except Exception:
        return []

def is_admin(chat_id, user_id):
    return user_id in get_admins(chat_id)

def contains_link(text):
    """Detects links even without 'www' or 'http'"""
    if not text:
        return False
    pattern = r"(?:https?:\/\/)?(?:www\.)?[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:\/\S*)?"
    return re.search(pattern, text) is not None

def send_welcome(chat_id, name):
    """Send a friendly welcome message"""
    msg = f"👋 Welcome, <b>{name}</b>! Please follow the group rules and stay respectful."
    bot.send_message(chat_id, msg)

def mute_user(chat_id, user_id, duration=MUTE_DURATION):
    """Restrict user temporarily"""
    until_time = int(time.time()) + duration
    bot.restrict_chat_member(chat_id, user_id,
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        until_date=until_time
    )

# === EVENT HANDLERS ===

@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_members(message):
    for new_member in message.new_chat_members:
        send_welcome(message.chat.id, new_member.first_name)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def monitor_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text

    # Ignore admin messages
    if is_admin(chat_id, user_id):
        return

    # Initialize counter
    if chat_id not in user_messages:
        user_messages[chat_id] = {}
    if user_id not in user_messages[chat_id]:
        user_messages[chat_id][user_id] = {"count": 0, "last_msg_time": 0}

    # Increment count only for member messages (ignore admins in between)
    now = time.time()
    last_time = user_messages[chat_id][user_id]["last_msg_time"]
    user_messages[chat_id][user_id]["last_msg_time"] = now

    # Reset count if messages are spaced apart
    if now - last_time > 30:
        user_messages[chat_id][user_id]["count"] = 0

    user_messages[chat_id][user_id]["count"] += 1

    # === Flood Protection ===
    if user_messages[chat_id][user_id]["count"] >= SPAM_LIMIT:
        mute_user(chat_id, user_id)
        bot.reply_to(message, f"🚫 User muted for flooding chat ({SPAM_LIMIT} consecutive messages).")
        user_messages[chat_id][user_id]["count"] = 0

    # === Link Protection ===
    elif contains_link(text):
        bot.delete_message(chat_id, message.message_id)
        bot.send_message(chat_id, f"⚠️ {message.from_user.first_name}, links are not allowed.")
        return

# === FLASK SETUP FOR RENDER ===
@app.route('/')
def index():
    return "MGShield bot is active."

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

# === STARTUP MODE ===
if __name__ == "__main__":
    # Use webhook to avoid "Conflict 409" from multiple instances
    url = f"https://{os.getenv('RENDER_EXTERNAL_URL', '')}/{TOKEN}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=url)
    print(f"✅ Webhook set: {url}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))




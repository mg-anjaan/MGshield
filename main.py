import os
import time
import re
import threading
from collections import defaultdict
import telebot
from telebot import types
from flask import Flask

# --- Load Bot Token ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# --- Flask Web Server for Render Keepalive ---
app = Flask(__name__)

@app.route('/')
def home():
    return "MGShield Bot is running fine!", 200

def run():
    app.run(host="0.0.0.0", port=8080)

# --- Background thread to keep Flask alive ---
threading.Thread(target=run).start()

# --- Flood Control Data ---
user_message_times = defaultdict(list)
MAX_MESSAGES = 5       # Allowed messages
INTERVAL = 10          # In seconds
MUTE_DURATION = 60     # Mute for 1 minute

# --- Link Pattern (detects most URLs) ---
LINK_PATTERN = re.compile(r"(https?:\/\/)?(www\.)?([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}|t\.me\/\S+")

# --- Check if a user is admin ---
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        print("Admin check error:", e)
        return False

# --- Welcome New Members ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(message):
    for member in message.new_chat_members:
        welcome_text = (
            f"👋 Welcome, {member.first_name}!\n"
            "Please follow the group rules and keep the chat clean 🙏"
        )
        bot.reply_to(message, welcome_text)

# --- Main Message Monitor ---
@bot.message_handler(func=lambda message: True)
def monitor_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    # --- Ignore messages from admins or bot itself ---
    if is_admin(chat_id, user_id) or message.from_user.is_bot:
        return

    now = time.time()

    # --- Flood Control ---
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < INTERVAL]
    user_message_times[user_id].append(now)

    if len(user_message_times[user_id]) > MAX_MESSAGES:
        try:
            bot.restrict_chat_member(chat_id, user_id, until_date=int(now + MUTE_DURATION))
            bot.send_message(chat_id, f"🤐 {message.from_user.first_name} muted for 1 minute due to spamming.")
            user_message_times[user_id].clear()
        except Exception as e:
            print("Mute error:", e)

    # --- Link Filter ---
    if LINK_PATTERN.search(text):
        try:
            bot.delete_message(chat_id, message.message_id)
            bot.send_message(chat_id, f"🚫 Link removed, {message.from_user.first_name}. Links are not allowed.")
        except Exception as e:
            print("Link delete error:", e)

# --- Start Bot ---
print("🚀 MGShield Bot is now running...")
bot.infinity_polling(skip_pending=True)




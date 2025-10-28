import os
import telebot
import re
import requests
from collections import defaultdict
from requests.exceptions import ConnectionError
from web import keep_alive
keep_alive()

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Read from environment variable
bot = telebot.TeleBot(BOT_TOKEN)

# Track message count and warnings
user_message_count = defaultdict(int)
user_warnings = defaultdict(int)

MAX_MESSAGES = 5  # Flood control limit
LINK_PATTERN = r"(https?://|t\.me|www\.)"  # Anti-link pattern

# --- HELPER: Check admin status ---
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        print("Error checking admin:", e)
        return False

# --- START / HELP ---
@bot.message_handler(commands=['start', 'help'])
def help_command(message):
    help_text = (
        "🛡️ *MGshield Commands*\n\n"
        "/ban - Ban a user\n"
        "/unban - Unban a user\n"
        "/mute - Mute a user\n"
        "/unmute - Unmute a user\n"
        "/warn - Warn a user\n"
        "/help - Show this message\n\n"
        "🧩 Auto moderation enabled:\n"
        "• Flood control (5 msgs)\n"
        "• Anti-link (members only)"
    )

    )
    try:
        bot.reply_to(message, help_text, parse_mode="Markdown")
    except ConnectionError:
        print("Telegram connection interrupted while sending /help.")
    except Exception as e:
        print("Error sending help message:", e)

# --- NEW CHAT MEMBER ---
@bot.my_chat_member_handler()
def handle_new_chat_member(update):
    if update.new_chat_member.status in ["administrator", "member"]:
        chat_id = update.chat.id
        try:
            bot.send_message(
                chat_id,
                "🛡️ *MGShield is now active in this group!*\nMonitoring for spam, flood & links ✅",
                parse_mode="Markdown"
            )
        except ConnectionError:
            print("Telegram API connection interrupted — will retry automatically.")
        except Exception as e:
            print("Error sending activation message:", e)

# --- WARN ---
@bot.message_handler(commands=['warn'])
def warn_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "🚫 Only admins can use this command.")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Reply to the user you want to warn.")
        return

    user_id = message.reply_to_message.from_user.id
    user_warnings[user_id] += 1
    bot.reply_to(message, f"⚠️ User warned! Total warnings: {user_warnings[user_id]}")

# --- MUTE ---
@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "🚫 Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to the user you want to mute.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=False)
        bot.reply_to(message, "🔇 User has been *muted!* ✅", parse_mode="Markdown")
    except Exception as e:
        print("Error muting user:", e)
        bot.reply_to(message, "⚠️ Couldn't mute user.")

# --- ✅ UNMUTE ---
@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "🚫 Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to the user you want to unmute.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=True)
        bot.reply_to(message, "🔊 User has been *unmuted!* ✅", parse_mode="Markdown")
    except Exception as e:
        print("Error unmuting user:", e)
        bot.reply_to(message, "⚠️ Couldn't unmute user.")

# --- BAN ---
@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "🚫 Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to the user you want to ban.")
        return

    try:
        user_id = message.reply_to_message.from_user.id
        bot.ban_chat_member(message.chat.id, user_id)
        bot.reply_to(message, "⛔ User has been *banned!* ✅", parse_mode="Markdown")
    except Exception as e:
        print("Error banning user:", e)
        bot.reply_to(message, "⚠️ Couldn't ban user.")

# --- UNBAN ---
@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "🚫 Only admins can use this command.")
        return
    try:
        if not message.reply_to_message:
            bot.reply_to(message, "Reply to the user you want to unban.")
            return
        user_id = message.reply_to_message.from_user.id
        bot.unban_chat_member(message.chat.id, user_id)
        bot.reply_to(message, "✅ User has been *unbanned!*", parse_mode="Markdown")
    except Exception as e:
        print("Error unbanning user:", e)

# --- AUTO MODERATION ---
@bot.message_handler(func=lambda message: True)
def auto_moderation(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    # Flood control
    user_message_count[user_id] += 1
    if user_message_count[user_id] > MAX_MESSAGES:
        try:
            bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
            bot.reply_to(message, "🤖 Flooding detected! User muted temporarily.")
            user_message_count[user_id] = 0
        except Exception as e:
            print("Error during flood control:", e)

    # Anti-link
    if re.search(LINK_PATTERN, text):
        try:
            if not is_admin(chat_id, user_id):
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(chat_id, "🚫 Links are not allowed for members.")
        except Exception as e:
            print("Error deleting link message:", e)

# --- RUN BOT ---
print("🤖 MGShield is running...")
bot.infinity_polling(skip_pending=True)



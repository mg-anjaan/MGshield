import os
import telebot
import re
from collections import defaultdict
from web import keep_alive

# Keep bot alive on Render
keep_alive()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Track message patterns
user_messages = defaultdict(list)   # store last few message timestamps
user_warnings = defaultdict(int)

# Anti-flood & anti-link configs
MAX_CONTINUOUS = 5   # number of continuous messages before mute
LINK_PATTERN = r"(?i)\b((?:https?://|www\.|t\.me/)?[a-z0-9\-]+\.[a-z]{2,}(?:/\S*)?)"

# ---------- Helper ----------
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        print("Error checking admin:", e)
        return False


# ---------- Start & Help ----------
@bot.message_handler(commands=['start', 'help'])
def help_command(message):
    help_text = (
        "🛡️ *MGshield Bot Commands*\n\n"
        "/ban - Ban a user\n"
        "/unban - Unban a user\n"
        "/mute - Mute a user\n"
        "/unmute - Unmute a user\n"
        "/warn - Warn a user\n"
        "/help - Show this message\n\n"
        "🧩 Auto moderation:\n"
        "• Flood mute (5 continuous msgs)\n"
        "• Anti-link (detects even without http/www)"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")


# ---------- /ban ----------
@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message to ban them.")
        return

    user_id = message.reply_to_message.from_user.id
    bot.ban_chat_member(message.chat.id, user_id)
    bot.reply_to(message, "🚫 User has been banned.")


# ---------- /unban ----------
@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command.")
        return
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /unban <user_id>")
        return

    user_id = message.text.split()[1]
    bot.unban_chat_member(message.chat.id, int(user_id))
    bot.reply_to(message, f"✅ User {user_id} has been unbanned.")


# ---------- /mute ----------
@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message to mute them.")
        return

    user_id = message.reply_to_message.from_user.id
    bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=False)
    bot.reply_to(message, "🔇 User has been muted.")


# ---------- /unmute ----------
@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message to unmute them.")
        return

    user_id = message.reply_to_message.from_user.id
    bot.restrict_chat_member(message.chat.id, user_id, can_send_messages=True)
    bot.reply_to(message, "🔊 User has been unmuted.")


# ---------- /warn ----------
@bot.message_handler(commands=['warn'])
def warn_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Only admins can use this command.")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message to warn them.")
        return

    user_id = message.reply_to_message.from_user.id
    user_warnings[user_id] += 1
    count = user_warnings[user_id]

    bot.reply_to(message, f"⚠️ Warning {count}/3 issued.")
    if count >= 3:
        bot.ban_chat_member(message.chat.id, user_id)
        bot.reply_to(message, "🚫 User banned after 3 warnings.")


# ---------- Auto Moderation ----------
@bot.message_handler(func=lambda m: True)
def auto_moderation(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    # Skip admins
    if is_admin(chat_id, user_id):
        return

    # --- Flood control (5 continuous messages) ---
    user_messages[chat_id].append(user_id)
    if len(user_messages[chat_id]) > MAX_CONTINUOUS:
        user_messages[chat_id].pop(0)

    # Check if same user sent last 5
    if all(u == user_id for u in user_messages[chat_id]) and len(user_messages[chat_id]) == MAX_CONTINUOUS:
        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
        bot.send_message(chat_id, f"🤐 {message.from_user.first_name} muted for spamming 5 continuous messages.")
        user_messages[chat_id].clear()

    # --- Anti-link (detect any type of link) ---
    if re.search(LINK_PATTERN, text):
        bot.delete_message(chat_id, message.message_id)
        bot.send_message(chat_id, f"🔗 Links are not allowed, {message.from_user.first_name}!")


# ---------- Run ----------
print("🤖 MGshield Bot is now running...")
bot.infinity_polling()



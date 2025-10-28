import telebot
from telebot import types
import re
from collections import defaultdict

BOT_TOKEN = "8407192161:AAFxZTEr50v81cso-8jhkg8CZt8rZGG_TCk"  # Replace this later with your token
bot = telebot.TeleBot(BOT_TOKEN)
user_message_count = defaultdict(int)
user_warnings = defaultdict(int)

MAX_MESSAGES = 5  # flood limit
LINK_PATTERN = r"(https?://|t\.me|www\.)"

def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=['start', 'help'])
def help_command(message):
    help_text = (
        "🛡️ *MGshield Commands*\n\n"
        "/ban - Ban a user\n"
        "/unban - Unban a user\n"
        "/mute - Mute a user\n"
        "/warn - Warn a user\n"
        "/help - Show this message\n\n"
        "🧩 Auto moderation enabled:\n"
        "• Flood control (5 msgs)\n"
        "• Anti-link (members only)"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        return
    if message.reply_to_message:
        bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        bot.reply_to(message, "🚫 User banned.")
    else:
        bot.reply_to(message, "Reply to a user's message to ban them.")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        return
    if message.reply_to_message:
        bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        bot.reply_to(message, "✅ User unbanned.")
    else:
        bot.reply_to(message, "Reply to a user's message to unban them.")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        return
    if message.reply_to_message:
        bot.restrict_chat_member(message.chat.id, message.reply_to_message.from_user.id, can_send_messages=False)
        bot.reply_to(message, "🔇 User muted.")
    else:
        bot.reply_to(message, "Reply to a user's message to mute them.")

@bot.message_handler(commands=['warn'])
def warn_user(message):
    if not is_admin(message.chat.id, message.from_user.id):
        return
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_warnings[user_id] += 1
        bot.reply_to(message, f"⚠️ Warning {user_warnings[user_id]} issued.")
        if user_warnings[user_id] >= 3:
            bot.ban_chat_member(message.chat.id, user_id)
            bot.send_message(message.chat.id, "🚫 User auto-banned after 3 warnings.")
    else:
        bot.reply_to(message, "Reply to a user's message to warn them.")

@bot.message_handler(func=lambda msg: True)
def auto_moderate(message):
    if message.chat.type not in ["group", "supergroup"]:
        return
    if is_admin(message.chat.id, message.from_user.id):
        return

    user_message_count[message.from_user.id] += 1

    if re.search(LINK_PATTERN, message.text or ""):
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "⚠️ Sending links is not allowed.")
        return

    if user_message_count[message.from_user.id] >= MAX_MESSAGES:
        bot.restrict_chat_member(message.chat.id, message.from_user.id, can_send_messages=False)
        bot.send_message(message.chat.id, "🤐 You are muted for flooding.")
        user_message_count[message.from_user.id] = 0

print("🤖 MGshield is running...")
bot.polling()


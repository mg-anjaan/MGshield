import telebot
from flask import Flask, request
import time, re

# === Replace this with your bot token ===
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === Config ===
APP_URL = "https://mgshield.onrender.com"  # your Render URL
FLOOD_LIMIT = 5
TIME_WINDOW = 20  # seconds
WARN_LIMIT = 3

# === Data storage ===
user_message_count = {}  # Flood tracker
user_warns = {}          # Warnings

# === Helper: check if user is admin ===
def is_admin(chat_id, user_id):
    try:
        admins = bot.get_chat_administrators(chat_id)
        return any(a.user.id == user_id for a in admins)
    except:
        return False

# === Welcome message ===
@bot.chat_member_handler()
def welcome(message):
    try:
        if message.new_chat_member and not message.new_chat_member.user.is_bot:
            name = message.new_chat_member.user.first_name
            bot.send_message(
                message.chat.id,
                f"👋 Welcome {name} to *{message.chat.title}*! Please follow the rules.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print("Welcome error:", e)

# === Flood + Link Protection ===
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_messages(m):
    chat_id, user_id = m.chat.id, m.from_user.id
    text = m.text or ""

    # Ignore admins
    if is_admin(chat_id, user_id):
        return

    # ---- Anti-link detection ----
    if re.search(r"(https?://|www\.|\.com|\.in|\.org|\.net|t\.me|telegram\.me)", text, re.IGNORECASE):
        try:
            bot.delete_message(chat_id, m.message_id)
            warn_user(chat_id, user_id, m.from_user.first_name, reason="link sharing")
        except Exception as e:
            print("Link delete error:", e)
        return

    # ---- Flood control ----
    now = time.time()
    user_message_count.setdefault(chat_id, {}).setdefault(user_id, [])
    msgs = user_message_count[chat_id][user_id]
    msgs.append(now)
    user_message_count[chat_id][user_id] = [t for t in msgs if now - t < TIME_WINDOW]

    if len(user_message_count[chat_id][user_id]) >= FLOOD_LIMIT:
        mute_user(chat_id, user_id, m.from_user.first_name, reason="spamming")
        user_message_count[chat_id][user_id].clear()

# === Command: /warn ===
@bot.message_handler(commands=['warn'])
def cmd_warn(m):
    if not is_admin(m.chat.id, m.from_user.id): return
    if not m.reply_to_message:
        bot.reply_to(m, "⚠️ Reply to a user's message to warn them.")
        return
    user = m.reply_to_message.from_user
    warn_user(m.chat.id, user.id, user.first_name, reason="manual warning")

# === Command: /mute ===
@bot.message_handler(commands=['mute'])
def cmd_mute(m):
    if not is_admin(m.chat.id, m.from_user.id): return
    if not m.reply_to_message:
        bot.reply_to(m, "Reply to a user's message to mute.")
        return
    user = m.reply_to_message.from_user
    mute_user(m.chat.id, user.id, user.first_name, reason="manual mute")

# === Command: /unmute ===
@bot.message_handler(commands=['unmute'])
def cmd_unmute(m):
    if not is_admin(m.chat.id, m.from_user.id): return
    if not m.reply_to_message:
        bot.reply_to(m, "Reply to a user's message to unmute.")
        return
    user = m.reply_to_message.from_user
    try:
        bot.restrict_chat_member(
            m.chat.id, user.id,
            permissions=telebot.types.ChatPermissions(can_send_messages=True)
        )
        bot.send_message(m.chat.id, f"✅ Unmuted [{user.first_name}](tg://user?id={user.id}).", parse_mode="Markdown")
    except Exception as e:
        print("Unmute error:", e)

# === Command: /ban ===
@bot.message_handler(commands=['ban'])
def cmd_ban(m):
    if not is_admin(m.chat.id, m.from_user.id): return
    if not m.reply_to_message:
        bot.reply_to(m, "Reply to a user's message to ban.")
        return
    user = m.reply_to_message.from_user
    try:
        bot.ban_chat_member(m.chat.id, user.id)
        bot.send_message(m.chat.id, f"🔨 Banned [{user.first_name}](tg://user?id={user.id}).", parse_mode="Markdown")
    except Exception as e:
        print("Ban error:", e)

# === Command: /unban ===
@bot.message_handler(commands=['unban'])
def cmd_unban(m):
    if not is_admin(m.chat.id, m.from_user.id): return
    if len(m.text.split()) < 2 and not m.reply_to_message:
        bot.reply_to(m, "Usage: `/unban <user_id>` or reply to a banned user.", parse_mode="Markdown")
        return

    try:
        if m.reply_to_message:
            user_id = m.reply_to_message.from_user.id
        else:
            user_id = int(m.text.split()[1])

        bot.unban_chat_member(m.chat.id, user_id)
        bot.send_message(m.chat.id, f"✅ Unbanned user ID `{user_id}` successfully.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(m, f"Error while unbanning: {e}")

# === Helpers ===
def warn_user(chat_id, user_id, name, reason):
    user_warns.setdefault(chat_id, {}).setdefault(user_id, 0)
    user_warns[chat_id][user_id] += 1
    count = user_warns[chat_id][user_id]
    bot.send_message(chat_id, f"⚠️ [{name}](tg://user?id={user_id}) warned for {reason}. ({count}/{WARN_LIMIT})", parse_mode="Markdown")

    if count >= WARN_LIMIT:
        mute_user(chat_id, user_id, name, reason="too many warnings")
        user_warns[chat_id][user_id] = 0

def mute_user(chat_id, user_id, name, reason):
    try:
        bot.restrict_chat_member(
            chat_id, user_id,
            until_date=int(time.time()) + 60,
            permissions=telebot.types.ChatPermissions(can_send_messages=False)
        )
        bot.send_message(chat_id, f"🚫 [{name}](tg://user?id={user_id}) muted for {reason}.", parse_mode="Markdown")
    except Exception as e:
        print("Mute error:", e)

# === Webhook routes ===
@app.route(f"/{BOT_TOKEN}/", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.data.decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/')
def index():
    return "🤖 MGShield v4 running with full moderation."

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{APP_URL}/{BOT_TOKEN}/")
    print("✅ Webhook set successfully for MGShield v4.")




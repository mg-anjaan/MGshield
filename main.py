import os, logging, json, asyncio, html
from datetime import datetime, timedelta
from aiohttp import web

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Config (from env or data/config.json)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
OWNER_ID = int(os.environ.get('OWNER_ID','0') or 0)
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID','0') or 0)
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')  # e.g. https://<service>.onrender.com/webhook
PORT = int(os.environ.get('PORT','8080'))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
WARNS_PATH = os.path.join(DATA_DIR, "warns.json")
MUTES_PATH = os.path.join(DATA_DIR, "mutes.json")
LOGS_PATH = os.path.join(DATA_DIR, "logs.json")

# defaults
DEFAULT_CONFIG = {
    "WELCOME_TEXT": "Welcome to the group! Please press Verify ✅ to chat. Read pinned rules.",
    "RULES_TEXT": "Be respectful. No spam. No hate.",
    "WARN_LIMIT": 3,
    "AUTO_DELETE_LINKS": True,
    "PROFANITY_LIST": ["badword1","badword2"],
    "FLOOD_LIMIT": 5,
    "FLOOD_WINDOW": 10,   # seconds
    "MUTE_DURATION": 60   # seconds
}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mgshield")

# --- JSON helpers ---
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception("Failed to save %s: %s", path, e)

config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
warns = load_json(WARNS_PATH, {})
mutes = load_json(MUTES_PATH, {})
logs = load_json(LOGS_PATH, [])

# utility
def log_action(text):
    entry = {"time": datetime.utcnow().isoformat()+"Z", "text": text}
    logs.append(entry)
    save_json(LOGS_PATH, logs)

def is_admin_member(chat_member):
    return chat_member.status in ("administrator","creator")

# flood control in-memory timestamps per user per chat
flood = {}  # {(chat_id, user_id): [timestamps]}

def record_message(chat_id, user_id, window):
    key = (chat_id, user_id)
    now = datetime.utcnow().timestamp()
    lst = flood.get(key, [])
    # keep only timestamps within window
    lst = [t for t in lst if now - t < window]
    lst.append(now)
    flood[key] = lst
    return len(lst)

def warn_user(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    val = warns.get(key, 0) + 1
    warns[key] = val
    save_json(WARNS_PATH, warns)
    return val

def reset_warns(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    if key in warns:
        warns.pop(key)
        save_json(WARNS_PATH, warns)

async def restrict_member(bot, chat_id, user_id, seconds=None):
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
        if seconds:
            # schedule unmute
            unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).timestamp()
            mutes[f"{chat_id}:{user_id}"] = unmute_at
            save_json(MUTES_PATH, mutes)
    except Exception as e:
        logger.exception("restrict_member failed: %s", e)

async def lift_restriction(bot, chat_id, user_id):
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        key = f"{chat_id}:{user_id}"
        if key in mutes:
            mutes.pop(key)
            save_json(MUTES_PATH, mutes)
    except Exception as e:
        logger.exception("lift_restriction failed: %s", e)

# --- Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("MGshield active. /help for commands.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = ("/help - show help\n"
           "/rules - show group rules\n"
           "/warn - reply to a user to warn them (admins only)\n"
           "/unwarn - clear warns for user (admins only)\n"
           "/mute - reply to a user to mute them (admins only)\n"
           "/unmute - reply to a user to unmute them (admins only)\n"
           "/setfloodlimit - (admin) set flood limit\n")
    await update.message.reply_text(txt)

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config.get("RULES_TEXT",""))

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        try:
            # restrict until verification
            await context.bot.restrict_chat_member(update.effective_chat.id, member.id, permissions=ChatPermissions(can_send_messages=False))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Verify ✅", callback_data=f"verify:{member.id}")]])
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{member.mention_html()}\n{config.get('WELCOME_TEXT')}", parse_mode='HTML', reply_markup=kb)
            log_action(f"Restricted new member {member.id} in {update.effective_chat.id}")
        except Exception as e:
            logger.exception("new_member handler error: %s", e)

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data.startswith("verify:"):
        try:
            user_id = int(data.split(":",1)[1])
            if q.from_user.id != user_id:
                await q.edit_message_text("This verify button is not for you.")
                return
            await lift_restriction(context.bot, q.message.chat_id, user_id)
            await q.edit_message_text("✅ Verified — you can now chat. Welcome!")
            log_action(f"User {user_id} verified in chat {q.message.chat_id}")
            if ADMIN_CHAT_ID:
                await context.bot.send_message(ADMIN_CHAT_ID, f"User {q.from_user.mention_html()} verified in {q.message.chat.title}", parse_mode='HTML')
        except Exception as e:
            logger.exception("button_cb error: %s", e)

# admin check helper
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return is_admin_member(member)

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to warn them.")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    target = update.message.reply_to_message.from_user
    count = warn_user(update.effective_chat.id, target.id)
    await update.message.reply_text(f"⚠️ {html.escape(target.full_name)} warned ({count}/{config.get('WARN_LIMIT')})")
    log_action(f"Admin {update.effective_user.id} warned {target.id} in {update.effective_chat.id}")
    if count >= config.get("WARN_LIMIT"):
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id)
            reset_warns(update.effective_chat.id, target.id)
            await update.message.reply_text(f"🚫 {html.escape(target.full_name)} has been banned after reaching warn limit.")
            log_action(f"Auto-banned {target.id} in {update.effective_chat.id}")
        except Exception as e:
            logger.exception("Auto-ban failed: %s", e)

async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to clear warns.")
        return
    target = update.message.reply_to_message.from_user
    reset_warns(update.effective_chat.id, target.id)
    await update.message.reply_text(f"✅ Cleared warnings for {html.escape(target.full_name)}")
    log_action(f"{update.effective_user.id} cleared warns for {target.id} in {update.effective_chat.id}")

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to mute them.")
        return
    target = update.message.reply_to_message.from_user
    # mute duration optional argument (seconds)
    try:
        seconds = int(context.args[0]) if context.args else config.get("MUTE_DURATION",60)
    except Exception:
        seconds = config.get("MUTE_DURATION",60)
    await restrict_member(context.bot, update.effective_chat.id, target.id, seconds)
    await update.message.reply_text(f"🔇 {html.escape(target.full_name)} muted for {seconds} seconds.")
    log_action(f"{update.effective_user.id} muted {target.id} in {update.effective_chat.id} for {seconds}s")

async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user to unmute them.")
        return
    target = update.message.reply_to_message.from_user
    await lift_restriction(context.bot, update.effective_chat.id, target.id)
    await update.message.reply_text(f"🔊 {html.escape(target.full_name)} unmuted.")
    log_action(f"{update.effective_user.id} unmuted {target.id} in {update.effective_chat.id}")

# message handler: anti-link (members only), profanity, flood
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    # only text for now
    text = (msg.text or "").lower()
    # admin exemption
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, msg.from_user.id)
        if is_admin_member(member):
            return  # admins free: do not enforce link/profanity/flood
    except Exception:
        # if error fetching member, proceed conservatively
        pass

    # flood control
    cnt = record_message(update.effective_chat.id, msg.from_user.id, config.get("FLOOD_WINDOW",10))
    if cnt > config.get("FLOOD_LIMIT",5):
        # mute temporarily
        await msg.delete()
        await restrict_member(context.bot, update.effective_chat.id, msg.from_user.id, config.get("MUTE_DURATION",60))
        await context.bot.send_message(update.effective_chat.id, f"🤐 You are temporarily muted for spamming, {msg.from_user.mention_html()}", parse_mode='HTML')
        log_action(f"Auto-mute for flood: {msg.from_user.id} in {update.effective_chat.id}")
        return

    # anti-link (members only): delete and warn
    if config.get("AUTO_DELETE_LINKS", True) and ("http://" in text or "https://" in text or "t.me/" in text):
        try:
            await msg.delete()
            await context.bot.send_message(update.effective_chat.id, f"🚫 Sending links is not allowed in this group.", parse_mode='HTML')
            log_action(f"Deleted link from {msg.from_user.id} in {update.effective_chat.id}")
        except Exception:
            pass
        return

    # profanity
    for bad in config.get("PROFANITY_LIST", []):
        if bad and bad in text:
            try:
                await msg.delete()
                await context.bot.send_message(update.effective_chat.id, f"Please avoid that language, {msg.from_user.mention_html()}", parse_mode='HTML')
                c = warn_user(update.effective_chat.id, msg.from_user.id)
                log_action(f"Profanity warn {msg.from_user.id} ({c}) in {update.effective_chat.id}")
                if c >= config.get("WARN_LIMIT",3):
                    await context.bot.ban_chat_member(update.effective_chat.id, msg.from_user.id)
                    reset_warns(update.effective_chat.id, msg.from_user.id)
                    log_action(f"Auto-banned {msg.from_user.id} in {update.effective_chat.id}")
                return
            except Exception:
                pass

# periodic task to lift mutes when expired
async def mute_watcher(app):
    while True:
        now = datetime.utcnow().timestamp()
        changed = False
        for key, ts in list(mutes.items()):
            if now >= ts:
                chat_id, user_id = key.split(":",1)
                try:
                    await lift_restriction(app.bot, int(chat_id), int(user_id))
                    log_action(f"Auto-unmute {user_id} in {chat_id}")
                except Exception:
                    pass
                mutes.pop(key, None)
                changed = True
        if changed:
            save_json(MUTES_PATH, mutes)
        await asyncio.sleep(5)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = await context.bot.get_chat(update.effective_chat.id)
        await update.message.reply_text(f"Chat: {chat.title}\\nMembers: {chat.get_members_count()}")
    except Exception:
        await update.message.reply_text("Unable to fetch stats.")

# Bot setup and run (webhook or polling fallback)
async def run():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Exiting.")
        return
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    # commands
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("rules", rules_cmd))
    application.add_handler(CommandHandler("warn", warn_cmd))
    application.add_handler(CommandHandler("unwarn", unwarn_cmd))
    application.add_handler(CommandHandler("mute", mute_cmd))
    application.add_handler(CommandHandler("unmute", unmute_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    # callbacks and messages
    application.add_handler(CallbackQueryHandler(button_cb))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), on_message))

    # start background mute watcher
    application.post_init = lambda app: asyncio.create_task(mute_watcher(app))

    if WEBHOOK_URL:
        # webhook mode: set webhook and run aiohttp server for Telegram updates
        logger.info("Starting in webhook mode. Setting webhook to %s", WEBHOOK_URL)
        await application.bot.set_webhook(WEBHOOK_URL)
        # use aiohttp web app to accept updates (Application.run_webhook can set up server but we'll use run_webhook below)
        await application.run_webhook(listen="0.0.0.0", port=PORT, webhook_path="/webhook", webhook_url=WEBHOOK_URL)
    else:
        logger.info("Starting in polling mode (no WEBHOOK_URL provided).")
        await application.run_polling()

if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

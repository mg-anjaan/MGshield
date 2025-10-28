# MGshield - Telegram Moderation Bot (Full Free Version)


This package contains a webhook-ready Telegram moderation bot suitable for free Render hosting.

## What's included

- `main.py` - bot code (webhook-ready)
- `requirements.txt` - Python dependencies
- `.env.example` - example env variables
- `data/` - JSON storage files (warns, mutes, logs, config)

## Quick setup (Render)

1. Create a new GitHub repo and upload these files (or push from Termux).
2. In Render, create a new **Web Service** and connect your GitHub repo.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. Set environment variables in Render:
   - `BOT_TOKEN` (from @BotFather)
   - `WEBHOOK_URL` (e.g. https://<your-service>.onrender.com/webhook)
   - `ADMIN_CHAT_ID` (optional)
6. Deploy. The bot will set webhook automatically and start.

## Notes
- Admins are exempt from link deletion, flood control, and profanity enforcement.
- Link messages from regular members are deleted and the bot sends: "🚫 Sending links is not allowed in this group." 
- Data is stored in `data/` as JSON. For multi-instance production move to a DB.

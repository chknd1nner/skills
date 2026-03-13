# Telegram Setup Guide

You need two things: a **bot token** and your **chat ID**.

---

## Step 1: Create a bot and get the token

1. Open Telegram and search for `@BotFather`
2. Start a conversation and send `/newbot`
3. Follow the prompts:
   - Choose a display name (e.g. `Claude Memory`)
   - Choose a username ending in `bot` (e.g. `claude_memory_chknd1nner_bot`)
4. BotFather replies with your token — looks like `7123456789:AAFxxxxx...`
5. Copy and save it

---

## Step 2: Get your chat ID

1. Search for your new bot by its username in Telegram and start a conversation
2. Send it any message (e.g. `hello`)
3. In your browser, open:
   ```
   https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates
   ```
   Replace `{YOUR_TOKEN}` with the token from Step 1.
4. You'll see JSON — look for `"chat":{"id": 123456789`. That number is your chat ID.

> If the JSON shows `"result":[]`, send another message to the bot and refresh the URL.

---

## Step 3: Add to your `.env` file

```
PAT = ghp_xxxx
MEMORY_REPO = chknd1nner/claude-memory-journal
TELEGRAM_BOT_TOKEN = 7123456789:AAFxxxxx...
TELEGRAM_CHAT_ID = 123456789
```

---

## Step 4: Test it

Run this from the project root:

```bash
python skills/continuity-memory/scripts/test_telegram.py
```

Expected: a message arrives in your Telegram chat from your bot within a few seconds.

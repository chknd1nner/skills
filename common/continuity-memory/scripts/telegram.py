"""
Telegram send/receive for the Ralph Wiggum loop.
Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from _env file.
"""

import os
from typing import Optional
import requests


def _load_env(env_path: str = "/mnt/project/_env") -> dict:
    env = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def send(message: str, env_path: str = "/mnt/project/_env") -> bool:
    """Send a Telegram message. Returns True on success."""
    env = _load_env(env_path)
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": message})
    return response.ok


def poll(env_path: str = "/mnt/project/_env", offset_file: Optional[str] = None) -> Optional[str]:
    """
    Check for new Telegram messages from the owner.

    Reads unprocessed updates since last call, filters to messages from
    TELEGRAM_CHAT_ID, advances the offset so messages aren't re-read.

    Args:
        env_path:    Path to env file with credentials.
        offset_file: Path to persist the update offset between calls.
                     If None, offset resets on each call (re-reads all history).

    Returns:
        Most recent message text, or None if no new messages.
    """
    env = _load_env(env_path)
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = str(env.get("TELEGRAM_CHAT_ID", ""))

    if not token or not chat_id:
        return None

    # Load persisted offset
    offset = 0
    if offset_file and os.path.exists(offset_file):
        try:
            with open(offset_file) as f:
                offset = int(f.read().strip() or 0)
        except (ValueError, IOError):
            offset = 0

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        response = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=5)
    except requests.RequestException:
        return None

    if not response.ok:
        return None

    updates = response.json().get("result", [])
    if not updates:
        return None

    messages = []
    new_offset = offset

    for update in updates:
        new_offset = update["update_id"] + 1
        msg = update.get("message", {})
        if str(msg.get("chat", {}).get("id", "")) == chat_id:
            text = msg.get("text", "").strip()
            if text:
                messages.append(text)

    # Persist offset so we don't re-read these updates
    if offset_file and new_offset > offset:
        try:
            os.makedirs(os.path.dirname(offset_file), exist_ok=True)
            with open(offset_file, "w") as f:
                f.write(str(new_offset))
        except IOError:
            pass

    return messages[-1] if messages else None

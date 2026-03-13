import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(__file__))

from telegram import send

env_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", ".env"
)
env_path = os.path.abspath(env_path)

result = send("Test from claude-continuity-memory: Telegram is working.", env_path=env_path)
print("Sent:", result)

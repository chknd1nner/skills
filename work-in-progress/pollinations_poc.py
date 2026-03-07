#!/usr/bin/env python3
"""
Pollinations.ai POC - Summarise chat transcript using Claude model.
Benchmarks: time to first token, total duration, chars/tokens processed.
"""

import requests
import time
from pathlib import Path

ENDPOINT = "https://gen.pollinations.ai/v1/chat/completions"
API_KEY = "sk_pT4jppAWsj2G8fVDGdm1gs2WDyni0Adw"
CHAT_FILE = Path(__file__).parent / "chats" / "Pollinations.ais free image generation business model.md"

SYSTEM_PROMPT = """You are a concise summariser. Given a chat transcript, produce a structured summary with:

## Key Topics Discussed
- Bullet points of main subjects covered

## Key Insights
- Most valuable or surprising findings from the conversation

## Action Items / Ideas Generated
- Any concrete next steps or project ideas that emerged

## One-Line Verdict
A single sentence capturing the overall conclusion or takeaway.

Be concise. No waffle."""

def run():
    # Read transcript
    transcript = CHAT_FILE.read_text(encoding="utf-8")
    char_count = len(transcript)
    # Rough token estimate: ~4 chars per token
    est_tokens = char_count // 4

    print(f"Transcript loaded: {char_count:,} chars (~{est_tokens:,} tokens estimated)")
    print(f"Sending to Pollinations (model: claude-fast / Haiku 4.5)...\n")

    payload = {
        "model": "claude-fast",  # Haiku 4.5 - free with auth key
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the chat transcript to summarise:\n\n{transcript}"}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    t_start = time.perf_counter()
    response = requests.post(ENDPOINT, json=payload, headers=headers, timeout=120)
    t_end = time.perf_counter()

    duration = t_end - t_start
    status = response.status_code

    print(f"--- Response ---")
    print(f"HTTP status : {status}")
    print(f"Duration    : {duration:.2f}s")

    if status != 200:
        print(f"Error body  : {response.text}")
        return

    data = response.json()

    # Extract content
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    prompt_tokens = usage.get("prompt_tokens", "n/a")
    completion_tokens = usage.get("completion_tokens", "n/a")
    total_tokens = usage.get("total_tokens", "n/a")

    print(f"Prompt tokens    : {prompt_tokens}")
    print(f"Completion tokens: {completion_tokens}")
    print(f"Total tokens     : {total_tokens}")
    if isinstance(completion_tokens, int) and duration > 0:
        print(f"Output speed     : {completion_tokens / duration:.1f} tokens/sec")
    print(f"\n{'='*60}\nSUMMARY OUTPUT\n{'='*60}\n")
    print(content)
    print(f"\n{'='*60}")
    print(f"Total wall time: {duration:.2f}s")

if __name__ == "__main__":
    run()

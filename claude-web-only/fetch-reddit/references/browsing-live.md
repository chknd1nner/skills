# Browsing Live (Redlib)

Real-time Reddit content via Redlib instances with Anubis PoW solving.

## Command

### live-browse

Browse a subreddit's current listings with real-time scores.

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse SUBREDDIT [--sort hot|new|rising|top]
```

**Flags:**
- `--sort` — Sort order: `hot` (default), `new`, `rising`, `top`

**Output:** Post listing with title, author, score, comment count, flair, relative timestamp, and Redlib permalink.

**Examples:**
```bash
# What's hot right now
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse ClaudeAI

# Latest posts
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse LocalLLaMA --sort new

# Rising posts (gaining traction)
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse programming --sort rising
```

**When to use:**
- "What's trending in r/X?"
- "Show me the hot posts"
- "What's new in r/X today?"
- Any request for current/fresh content

## Limitations

- **No search:** Redlib does not support keyword search.
- **No filters:** Redlib doesn't support flair, time range, or author filtering.
- **No pagination:** Returns whatever Redlib's page shows (typically 25 posts).
- **HTML parsing:** If Redlib changes their HTML structure, parsers may break. The script will report "HTML may have changed".
- **Instance failover:** At the start of each chat, the first command fetches the current instance list from the official Redlib registry (`github.com/redlib-org/redlib-instances`). The script then tries instances in order until one returns valid content. If all fail — typically because Reddit is blocking that instance's API calls — it reports each failure reason explicitly.

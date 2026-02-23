# Browsing Live (Redlib)

Real-time Reddit content via Redlib instances with Anubis PoW solving. Use these commands when the user wants current/trending content or posts newer than ~36 hours (not yet indexed by Arctic Shift).

## Commands

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

### live-post

Fetch a single post with real-time score and content.

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID [--comments N]
```

**Flags:**
- `--comments N` — Also fetch top N comments (sorted by score)

**Output:** Full post detail with title, author, score, comment count, upvote ratio, body text, and optionally top comments.

**Examples:**
```bash
# Post only
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv

# Post with top 20 comments
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv --comments 20
```

**When to use:**
- User wants current score/vote counts
- Post is very recent (< 36 hours)
- User explicitly asks for "live" or "current" data

### live-comments

Fetch comments for a post with real-time scores and nested threading.

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID [--limit N]
```

**Flags:**
- `--limit N` — Number of top comments to return (default: 20)

**Output:** Comments sorted by score descending, with author, score, OP indicator, and indentation for reply depth.

**Examples:**
```bash
# Default top 20
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments 1r7vovv

# More comments for a busy thread
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments 1r7vovv --limit 40
```

## Limitations

- **No search:** Redlib does not support keyword search. Use the archive `search` command instead.
- **No filters:** Redlib doesn't support flair, time range, or author filtering. Use archive `browse` for filtered listings.
- **No pagination:** Returns whatever Redlib's page shows (typically 25 posts).
- **HTML parsing:** If Redlib changes their HTML structure, parsers may break. The script will report "HTML may have changed" — fall back to archive commands.
- **Instance failover:** The script tries multiple Redlib instances in order. If all fail, it reports which instances were tried and why each failed.

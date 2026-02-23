# User and Subreddit Info

Commands for looking up user activity, user profile stats, and subreddit metadata. All via Arctic Shift.

## User activity

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user USERNAME [--limit N] [--after TIME] [--before TIME]
```

Returns a user's recent posts and comments with body previews, scores, and timestamps.

**Flags:**
- `--limit N` — Number of posts and comments each (default: 25)
- `--after TIME` — Activity after this time
- `--before TIME` — Activity before this time

**Examples:**
```bash
# Recent activity
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user spez

# Activity in a time range
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user spez --after 2024-01-01 --before 2024-06-01

# More results
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user spez --limit 50
```

## User profile stats

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user-info USERNAME
```

Returns profile-level stats: total karma, post/comment karma breakdown, post and comment counts, first and last activity dates.

**Example:**
```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user-info spez
```

**Sample output:**
```
# u/spez

**Total karma:** 1,234,567
**Post karma:** 456,789 | **Comment karma:** 777,778
**Posts:** 1,234 | **Comments:** 56,789
**First post:** 2005-06-06 00:00 UTC
**Last post:** 2024-12-01 15:30 UTC
**Last comment:** 2024-12-15 10:00 UTC
```

## Subreddit metadata

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py subreddit-info SUBREDDIT
```

Returns subreddit metadata: subscriber count, active users, creation date, title, public description, and detailed description.

**Example:**
```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py subreddit-info ClaudeAI
```

**Sample output:**
```
# r/ClaudeAI

**Subscribers:** 123,456
**Active users:** 1,234
**Created:** 2023-03-15 00:00 UTC
**Title:** Claude AI by Anthropic

A community for discussing Claude AI...

---
[Extended description truncated at 1000 chars]
```

## When to use which command

| User wants... | Command |
|---|---|
| "What has u/X been posting?" | `user` |
| "Show me my recent Reddit activity" | `user` (ask for username first) |
| "What's u/X's karma?" | `user-info` |
| "How long has u/X been on Reddit?" | `user-info` |
| "Tell me about r/X" | `subreddit-info` |
| "How many subscribers does r/X have?" | `subreddit-info` |
| "What did u/X post in r/Y?" | `browse --author X` (in subreddit Y) |

# Searching Posts (Arctic Shift)

Full-text keyword search within a subreddit via Arctic Shift. Redlib has no search capability — this is the only way to find posts by keyword.

## Command

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search SUBREDDIT "keywords" [flags]
```

**Flags:**
- `--limit N` — Number of results (default: 25)
- `--title-only` — Search only in post titles
- `--body-only` — Search only in post bodies (selftext)
- `--flair "TEXT"` — Filter by flair (exact match)
- `--after TIME` — Posts after this time
- `--before TIME` — Posts before this time
- `--author USERNAME` — Filter by author

## Search modes

By default, `search` performs full-text search across both title and body. Use `--title-only` or `--body-only` to narrow:

```bash
# Full-text (title + body)
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "prompt caching"

# Title only — useful when you know the post title
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "prompt caching" --title-only

# Body only — find posts that discuss a topic in detail
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "system prompt" --body-only
```

## Combining filters

```bash
# Search with flair filter
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "API" --flair "Bug"

# Search within a time range
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search LocalLLaMA "fine tuning" --after 30d

# Search by a specific author
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "artifacts" --author someuser

# Combine multiple filters
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search ClaudeAI "tool use" --title-only --after 7d --limit 10
```

## Pagination

Same as `browse` — when results equal the `--limit`, a pagination hint appears:

```
<!-- next_page: --before 1708900000 -->
```

Pass via `--before` for the next page.

## Limitations

- **Subreddit required:** Arctic Shift does not support Reddit-wide full-text search. You must specify a subreddit.
- **Data freshness:** Posts newer than ~36 hours may not appear. For very recent posts, use `live-browse` and scan visually.
- **No regex:** Search is plain-text matching, not regex.

## When to use

- "Find posts about X in r/Y"
- "Has anyone discussed Z?"
- "Search r/X for posts mentioning Y"
- Any keyword-based query — `live-browse` cannot search, only list.

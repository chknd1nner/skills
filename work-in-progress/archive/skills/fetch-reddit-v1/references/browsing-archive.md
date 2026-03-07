# Browsing Archive (Arctic Shift)

Browse subreddit posts with filtering and pagination via the Arctic Shift archive API. Use this when the user wants filtered results, historical data, or content older than ~36 hours.

## Command

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse SUBREDDIT [flags]
```

**Flags:**
- `--limit N` — Number of posts (default: 25)
- `--flair "TEXT"` — Filter by flair (exact match)
- `--after TIME` — Posts after this time (e.g., `7d`, `30d`, `2024-01-01`, unix epoch)
- `--before TIME` — Posts before this time (same formats)
- `--nsfw` — Include NSFW posts
- `--author USERNAME` — Filter by post author

## Examples

```bash
# Recent posts (default)
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI

# Posts with specific flair
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI --flair "Bug"

# Posts from last week
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse LocalLLaMA --after 7d

# Posts in a time range
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI --after 2024-06-01 --before 2024-07-01

# Combine filters
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI --flair "Discussion" --after 30d --limit 10

# Posts by a specific author in a subreddit
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI --author someuser
```

## Pagination

When results equal the `--limit`, the output includes a pagination hint:

```
<!-- next_page: --before 1708900000 -->
```

Pass this timestamp via `--before` to get the next page:

```bash
# Page 2
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse ClaudeAI --before 1708900000
```

## When to use vs. live-browse

| Situation | Use |
|---|---|
| Current/trending content | `live-browse` |
| Filtered by flair, time, or author | `browse` |
| Historical research | `browse` with `--after`/`--before` |
| Paginating through many posts | `browse` with `--before` |

## Time format examples

- Relative: `7d` (7 days ago), `30d`, `1h`
- ISO date: `2024-01-01`, `2024-06-15`
- Unix epoch: `1708900000`

# Arctic Shift API — Complete Reference

**Base URL:** `https://arctic-shift.photon-reddit.com`
**Auth:** None required
**Rate limits:** Not formally documented; "Timeout. Maybe slow down a bit" errors observed under rapid-fire testing
**Response format:** `{ "data": [...] }` — no pagination metadata, cursor, or total count

---

## Endpoints

### 1. `GET /api/posts/search`

Search and browse posts. The primary workhorse.

| Parameter | Type | Notes |
|---|---|---|
| `subreddit` | string | Exact match only. No wildcards, no comma-separated multiples. |
| `author` | string | Filter by post author. Works cross-subreddit when subreddit is omitted. |
| `query` | string | Full-text search. **Requires** `subreddit` or `author` — cannot search all of Reddit. |
| `title` | string | Search within post titles only. Can combine with `query`. |
| `selftext` | string | Search within post body text only. |
| `link_flair_text` | string | Exact flair match (e.g., `"News"`, `"Bug"`, `"💙 Companionship"`). |
| `author_flair_text` | string | Filter by author's flair in that sub (e.g., `"Anthropic"` catches official posts). |
| `url` | string | Filter by link URL. Must be 14-500 chars (not a domain filter — needs substantial URL). |
| `over_18` | bool | NSFW filter. `true` or `false`. |
| `spoiler` | bool | Spoiler-tagged posts. |
| `distinguished` | string | `"moderator"` for mod-distinguished posts. |
| `after` | date | Posts after this time. Accepts: unix epoch, ISO date, ISO datetime, or relative (`1h`, `6h`, `1d`, `3d`, `7d`, `30d`, `1y`). Note: `1w` does NOT work — use `7d`. |
| `before` | date | Posts before this time. Same formats as `after`. |
| `sort` | enum | `asc` or `desc` only. |
| `sort_type` | enum | `default` or `created_utc` only. Both behave identically (time-based). **No sort by score.** |
| `limit` | int | 1–100. Default varies. |
| `fields` | string | Comma-separated field names to return (reduces payload). |

**Key limitations:**
- No score-based sorting or filtering (no `min_score`, no `sort_type=score`)
- No cross-Reddit full-text search (need subreddit or author)
- No multi-subreddit queries
- No offset/skip — pagination only via `before`/`after` timestamps

### 2. `GET /api/comments/search`

Search and retrieve comments.

| Parameter | Type | Notes |
|---|---|---|
| `subreddit` | string | Exact match. |
| `author` | string | Comment author. |
| `body` | string | Full-text search within comment bodies. Requires `subreddit` or `author` (same constraint as posts). |
| `link_id` | string | Post ID (with or without `t3_` prefix). Returns all comments for that post. |
| `parent_id` | string | Parent comment ID (`t1_xxxxx`). For fetching reply chains. |
| `author_flair_text` | string | Filter by commenter's flair. |
| `distinguished` | string | `"moderator"` etc. |
| `after` | date | Same formats as posts. |
| `before` | date | Same formats as posts. |
| `sort` | enum | `asc` / `desc`. |
| `sort_type` | enum | `default` / `created_utc`. |
| `limit` | int | 1–100. |
| `fields` | string | Comma-separated. |

**Key note:** Like posts, comments have **no score-based sorting**. The existing `fetch.py` works around this by fetching 100 and sorting client-side — this is correct and should continue.

### 3. `GET /api/posts/ids`

Batch lookup posts by ID.

| Parameter | Type | Notes |
|---|---|---|
| `ids` | string | Comma-separated post IDs. Works with or without `t3_` prefix. |
| `fields` | string | Comma-separated field filter. |

Returns full post objects. Tested with 3 IDs successfully.

### 4. `GET /api/comments/ids`

Batch lookup comments by ID.

| Parameter | Type | Notes |
|---|---|---|
| `ids` | string | Comma-separated comment IDs. |
| `fields` | string | Comma-separated field filter. |

### 5. `GET /api/subreddits/search`

Look up subreddit metadata.

| Parameter | Type | Notes |
|---|---|---|
| `subreddit` | string | Exact subreddit name. |
| `after` | date | Time filter. |
| `before` | date | Time filter. |
| `sort` | enum | `asc` / `desc`. |
| `sort_type` | enum | `default` / `created_utc`. |
| `limit` | int | 1–100. |
| `fields` | string | Comma-separated. |

Returns **101 fields** per subreddit including: `display_name`, `subscribers`, `public_description`, `title`, `created_utc`, `over18`, `active_user_count`, banner/icon URLs, rules, etc.

### 6. `GET /api/users/search`

Look up user metadata.

| Parameter | Type | Notes |
|---|---|---|
| `author` | string | Exact username. |
| `sort` | enum | `asc` / `desc`. |
| `sort_type` | enum | `default` / `created_utc`. |
| `limit` | int | Range unknown — tested with small values. |

Returns `_meta` with rich stats:
```json
{
  "_meta": {
    "earliest_comment_at": 1467077237,
    "earliest_post_at": 1467075003,
    "last_comment_at": 1742837190,
    "last_post_at": 1753065845,
    "num_comments": 4761,
    "num_posts": 116,
    "post_karma": 7833,
    "comment_karma": 27029,
    "total_karma": 34862
  },
  "author": "m3umax",
  "id": "z2mvk"
}
```

---

## Pagination

No offset/cursor. Pagination is done manually via `before`/`after`:

```
Page 1: /api/posts/search?subreddit=X&limit=25&sort=desc
Page 2: /api/posts/search?subreddit=X&limit=25&sort=desc&before={last_created_utc_from_page_1}
```

Zero overlap confirmed in testing. The `created_utc` of the last result becomes the `before` for the next page.

---

## Date Format Support

All `after`/`before` parameters accept:
- Unix epoch: `1700000000`
- ISO date: `2024-01-01`
- ISO datetime: `2024-01-01T00:00:00Z`
- Relative: `1h`, `6h`, `12h`, `1d`, `3d`, `7d`, `30d`, `1m`, `1y`
- **NOT supported:** `1w` (use `7d` instead)

---

## What We Currently Use vs What's Available

| Capability | Currently used? | Notes |
|---|---|---|
| Browse by subreddit | ✅ | `browse` command |
| Keyword search in sub | ✅ | `search` command |
| Fetch post by ID | ✅ | `post` command |
| Fetch comments by post | ✅ | `comments` command |
| User post/comment history | ✅ | `user` command |
| **Flair filtering** | ❌ NEW | `link_flair_text` param — exact match |
| **Author flair filtering** | ❌ NEW | `author_flair_text` — find official/verified posts |
| **Title-only search** | ❌ NEW | `title` param — more precise than `query` |
| **Body-only search** | ❌ NEW | `selftext` param for posts, `body` for comments |
| **Time range filtering** | ❌ NEW | `after`/`before` with relative or absolute dates |
| **Pagination (page 2+)** | ❌ NEW | `before=last_timestamp` for next page |
| **Subreddit info lookup** | ❌ NEW | Subscriber count, description, metadata |
| **User profile lookup** | ❌ NEW | Karma, post/comment counts, activity dates |
| **Batch ID lookup** | ❌ NEW | Multiple IDs in one call |
| **NSFW / spoiler filters** | ❌ NEW | `over_18`, `spoiler` booleans |
| **Comment body search** | ❌ NEW | `body` param on comments endpoint |
| **Combined filters** | ❌ NEW | All params stack (flair + time + author etc.) |
| Cross-reddit full-text search | ❌ N/A | API doesn't support — requires subreddit or author |
| Sort by score | ❌ N/A | API doesn't support — client-side only |
| Sort by num_comments | ❌ N/A | API doesn't support |

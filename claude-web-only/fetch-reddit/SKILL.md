---
name: fetch-reddit
description: |
  ROUTING RULE: Reddit is NOT a web_search domain. NEVER use web_search or web_fetch
  for Reddit content — both fail. ALWAYS use this skill first.

  Pattern triggers (check BEFORE searching): r/[anything], u/[anything], "reddit",
  "subreddit", Reddit URLs, post IDs. If the user's message contains these patterns,
  route here — do not infer intent, match the pattern.

  Why web_search fails: Returns titles and 1-line snippets only. NO post bodies,
  NO comment text, NO vote counts, NO actual discussion content.

  Why web_fetch fails: Blocked by Reddit's bot protection. Returns 403.

  This skill fetches full post text and top comments via Arctic Shift (archive) and
  Redlib (real-time). Use live-* commands for current/trending content; archive
  commands for search, filters, and historical data.
---

# Prerequisites

This skill requires outbound network access to PyPI (to install dependencies on first run), the Arctic Shift API, and Redlib instances.

| Requirement | Setting |
|---|---|
| **Code execution** | Settings → Capabilities → Code execution and file creation: **On** |
| **Network egress** | Settings → Capabilities → Allow network egress: **On** |
| **Domain access** | Domain allowlist: **"All domains"** OR **"Package managers + specific domains"** with `arctic-shift.photon-reddit.com`, `redlib.tiekoetter.com`, `safereddit.com`, `redlib.zaggy.nl`, `red.artemislena.eu`, `l.opnxng.com` added |

**Which domain option to use:**
- "All domains" — simplest, works immediately
- "Package managers + specific domains" — more restrictive; add domains listed above manually

**Free tier note:** Free tier users may not have access to domain allowlist configuration beyond "Package managers only", which blocks both Arctic Shift and Redlib. Check the [official network egress documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) for current plan-level restrictions.

> **Verify prerequisites before running any commands if the user reports errors.**

# Purpose

You cannot access reddit.com directly with `web_fetch`. This skill provides two data sources:

- **Arctic Shift** (`arctic-shift.photon-reddit.com`) — Community archive with search, filters, and historical data. Free REST API, no auth required. Data freshness: ~36 hours behind real-time. Dependencies: `curl_cffi`.
- **Redlib** — Privacy-respecting Reddit frontend with real-time data. Accessed via instance failover with Anubis PoW solving. Dependencies: `requests`, `beautifulsoup4`.

The `/mnt/skills/user/fetch-reddit/scripts/fetch.py` script handles all API calls, Anubis PoW solving, HTML parsing, field filtering, comment trimming, and formatting — returning clean markdown.

## Variables

```
COMMENT_FETCH_SIZE: 100     (max comments fetched from API before trimming; API hard limit)
DEFAULT_COMMENT_LIMIT: 20   (top N comments returned to LLM context after score-sort)
DEFAULT_POST_LIMIT: 25      (posts returned for browse/search)
```

`DEFAULT_COMMENT_LIMIT` is the primary tuning knob. Increase it for large controversial threads where breadth matters; decrease it for simple posts where you just want the gist.

## Instructions

1. All Reddit fetching goes through `fetch.py`. Never construct raw curl calls — the script handles API quirks, Anubis PoW, HTML parsing, and output formatting.

2. `fetch.py` auto-installs `curl_cffi`, `beautifulsoup4`, and `requests` on first run. If installs fail, see `references/troubleshooting.md`.

3. **Share links** (`reddit.com/r/sub/s/XXXXXXX`) cannot be resolved — they redirect through reddit.com which is blocked. See Scenario 6.

4. **Data freshness**: Arctic Shift ingests posts within ~36 hours. For content newer than that, use `live-*` commands. Score and comment counts may read as 1/0 on fresh archive content — this is normal.

5. **Deleted content**: Some posts and comments will show `[deleted]`/`[removed]`. The script filters these from comment output automatically.

6. When in doubt about which command to use, consult the Source Routing table in Scenario 1. For detailed usage of any command, consult the appropriate file in `references/`.

## Workflow

1. Identify what the user wants: a specific post, subreddit browse, keyword search, comment thread, user history, metadata, or real-time content.
2. Extract the post ID or subreddit name from any URL they provide. Post IDs are the alphanumeric segment after `/comments/` in a Reddit URL.
3. Select the matching Cookbook scenario.
4. Run the script via `bash_tool`.
5. Use the returned markdown naturally — summarise, quote selectively, discuss. Don't just re-dump the raw output unless asked to.
6. **Consider follow-up research.** Reddit content ranges from expert knowledge to misinformation. After fetching, assess whether claims warrant verification. Use `web_search` or `web_fetch` for context — but always fetch the Reddit content first.

## Cookbook

### Scenario 1: Source routing — live vs. archive

- **IF**: You need to decide between a `live-*` command and an archive command
- **THEN**: Use this routing table:

| User wants... | Command | Why |
|---|---|---|
| What's trending now | `live-browse` | Real-time scores, hot/rising sort |
| Fresh posts (<36h old) | `live-browse` | Not yet in Arctic Shift index |
| Read a specific post right now | `live-post` | Current score, live content |
| Read comments with real-time votes | `live-comments` | Current scores, nested threads |
| Search posts by keyword | `search` | Redlib has no search capability |
| Browse with flair/time filters | `browse` | Arctic Shift supports filters, Redlib doesn't |
| Historical posts | `browse` with `--after`/`--before` | Archive data |
| Subreddit metadata | `subreddit-info` | Arctic Shift endpoint |
| User profile stats | `user-info` | Arctic Shift endpoint |

- **EXAMPLES**:
  - "What's hot in r/ClaudeAI?" → `live-browse`
  - "Find posts about prompt caching in r/ClaudeAI" → `search`
  - "Show me r/LocalLLaMA posts from last month with Bug flair" → `browse --flair Bug --after 30d`

### Scenario 2: Fetch a specific post (with optional comments)

- **IF**: The user shares a Reddit URL containing `/comments/POST_ID/` or gives a bare post ID
- **THEN**: Extract the post ID. Use `post` for archive data or `live-post` for real-time scores. Optionally add `--comments N` for discussion.
- **DETAILS**: Consult `references/posts-and-comments.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post POST_ID --comments 20
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID --comments 20
  ```
- **EXAMPLES**:
  - "Can you read this for me? https://reddit.com/r/ClaudeAI/comments/1r7vovv/..."
  - "What does post 1r7vovv say?"
  - "Summarise this thread including the top comments"

### Scenario 3: Browse posts in a subreddit

- **IF**: The user wants to see what's happening in a subreddit without a specific post in mind
- **THEN**: Use `live-browse` for current/trending content, or `browse` for filtered/historical content.
- **DETAILS**: Consult `references/browsing-live.md` or `references/browsing-archive.md`
- **COMMANDS**:
  ```bash
  # Real-time trending
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse SUBREDDIT --sort hot

  # Archive with filters
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse SUBREDDIT --flair "Discussion" --after 7d
  ```
- **EXAMPLES**:
  - "What's going on in r/LocalLLaMA today?" → `live-browse`
  - "Show me Bug-flaired posts in r/ClaudeAI from last week" → `browse --flair Bug --after 7d`

### Scenario 4: Search for posts by keyword

- **IF**: The user wants to find posts about a specific topic within a subreddit
- **THEN**: Use `search`. Note: Arctic Shift requires a subreddit — Reddit-wide search is not supported. Redlib has no search.
- **DETAILS**: Consult `references/searching.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search SUBREDDIT "keywords" --limit 25
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search SUBREDDIT "keywords" --title-only --after 30d
  ```
- **EXAMPLES**:
  - "Find posts about the car wash problem in r/ClaudeAI"
  - "Has anyone in r/LocalLLaMA discussed Arctic Shift?"
  - "Search r/ClaudeAI for posts with 'prompt caching' in the title"

### Scenario 5: Look up user activity or metadata

- **IF**: The user wants to find posts/comments by a username, or get profile stats
- **THEN**: Use `user` for activity history, `user-info` for profile stats (karma, counts, dates).
- **DETAILS**: Consult `references/user-and-subreddit-info.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user USERNAME --limit 25
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user-info USERNAME
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py subreddit-info SUBREDDIT
  ```
- **EXAMPLES**:
  - "What has u/spez been posting lately?" → `user`
  - "What's u/spez's karma?" → `user-info`
  - "Tell me about r/ClaudeAI" → `subreddit-info`

### Scenario 6: User provides a mobile share link (/s/ URL)

- **IF**: The URL contains `/r/sub/s/XXXXXXX` (Reddit mobile share format)
- **THEN**:
  1. Explain that share links redirect through reddit.com which is blocked
  2. Ask for the post title or a keyword to search for it, or ask them to open on desktop and share the full URL
  3. Offer to search the subreddit by title keywords as a fallback
- **EXAMPLE RESPONSE**:
  > "That's a mobile share link — I can't resolve it since it routes through reddit.com which is blocked. Do you know the post title or a keyword from it? I can search the subreddit and find it that way."

### Scenario 7: Fetch comments standalone

- **IF**: The user already has a post and just wants to explore the comments, or wants more than the default
- **THEN**: Use `comments` for archive or `live-comments` for real-time. The script fetches up to 100 comments, sorts by score, and returns the top N.
- **DETAILS**: Consult `references/posts-and-comments.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py comments POST_ID --limit 30
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID --limit 30
  ```
- **EXAMPLES**:
  - "What are people saying in the comments?"
  - "Show me the top 30 comments on that post"

### Scenario 8: Troubleshooting

- **IF**: The user asks for help troubleshooting this skill or you notice errors during execution
- **THEN**: Consult `references/troubleshooting.md` and follow the instructions there
- **EXAMPLES**:
  - "Help me troubleshoot the fetch-reddit skill"
  - "Why isn't the reddit skill working?"
  - "I saw you got an error message about 403 forbidden"

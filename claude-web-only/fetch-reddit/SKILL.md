---
name: fetch-reddit
description: Fetch Reddit posts and comments. Your default `web_fetch` tool is blocked by Reddit. This skill is the only way to access Reddit content. Use when the user shares a Reddit URL or post ID, asks what's happening in a subreddit, wants to find Reddit posts from a specific user, or wants to find and discuss Reddit content that you cannot access directly due to bot blocking.
version: 1.0.0
---

# Purpose

You cannot access reddit.com directly with `web_fetch`. So this skill routes all Reddit access through the **Arctic Shift API** (`arctic-shift.photon-reddit.com`), a free community archive that continuously ingests Reddit content and exposes it via a clean REST API requiring no authentication.

The `/mnt/skills/user/fetch-reddit/scripts/fetch.py` script handles all API calls, field filtering, JSON parsing, comment trimming, and formatting — returning clean markdown to you.

## Variables

```
COMMENT_FETCH_SIZE: 100     (max comments fetched from API before trimming; API hard limit)
DEFAULT_COMMENT_LIMIT: 20   (top N comments returned to LLM context after score-sort)
DEFAULT_POST_LIMIT: 25      (posts returned for browse/search)
```

`DEFAULT_COMMENT_LIMIT` is the primary tuning knob. Increase it for large controversial threads where breadth matters; decrease it for simple posts where you just want the gist.

## Instructions

1. All Reddit fetching goes through `fetch.py`. Never construct raw curl calls to Arctic Shift — the script handles field validation, API quirks, and output formatting that would otherwise require re-learning each session.

2. `fetch.py` auto-installs `curl_cffi` if not present. No setup required.

3. **Share links** (`reddit.com/r/sub/s/XXXXXXX`) cannot be resolved — they redirect through reddit.com which is blocked. See Scenario 5.

4. **Data freshness**: Arctic Shift ingests posts within ~36 hours. Score and comment counts may read as 1/0 on very fresh content — this is normal, not an error.

5. **Deleted content**: Some posts and comments will show `[deleted]`/`[removed]`. The script filters these from comment output automatically.

## Workflow

1. Identify what the user wants: a specific post, subreddit browse, keyword search, comment thread, or user history.
2. Extract the post ID or subreddit name from any URL they provide. Post IDs are the alphanumeric segment after `/comments/` in a Reddit URL.
3. Select the matching Cookbook scenario.
4. Run the script via `bash_tool`.
5. Use the returned markdown naturally — summarise, quote selectively, discuss. Don't just re-dump the raw output unless asked to.

## Cookbook

### Scenario 1: Fetch a specific post (with optional comments)

- **IF**: The user shares a Reddit URL containing `/comments/POST_ID/` or gives a bare post ID
- **THEN**:
  1. Extract the post ID from the URL
  2. Run `fetch.py post` — optionally with `--comments N` if they want discussion too
- **COMMANDS**:
  ```bash
  # Post only
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post POST_ID

  # Post + top 20 comments (default)
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post POST_ID --comments 20

  # Post + more comments for a busy thread
  python3 scripts/fetch.py post POST_ID --comments 50
  ```
- **EXAMPLES**:
  - "Can you read this for me? https://reddit.com/r/ClaudeAI/comments/1r7vovv/..."
  - "What does post 1r7vovv say?"
  - "Summarise this thread including the top comments"

### Scenario 2: Browse recent posts in a subreddit

- **IF**: The user wants to see what's happening in a subreddit without a specific post in mind
- **THEN**: Run `fetch.py browse` and return a digest, offering to fetch full content for anything interesting
- **COMMAND**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py browse SUBREDDIT [--limit 25]
  ```
- **EXAMPLES**:
  - "What's going on in r/LocalLLaMA today?"
  - "Show me the latest posts from r/claudexplorers"
  - "What are people talking about in r/ClaudeAI?"

### Scenario 3: Search for posts by keyword within a subreddit

- **IF**: The user wants to find posts about a specific topic
- **THEN**: Run `fetch.py search`. Note: Arctic Shift requires a subreddit for keyword search — Reddit-wide full-text search is not supported.
- **COMMAND**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py search SUBREDDIT "keywords" [--limit 25]
  ```
- **EXAMPLES**:
  - "Find posts about the car wash problem in r/ClaudeAI"
  - "Has anyone in r/LocalLLaMA discussed Arctic Shift?"
  - "Search r/claudexplorers for posts about the long conversation reminder"

### Scenario 4: Fetch comments for a post (standalone)

- **IF**: The user already has a post and just wants to explore the comments, or wants more than the default
- **THEN**:
  1. The script fetches 100 comments from Arctic Shift (API max)
  2. Sorts by score descending
  3. Returns the top N to LLM context
- **COMMAND**:
  ```bash
  # Default top 20
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py comments POST_ID

  # More for a large thread
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py comments POST_ID --limit 50
  ```
- **EXAMPLES**:
  - "What are people saying in the comments?"
  - "Show me the top 30 comments on that post"
  - "What's the most upvoted response?"

### Scenario 5: User provides a mobile share link (/s/ URL)

- **IF**: The URL contains `/r/sub/s/XXXXXXX` (Reddit mobile share format)
- **THEN**:
  1. Explain that share links redirect through reddit.com which is blocked
  2. Ask for the post title or a keyword to search for it, or ask them to open on desktop and share the full URL
  3. Offer to search the subreddit by title keywords as a fallback
- **EXAMPLE RESPONSE**:
  > "That's a mobile share link — I can't resolve it since it routes through reddit.com which is blocked. Do you know the post title or a keyword from it? I can search the subreddit and find it that way."

### Scenario 6: Look up a user's recent activity

- **IF**: The user wants to find posts or comments by a specific Reddit username
- **THEN**: Run `fetch.py user` — returns recent posts and comments with body previews
- **COMMAND**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py user USERNAME [--limit 25]
  ```
- **EXAMPLES**:
  - "What has u/spez been posting lately?"
  - "Show me my recent Reddit activity" (ask for their username first if not provided)
  - "Find posts by u/someuser"

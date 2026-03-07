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

  This skill fetches full post text and top comments via Redlib, a privacy-respecting
  Reddit frontend. Use it whenever the user shares a Reddit link, asks what's happening
  in a subreddit, or wants to read comments on a post.
---

# Prerequisites

This skill requires outbound network access to PyPI (to install dependencies on first run) and Redlib instances.

| Requirement | Setting |
|---|---|
| **Code execution** | Settings → Capabilities → Code execution and file creation: **On** |
| **Network egress** | Settings → Capabilities → Allow network egress: **On** |
| **Domain access** | Domain allowlist: **"All domains"** OR **"Package managers + specific domains"** with `raw.githubusercontent.com` added |

On the **first command** each chat session, the script fetches the current Redlib instance list from `raw.githubusercontent.com` (~1s, one-time). If unreachable, it falls back to a bundled list automatically.

**Free tier note:** Free tier users may not have access to domain allowlist configuration beyond "Package managers only". Check the [official network egress documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) for current plan-level restrictions.

> **Verify prerequisites before running any commands if the user reports errors.**

# Purpose

You cannot access reddit.com directly with `web_fetch`. This skill uses **Redlib** — a privacy-respecting Reddit frontend — to fetch live post content and browse subreddits in real time.

The `/mnt/skills/user/fetch-reddit/scripts/fetch.py` script handles Anubis PoW solving, instance failover, HTML parsing, comment trimming, and formatting — returning clean markdown.

## Variables

```
DEFAULT_COMMENT_LIMIT: 20   (top N comments returned to LLM context after score-sort)
```

Increase for large controversial threads where breadth matters; decrease for simple posts where you just want the gist.

## Instructions

1. All Reddit fetching goes through `fetch.py`. Never construct raw curl calls.

2. `fetch.py` auto-installs `beautifulsoup4` and `requests` on first run. If installs fail, see `references/troubleshooting.md`.

3. **Share links** (`reddit.com/r/sub/s/XXXXXXX`) are supported via `live-share`. Extract the subreddit and token from the URL and use Scenario 4.

4. When in doubt about which command to use, the choice is simple: use `live-post` for a specific post, `live-browse` to see what's happening in a subreddit, `live-comments` for a comment thread.

## Workflow

1. Identify what the user wants: a specific post, subreddit browse, or comment thread.
2. Extract the post ID or subreddit name from any URL they provide. Post IDs are the alphanumeric segment after `/comments/` in a Reddit URL.
3. Select the matching Cookbook scenario.
4. Run the script via `bash_tool`.
5. Use the returned markdown naturally — summarise, quote selectively, discuss. Don't just re-dump the raw output unless asked to.
6. **Consider follow-up research.** Reddit content ranges from expert knowledge to misinformation. After fetching, assess whether claims warrant verification. Use `web_search` or `web_fetch` for context — but always fetch the Reddit content first.

## Cookbook

### Scenario 1: Fetch a specific post (with optional comments)

- **IF**: The user shares a Reddit URL containing `/comments/POST_ID/` or gives a bare post ID
- **THEN**: Extract the post ID and use `live-post`. Add `--comments N` to include discussion.
- **DETAILS**: Consult `references/posts-and-comments.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID --comments 20
  ```
- **EXAMPLES**:
  - "Can you read this for me? https://reddit.com/r/ClaudeAI/comments/1r7vovv/..."
  - "What does post 1r7vovv say?"
  - "Summarise this thread including the top comments"

### Scenario 2: Browse posts in a subreddit

- **IF**: The user wants to see what's happening in a subreddit without a specific post in mind
- **THEN**: Use `live-browse` for current/trending content.
- **DETAILS**: Consult `references/browsing-live.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse SUBREDDIT
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-browse SUBREDDIT --sort new
  ```
- **EXAMPLES**:
  - "What's going on in r/LocalLLaMA today?"
  - "Show me the hot posts in r/ClaudeAI"
  - "What's new in r/programming?"

### Scenario 3: Fetch comments standalone

- **IF**: The user already has a post and just wants to explore the comments, or wants more than the default
- **THEN**: Use `live-comments`. The script fetches all visible comments, sorts by score, and returns the top N.
- **DETAILS**: Consult `references/posts-and-comments.md`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID --limit 30
  ```
- **EXAMPLES**:
  - "What are people saying in the comments?"
  - "Show me the top 30 comments on that post"

### Scenario 4: User provides a mobile share link (/s/ URL)

- **IF**: The URL contains `/r/sub/s/XXXXXXX` (Reddit mobile share format — works for both post and comment share links)
- **THEN**: Extract the subreddit name and share token from the URL, then use `live-share`
- **COMMANDS**:
  ```bash
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-share SUBREDDIT SHARE_TOKEN
  python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-share SUBREDDIT SHARE_TOKEN --comments 20
  ```
- **EXAMPLES**:
  - URL `https://www.reddit.com/r/claudexplorers/s/LBwofUPUb2` → subreddit=`claudexplorers`, token=`LBwofUPUb2`
  - "Can you read this? https://reddit.com/r/AskReddit/s/ABC123XYZ" → `live-share AskReddit ABC123XYZ`
- **NOTE — comment share links**: If the share link points to a specific comment, Redlib will load only that comment's thread context rather than the full discussion. The post header and ID will still be shown. To read the full discussion, follow up with `live-post POST_ID --comments N` using the ID from the output.

### Scenario 5: Troubleshooting

- **IF**: The user asks for help troubleshooting this skill or you notice errors during execution
- **THEN**: Consult `references/troubleshooting.md` and follow the instructions there
- **EXAMPLES**:
  - "Help me troubleshoot the fetch-reddit skill"
  - "Why isn't the reddit skill working?"
  - "I saw you got an error message about 403 forbidden"

---
name: fetch-reddit
description: |
  ROUTING RULE: Reddit is NOT a web_search domain. NEVER use web_search or web_fetch 
  for Reddit content — both fail. ALWAYS use this skill first.
  
  Pattern triggers (check BEFORE searching): r/[anything], u/[anything], "reddit", 
  "subreddit", Reddit URLs, post IDs. If the user's message contains these patterns, 
  route here — do not infer intent, match the pattern.
  
  Why web_search fails: Returns titles and 1-line snippets only. NO post bodies, 
  NO comment text, NO vote counts, NO actual discussion content. Useless for 
  understanding what people are saying.
  
  Why web_fetch fails: Blocked by Reddit's bot protection. Returns 403.
  
  This skill fetches full post text and top comments via Arctic Shift API.
---

# Prerequisites

This skill requires outbound network access to PyPI (to install `curl_cffi` on first run) and the Arctic Shift API. PyPI is covered by default package manager access; Arctic Shift requires an explicit domain allowance.

| Requirement | Setting |
|---|---|
| **Code execution** | Settings → Capabilities → Code execution and file creation: **On** |
| **Network egress** | Settings → Capabilities → Allow network egress: **On** |
| **Domain access** | Domain allowlist: **"All domains"** OR **"Package managers + specific domains"** with `arctic-shift.photon-reddit.com` added |

**Which domain option to use:**
- "All domains" — simplest, works immediately
- "Package managers + specific domains" — more restrictive; add `arctic-shift.photon-reddit.com` manually

**Free tier note:** Free tier users may not have access to domain allowlist configuration beyond "Package managers only", which blocks Arctic Shift. Check the [official network egress documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) for current plan-level restrictions — these settings may change.

> **Verify prerequisites before running any commands if the user reports errors.**

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

2. `fetch.py` auto-installs `curl_cffi` on first run. If the install fails, see the Troubleshooting section — the most common cause is network egress not set to "All domains".

3. **Share links** (`reddit.com/r/sub/s/XXXXXXX`) cannot be resolved — they redirect through reddit.com which is blocked. See Scenario 5.

4. **Data freshness**: Arctic Shift ingests posts within ~36 hours. Score and comment counts may read as 1/0 on very fresh content — this is normal, not an error.

5. **Deleted content**: Some posts and comments will show `[deleted]`/`[removed]`. The script filters these from comment output automatically.

## Workflow

1. Identify what the user wants: a specific post, subreddit browse, keyword search, comment thread, or user history.
2. Extract the post ID or subreddit name from any URL they provide. Post IDs are the alphanumeric segment after `/comments/` in a Reddit URL.
3. Select the matching Cookbook scenario.
4. Run the script via `bash_tool`.
5. Use the returned markdown naturally — summarise, quote selectively, discuss. Don't just re-dump the raw output unless asked to.
6. **Consider follow-up research.** Reddit content ranges from expert knowledge to misinformation. After fetching, assess whether claims, products, events, or people mentioned warrant verification before presenting conclusions. Use `web_search` or `web_fetch` for context where reliability matters — but always fetch the Reddit content first; never substitute `web_search` for this skill.

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

### Scenario 7: Troubleshooting

- **IF**: The user asks for help troubleshooting this skill or you notice issues with executing the skill
- **THEN**: Consult the 'Troubleshooting' section and follow the instructions there

- **EXAMPLES**:
  - "Help me troubleshoot the fetch-reddit skill"
  - "Why isn't the reddit skill working?"
  - "I saw you got an error message about 403 forbidden, what does that mean?"

## Troubleshooting

Use these to diagnose failures and give the user a specific, actionable response — not a generic "something went wrong".

### `curl_cffi` install fails with 403 or connection error

**Action:** PyPI is included in the default "Package managers only" allowlist, so a failure here means network egress is **completely disabled** — not just domain-restricted. Ask the user to confirm "Allow network egress" is toggled On.

**Suggested message to the user:**
> "The `curl_cffi` install failed — since PyPI is accessible by default when network egress is on, this usually means the egress toggle is off entirely. Please check Settings → Capabilities and confirm 'Allow network egress' is turned on. Start a new chat after enabling it."

**Root cause:** Network egress toggle is off. Distinct from the Arctic Shift domain error below.

### Arctic Shift API returns a connection error

**Action:** Confirm `fetch.py` is being used (not `web_fetch` — which will always fail Reddit's bot protection). If the script itself is failing to reach the API, the domain allowlist is likely set to "Package managers only", which excludes `arctic-shift.photon-reddit.com`.

**Suggested message to the user:**
> "I can reach PyPI but not the Arctic Shift API — this means network egress is on but the domain allowlist is set to 'Package managers only', which blocks external APIs. Please go to Settings → Capabilities → Allow network egress → Domain allowlist and either select 'All domains', or choose 'Package managers + specific domains' and add `arctic-shift.photon-reddit.com`. Start a new chat once changed."

**Root cause:** Domain allowlist excludes Arctic Shift. See the [official documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) for current options — plan-level restrictions on allowlist tiers may vary.

### User is on the Free tier

Free tier users may only have access to "Package managers only" and cannot add external domains. The official documentation has the authoritative breakdown of what each plan supports.

**Tell the user:**
> "This skill needs access to an external API (`arctic-shift.photon-reddit.com`) which requires your domain allowlist to be set beyond 'Package managers only'. Free tier may not support this — check Settings → Capabilities to see what options are available to you, or refer to the [network egress documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)."

Do not attempt to run the script until confirmed.

### Script runs but returns no posts / empty results

- Very new posts (< 36 hours) may not yet be indexed by Arctic Shift — this is normal
- Score and comment counts may show as 1/0 on fresh content — also normal
- If a subreddit is private or banned, the API will return empty results with no error

# fetch-reddit v2 Design: Redlib + Expanded Arctic Shift

**Date:** 2026-02-22
**Skill:** `claude-web-only/fetch-reddit`
**Architecture:** Single script expansion (fetch.py)

---

## Goals

1. Add real-time Reddit content via Redlib (with Anubis PoW solving)
2. Expose all unused Arctic Shift API capabilities
3. Restructure SKILL.md with progressive disclosure via `references/`

## Architecture Decision

Single `fetch.py` script containing both Redlib and Arctic Shift logic. The LLM selects the appropriate command based on SKILL.md routing guidance. No `--source` flag; the command name implies the data source (`live-*` = Redlib, everything else = Arctic Shift).

---

## Command Structure

### Enhanced Existing Commands (Arctic Shift)

| Command | New Flags |
|---|---|
| `browse SUBREDDIT` | `--flair`, `--after`, `--before`, `--nsfw` |
| `search SUBREDDIT "query"` | `--title-only`, `--body-only`, `--flair`, `--after`, `--before`, `--author` |
| `user USERNAME` | `--after`, `--before` |
| `post POST_ID` | _(unchanged)_ |
| `comments POST_ID` | _(unchanged)_ |

### New Commands

| Command | Source | Purpose |
|---|---|---|
| `live-browse SUBREDDIT` | Redlib | Real-time post listings with current scores |
| `live-post POST_ID` | Redlib | Real-time post content with current score |
| `live-comments POST_ID` | Redlib | Real-time nested comment thread |
| `subreddit-info SUBREDDIT` | Arctic Shift | Subscriber count, description, metadata |
| `user-info USERNAME` | Arctic Shift | Karma, post/comment counts, activity dates |

### Pagination

Commands that return lists output a footer: `<!-- next_page: before=TIMESTAMP -->`. The LLM passes this timestamp via `--before` for the next page.

---

## Redlib Integration

### Anubis PoW Solver

Embedded in `fetch.py`. Protocol:

1. GET request to Redlib instance
2. Detect `<script id="anubis_challenge">` in response
3. Parse challenge JSON: `randomData`, `difficulty`, `challenge.id`
4. Brute-force SHA-256: find nonce N where `SHA256(randomData + N)` has required leading zero bits
5. Submit to `/.within.website/x/cmd/anubis/api/pass-challenge` with params: `id`, `response`, `nonce`, `redir`, `elapsedTime`
6. Receive JWT auth cookie (~7 day lifetime)
7. Re-fetch original URL with cookie

At difficulty 2 (current), solving takes <1ms (<100 nonces).

### Instance Failover

Ranked list starting with `redlib.tiekoetter.com`. On failure (TLS error, 502, Cloudflare), try next instance. List is hardcoded.

### HTML Parsing

BeautifulSoup4 with structured extraction:
- CSS selectors targeting Redlib's semantic HTML classes
- Fallback patterns for version variations
- Clear error messages on format mismatch

### Dependencies

- `requests` (stdlib-adjacent, for Redlib)
- `beautifulsoup4` (new, for HTML parsing)
- `curl_cffi` (existing, for Arctic Shift)
- `hashlib` (stdlib, for SHA-256 PoW)

---

## Expanded Arctic Shift Features

### New Parameters on Existing Endpoints

**`/api/posts/search` (browse, search):**
- `link_flair_text` — exact flair match
- `after` / `before` — time range (relative: `7d`, `30d`; absolute: ISO dates; unix epochs)
- `title` — title-only search
- `selftext` — body-only search
- `author` — filter by post author
- `over_18` — NSFW filter

**`/api/comments/search` (comments):**
- `body` — search within comment bodies (requires subreddit or author)

### New Endpoints

**`/api/subreddits/search`** — returns subscriber count, description, creation date, NSFW status, active users.

**`/api/users/search`** — returns karma breakdown, post/comment counts, first/last activity dates.

---

## File Structure

```
claude-web-only/fetch-reddit/
├── SKILL.md                          # Lean: command table + routing rules + prerequisites
├── scripts/
│   └── fetch.py                      # All logic (Arctic Shift + Redlib + Anubis solver)
└── references/
    ├── browsing-live.md              # live-browse, live-post, live-comments
    ├── browsing-archive.md           # browse with filters, pagination
    ├── searching.md                  # search with all filter combinations
    ├── posts-and-comments.md         # post, comments usage
    ├── user-and-subreddit-info.md    # user, user-info, subreddit-info
    └── troubleshooting.md            # Network, Anubis, empty results
```

### SKILL.md Content

Concise command reference table, routing guidance (when to use `live-*` vs archive commands), network prerequisites (add Redlib domains to allowlist), dependency list. No full cookbook — reference files handle that.

### References

Each file covers scenarios, example invocations, expected output format, and edge cases for its domain. The LLM consults the relevant reference based on the user's request.

---

## Source Selection Routing (for SKILL.md)

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

---

## Error Handling

- **Redlib instance down:** try next in list, surface error only after all fail
- **Anubis format change:** detect and report "Anubis challenge format may have changed"
- **HTML parse failure:** report which element couldn't be found, suggest trying Arctic Shift
- **Arctic Shift timeout:** existing behavior (report error)
- **Empty results:** distinguish between "no matches" and "subreddit not found"

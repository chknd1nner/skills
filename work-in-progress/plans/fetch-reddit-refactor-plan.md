# fetch-reddit Skill: Bug Report & Refactoring Plan

Authored for Claude Code execution. Address issues in order — later changes
depend on earlier ones.

---

## Context: What Was Discovered

During a live debugging session (`r/claudeai`, 2026-02-23), three distinct
problems were found in `fetch.py` and one gap in the skill documentation.
Two bugs were patched in-session (marked ✅); the rest are outstanding work.

---

## Bug 1 — Stale, Incomplete Redlib Instance List

### What happened

`REDLIB_INSTANCES` was a hand-picked list of 5 instances that did not
correspond to the official instance registry at
`https://github.com/redlib-org/redlib-instances`. Several of the listed
instances were dead (safereddit.com, redlib.zaggy.nl, red.artemislena.eu all
returned TLS errors or 503s). The one working instance (`redlib.freedit.eu`)
was not in the original list at all — it was found manually by the user.

### Current state of the file

The original `REDLIB_INSTANCES` in `fetch.py` contains these 5 entries — none
of which are in the official registry and most of which are dead:

```python
REDLIB_INSTANCES = [
    "https://redlib.tiekoetter.com",
    "https://safereddit.com",
    "https://redlib.zaggy.nl",
    "https://red.artemislena.eu",
    "https://l.opnxng.com",
]
```

This list predates the dynamic fetch feature and must be replaced as part of
the refactor. `redlib.freedit.eu` (confirmed working) is not present.

### Remaining work: Dynamic instance fetching

The list will go stale again. The fix is to fetch it fresh at the start of
each chat session, on the first `live-*` invocation.

**Implementation plan for `fetch.py`:**

1. Add a module-level sentinel: `_instances_fetched = False`

2. Add a function `fetch_redlib_instances()` that:
   - GETs `https://raw.githubusercontent.com/redlib-org/redlib-instances/main/instances.json`
     using `std_requests` (plain requests, not curl_cffi — no Anubis needed here)
   - Filters to entries where `"url"` is present and starts with `https://`
   - Returns the URL list, or `None` on any error (timeout, parse failure, etc.)

3. Add a function `get_redlib_instances()` that:
   - Checks `_instances_fetched`; if already done, returns current `REDLIB_INSTANCES`
   - Calls `fetch_redlib_instances()`
   - On success: prepends any entries from the hardcoded list that are **not**
     in the fetched list (preserves `redlib.freedit.eu` and any other
     manually-confirmed instances that aren't in the official registry), then
     appends the fetched list, deduplicating. Updates `REDLIB_INSTANCES` in place.
   - On failure: logs a warning to stderr, uses the hardcoded list as fallback
   - Sets `_instances_fetched = True` either way

   **Mutation approach:** Use `global _instances_fetched` (required — bool
   rebinding) and `REDLIB_INSTANCES[:] = merged_list` (list slice assignment —
   no `global` needed, idiomatic Python for in-place module-level list updates).
   There is no existing `global` usage in `fetch.py`; keep it minimal.

4. In `redlib_get()`, replace the direct iteration over `REDLIB_INSTANCES`
   with a call to `get_redlib_instances()` first.

**Timeout:** Use a short timeout (5s) on the instances fetch — it's a fast
GitHub raw request and we don't want it to slow down the first live command.

**Domain allowlist note:** `raw.githubusercontent.com` must be accessible.
This should be fine under "All domains" but needs a mention in SKILL.md and
troubleshooting.md.

---

## Bug 2 — Silent Failure Masking Real Redlib Errors

### What happened

`redlib_get()` checks for success with:
```python
if r.status_code == 200 and "anubis" not in r.text.lower()[:500]:
```

This passes two kinds of bad responses as if they were valid HTML:

**Case A — Reddit API backend failure:** After Anubis is solved and the auth
cookie is set, the re-fetch returns a Redlib error page with title
`"Backend temporarily unavailable. Retrying..."` and HTTP 200 (Redlib serves
its own error pages as 200). The check passes, `parse_redlib_posts` finds no
`div#posts`, returns `[]`, and `cmd_live_browse` prints:

```
No posts found in r/ClaudeAI (live). Redlib HTML may have changed or the subreddit may not exist.
```

This message is wrong on all three counts — posts exist, HTML hasn't changed,
and the subreddit exists. The actual error (Reddit blocking the Redlib
instance's API calls) is invisible.

**Case B — Redlib 404 error page:** Some instances return 404 for subreddits
they can't reach, which Redlib serves as status 200 with an error title. Same
silent failure path.

### Fix for `redlib_get()`

After getting a 200 response that passes the Anubis check, validate that
it actually looks like a Redlib page before returning it:

```python
# After existing Anubis check passes:
soup = BeautifulSoup(r.text, "html.parser")
title = soup.find("title")
title_text = title.get_text(strip=True) if title else ""

# Detect Redlib error pages
error_indicators = [
    "backend temporarily unavailable",
    "failed to parse page json",
]
if any(indicator in title_text.lower() for indicator in error_indicators):
    errors.append(f"{base}: Redlib error — {title_text}")
    continue
```

This moves the instance to the errors list and tries the next one, rather
than returning a bad response. The existing "All Redlib instances failed"
error path then surfaces with a meaningful per-instance reason.

**Why `"error:"` is excluded:** `redlib_get()` is called from three sites —
`cmd_live_browse` (path `/r/{sub}/…`) and both `cmd_live_post` /
`cmd_live_comments` (path `/comments/{post_id}`). For listing pages the
`<title>` is `r/{sub} - Redlib`, safe to match. For post/comments pages the
`<title>` is the **post title** (e.g. `"Error: API keeps returning 403 -
Redlib"`), so `"error:"` would false-positive on any normally-titled post and
cause the instance to be incorrectly skipped. The two retained indicators are
specific to Redlib's own error copy and won't appear in user-authored content.

Redlib 404s (subreddit-not-found) are handled adequately by the existing
parser fallback: `parse_redlib_posts()` returns `[]`, the hardened message
fires with the page title. Skipping to the next instance for a non-existent
subreddit would make no difference anyway — all instances return the same 404.

### Fix for `cmd_live_browse()` and other `cmd_live_*` functions

The `parse_redlib_posts` → empty list → "No posts found" message should also
be hardened as a secondary check:

```python
posts = parse_redlib_posts(soup)
if not posts:
    # At this point redlib_get() returned successfully, so the page loaded
    # but contained no posts. This is unexpected — log the page title.
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else "unknown"
    print(f"No posts found in r/{args.subreddit} (live). Page title was: '{title_text}'. "
          f"Try archive commands as a fallback.")
    return
```

---

## Bug 3 — Permalink Selector Grabs Flair Link Instead of Post Link

### What happened

In `parse_redlib_posts()`:
```python
title_link = title_el.select_one("a[href]")
```

In Redlib's HTML, `h2.post_title` contains two `<a>` elements: the flair
link (with class `post_flair`) comes **first**, followed by the actual post
title link. `select_one("a[href]")` grabbed the flair search URL every time.

Result: all `live-browse` output had permalinks like:
```
/r/ClaudeAI/search?q=flair_name%3A%22Humor%22&restrict_sr=on
```
instead of:
```
/r/ClaudeAI/comments/1rc27sc/i_built_an_app_to_monitor.../
```

### Fix required

In `parse_redlib_posts()`, change:

```python
title_link = title_el.select_one("a[href]")
```

to:

```python
title_link = title_el.select_one("a:not(.post_flair)[href]")
```

---

## SKILL.md Changes Required

### 1. Domain allowlist — add `raw.githubusercontent.com`

The dynamic instance fetch (Bug 1 fix) hits GitHub's raw content CDN.
Update the prerequisites table:

```
| **Domain access** | ... add `raw.githubusercontent.com` for dynamic instance list fetching |
```

Also update the "Package managers + specific domains" bullet to include it.

### 2. Scenario 1 (Source routing table) — add note on instance list refresh

Add a row or note:

> **On first `live-*` invocation per session**, the script fetches the
> current instance list from the official Redlib registry. This adds ~1s
> on first call only. If the fetch fails, the bundled fallback list is used.

### 3. Scenario 8 (Troubleshooting) — add pointer to new troubleshooting entries

Reference the two new troubleshooting cases being added (see below).

---

## `references/troubleshooting.md` Changes Required

### Add new section: "Redlib backend error (Reddit blocking the instance)"

```markdown
### Redlib returns content but posts are empty or page title is an error

**Cause:** The Redlib instance successfully loaded (Anubis solved, cookie set)
but Reddit's API rejected the instance's requests. Redlib serves its own error
page as HTTP 200, which looks like a valid response until the title is checked.
Common titles: "Backend temporarily unavailable. Retrying...", "Error: Failed
to parse page JSON data".

This is Reddit throttling or blocking specific Redlib instance IPs — not a
problem with the skill's code. The script will now automatically skip these
instances and try the next one.

**If all instances show this error:**
> "All Redlib instances are currently being blocked by Reddit's API. This
> happens periodically as Reddit tightens its crackdown on alternative
> frontends. Archive commands (`browse`, `post`, `search`, `comments`) still
> work via Arctic Shift for content older than ~36 hours."
```

### Add new section: "Instance list fetch failure"

```markdown
### Warning: Could not refresh Redlib instance list from GitHub

**Cause:** The request to `raw.githubusercontent.com` timed out or failed.
The script falls back to its bundled instance list automatically.

**If you see this warning repeatedly:**
> "The skill couldn't reach GitHub to refresh the Redlib instance list and
> is using a potentially stale fallback. Check that `raw.githubusercontent.com`
> is accessible under your domain allowlist settings."
```

---

## `references/browsing-live.md` Changes Required

### Update the Limitations section

Replace the current "Instance failover" bullet with:

```markdown
- **Instance failover:** At the start of each chat, the first `live-*`
  command fetches the current instance list from the official Redlib registry
  (`github.com/redlib-org/redlib-instances`). The script then tries instances
  in order until one returns valid content. If all fail — typically because
  Reddit is blocking that instance's API calls — it reports each failure
  reason explicitly. Fall back to archive commands in that case.
```

---

## Summary Checklist for Claude Code

- [ ] `fetch.py` — Add `_instances_fetched` sentinel and `fetch_redlib_instances()` / `get_redlib_instances()` functions
- [ ] `fetch.py` — Call `get_redlib_instances()` at the top of `redlib_get()` before iterating
- [ ] `fetch.py` — Add Redlib error page detection inside `redlib_get()` loop (title-based check)
- [ ] `fetch.py` — Harden empty-posts fallback message in `cmd_live_browse()`, `cmd_live_post()`, `cmd_live_comments()` to include page title
- [ ] `fetch.py` — Fix permalink selector in `parse_redlib_posts()`: change `a[href]` to `a:not(.post_flair)[href]`
- [ ] `SKILL.md` — Add `raw.githubusercontent.com` to domain allowlist prerequisites
- [ ] `SKILL.md` — Add instance refresh note to Scenario 1 routing table
- [ ] `references/troubleshooting.md` — Add Reddit-blocking-instance section
- [ ] `references/troubleshooting.md` — Add instance-list-fetch-failure section
- [ ] `references/browsing-live.md` — Update Instance failover bullet in Limitations

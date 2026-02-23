# fetch-reddit Bug Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three bugs in `fetch.py` (stale instance list, silent Redlib error pages, wrong permalink selector) and update the three affected reference docs.

**Architecture:** All changes are isolated to `claude-web-only/fetch-reddit/scripts/fetch.py` and the three markdown files under `references/`. Tasks are ordered by blast radius: smallest/most isolated first (Bug 3), then Bug 2 improvements to `redlib_get()`, then Bug 1 which adds new module-level state and two new functions.

**Tech Stack:** Python 3, `requests` (aliased `std_requests`), `curl_cffi` (aliased `requests`), `beautifulsoup4`. No test framework — verification is manual script invocation against a live subreddit.

---

## Context

Design doc: `work-in-progress/plans/fetch-reddit-refactor-plan.md` — read it before starting. It contains the exact code for each fix and the reasoning behind every decision. This plan is the step-by-step execution guide; the design doc is the reference.

Key file: `claude-web-only/fetch-reddit/scripts/fetch.py`

---

### Task 1: Fix permalink selector (Bug 3)

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py:199`

**Step 1: Read the current selector**

Open `fetch.py` and find `parse_redlib_posts()` around line 185. Confirm line 199 reads:
```python
title_link = title_el.select_one("a[href]")
```

**Step 2: Apply the fix**

Change line 199 from:
```python
title_link = title_el.select_one("a[href]")
```
to:
```python
title_link = title_el.select_one("a:not(.post_flair)[href]")
```

**Step 3: Verify manually**

Run live-browse against any active subreddit and confirm the permalinks look like post paths, not flair search URLs:
```bash
cd claude-web-only/fetch-reddit/scripts
python fetch.py live-browse ClaudeAI
```
Expected: Each post shows a permalink like `` `1rc27sc` — https://redlib.freedit.eu/r/ClaudeAI/comments/1rc27sc/...` ``

Bad (pre-fix): `` `1rc27sc` — https://redlib.freedit.eu/r/ClaudeAI/search?q=flair_name%3A%22...` ``

**Step 4: Commit**
```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "fix(fetch-reddit): fix permalink selector grabbing flair link instead of post link"
```

---

### Task 2: Add Redlib error page detection in redlib_get() (Bug 2, part A)

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py:160-182`

**Step 1: Read the current redlib_get() loop**

Lines 168-177. The success path is:
```python
if r.status_code == 200 and "anubis" not in r.text.lower()[:500]:
    return BeautifulSoup(r.text, "html.parser"), base
```

This passes Redlib error pages served as HTTP 200.

**Step 2: Apply the fix**

Replace the success branch inside `redlib_get()`. The full updated loop body (lines 169-177) becomes:

```python
    for base in REDLIB_INSTANCES:
        url = f"{base}{path}"
        try:
            r = solve_anubis(session, url)
            if r.status_code == 200 and "anubis" not in r.text.lower()[:500]:
                soup = BeautifulSoup(r.text, "html.parser")
                title = soup.find("title")
                title_text = title.get_text(strip=True) if title else ""
                error_indicators = [
                    "backend temporarily unavailable",
                    "failed to parse page json",
                ]
                if any(ind in title_text.lower() for ind in error_indicators):
                    errors.append(f"{base}: Redlib error — {title_text}")
                    continue
                return soup, base
            errors.append(f"{base}: got Anubis page despite solving")
        except Exception as e:
            errors.append(f"{base}: {e}")
```

Note: `"error:"` is intentionally absent from `error_indicators`. See the design doc for why — it false-positives on post detail pages where `<title>` contains the post title.

**Step 3: Verify — good instance still returns normally**

```bash
python fetch.py live-browse ClaudeAI
```
Expected: Normal post listing. The check should be transparent when Redlib serves a real page.

**Step 4: Commit**
```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "fix(fetch-reddit): detect Redlib error pages in redlib_get() to enable instance failover"
```

---

### Task 3: Harden empty-result messages to include page title (Bug 2, part B)

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py` — three functions

**Step 1: Update cmd_live_browse() fallback (lines 712-714)**

Current:
```python
    if not posts:
        print(f"No posts found in r/{args.subreddit} (live). Redlib HTML may have changed or the subreddit may not exist.")
        return
```

Replace with:
```python
    if not posts:
        page_title = soup.find("title")
        title_text = page_title.get_text(strip=True) if page_title else "unknown"
        print(f"No posts found in r/{args.subreddit} (live). Page title was: '{title_text}'. "
              f"Try archive commands as a fallback.")
        return
```

**Step 2: Update cmd_live_comments() fallback (lines 767-769)**

Current:
```python
    if not comments:
        print(f"No comments found for post {post_id} (live).")
        return
```

Replace with:
```python
    if not comments:
        page_title = soup.find("title")
        title_text = page_title.get_text(strip=True) if page_title else "unknown"
        print(f"No comments found for post {post_id} (live). Page title was: '{title_text}'. "
              f"Try archive commands as a fallback.")
        return
```

**Step 3: cmd_live_post() — no change needed**

`cmd_live_post()` uses `parse_redlib_post_detail()` which checks for `div.post` absence and returns `None`. The existing message at line 735 is adequate for that parser's failure mode. Leave it as is.

**Step 4: Verify**

Run live-browse normally — fallback message should not appear on a working subreddit:
```bash
python fetch.py live-browse ClaudeAI
```

**Step 5: Commit**
```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "fix(fetch-reddit): include page title in empty-result fallback messages"
```

---

### Task 4: Add dynamic Redlib instance fetching (Bug 1)

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py` — module level + `redlib_get()`

**Step 1: Update the hardcoded REDLIB_INSTANCES list (lines 86-92)**

Replace the current 5 dead instances with a list containing only the confirmed-working instance as fallback:
```python
REDLIB_INSTANCES = [
    "https://redlib.freedit.eu",
]
```

This is the fallback used if the dynamic fetch fails. It's a short list intentionally — the dynamic fetch will populate it.

**Step 2: Add the sentinel and two new functions after the REDLIB_UA constant (after line 94)**

Insert after `REDLIB_UA = "..."`:

```python
_instances_fetched = False


def fetch_redlib_instances():
    """Fetch current Redlib instance list from the official registry. Returns URL list or None on error."""
    try:
        r = std_requests.get(
            "https://raw.githubusercontent.com/redlib-org/redlib-instances/main/instances.json",
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        return [
            entry["url"]
            for entry in data.get("instances", [])
            if entry.get("url", "").startswith("https://")
        ]
    except Exception:
        return None


def get_redlib_instances():
    """Return the current instance list, fetching from the registry on first call."""
    global _instances_fetched
    if _instances_fetched:
        return REDLIB_INSTANCES
    fetched = fetch_redlib_instances()
    if fetched:
        # Prepend any hardcoded entries not already in the fetched list (preserves
        # manually-confirmed instances that may not be in the official registry)
        fetched_set = set(fetched)
        extra = [u for u in REDLIB_INSTANCES if u not in fetched_set]
        REDLIB_INSTANCES[:] = extra + fetched
    else:
        print("WARNING: Could not refresh Redlib instance list from GitHub; using fallback.", file=sys.stderr)
    _instances_fetched = True
    return REDLIB_INSTANCES
```

**Step 3: Update redlib_get() to use get_redlib_instances()**

In `redlib_get()`, change line 169 from:
```python
    for base in REDLIB_INSTANCES:
```
to:
```python
    for base in get_redlib_instances():
```

**Step 4: Verify — first live call fetches instances**

```bash
python fetch.py live-browse ClaudeAI
```
Expected: Normal output. On the first call there's a ~1s pause as GitHub is hit; subsequent calls in the same process are instant. No warning printed = dynamic fetch succeeded.

To verify the fetch itself works in isolation:
```bash
python -c "
import requests as std_requests
r = std_requests.get('https://raw.githubusercontent.com/redlib-org/redlib-instances/main/instances.json', timeout=5)
data = r.json()
urls = [e['url'] for e in data.get('instances', []) if e.get('url','').startswith('https://')]
print(f'Fetched {len(urls)} instances')
print(urls[:3])
"
```
Expected: `Fetched N instances` with N > 10 and a list of https:// URLs.

**Step 5: Commit**
```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): dynamically fetch Redlib instance list from official registry on first live call"
```

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `claude-web-only/fetch-reddit/SKILL.md:29`

**Step 1: Update the domain allowlist table entry**

Find the Prerequisites table. The "Package managers + specific domains" row currently lists the dead Redlib instance domains. Update it to:
```
| **Domain access** | Domain allowlist: **"All domains"** OR **"Package managers + specific domains"** with `arctic-shift.photon-reddit.com` and `raw.githubusercontent.com` added |
```

The individual Redlib instance domains no longer need to be listed — the script now fetches instances dynamically and tries many; listing specific ones was misleading anyway.

**Step 2: Add instance refresh note to the "Which domain option to use" bullets**

After the two existing bullets, add:
```
- On the **first `live-*` command** each chat session, the script fetches the current Redlib instance list from `raw.githubusercontent.com` (~1s, one-time). If unreachable, it falls back to a bundled list automatically.
```

**Step 3: Verify the file renders correctly**

Read through the Prerequisites section to confirm nothing looks broken.

**Step 4: Commit**
```bash
git add claude-web-only/fetch-reddit/SKILL.md
git commit -m "docs(fetch-reddit): update domain allowlist prereqs and add instance refresh note"
```

---

### Task 6: Update troubleshooting.md

**Files:**
- Modify: `claude-web-only/fetch-reddit/references/troubleshooting.md`

**Step 1: Add Reddit-blocking-instance section**

Append to the "Redlib errors" section (after the existing "Connection errors" entry, before "Free tier limitations"):

```markdown
### Redlib returns a page but posts are empty, or page title is an error message

**Cause:** The Redlib instance loaded successfully (Anubis solved, cookie set) but Reddit's API rejected that instance's requests. Redlib serves its own error page as HTTP 200 — common titles: "Backend temporarily unavailable. Retrying..." or "Error: Failed to parse page JSON data".

The script now detects these and skips to the next instance. If all instances show this error, Reddit is throttling all currently-known Redlib instance IPs.

**Tell the user:**
> "All Redlib instances are currently being blocked by Reddit's API. This happens periodically as Reddit tightens its crackdown on alternative frontends. Archive commands (`browse`, `search`, `post`, `comments`) still work via Arctic Shift for content older than ~36 hours."
```

**Step 2: Add instance list fetch failure section**

Append after the section just added:

```markdown
### Warning: Could not refresh Redlib instance list from GitHub

**Cause:** The request to `raw.githubusercontent.com` timed out or failed. The script falls back to its bundled instance list automatically — live commands will still work if the bundled instances are up.

**If you see this warning repeatedly:**
> "The skill couldn't reach GitHub to refresh the Redlib instance list and is using a potentially stale fallback. Check that `raw.githubusercontent.com` is accessible under your domain allowlist settings."
```

**Step 3: Commit**
```bash
git add claude-web-only/fetch-reddit/references/troubleshooting.md
git commit -m "docs(fetch-reddit): add troubleshooting entries for Reddit-blocked instances and instance list fetch failure"
```

---

### Task 7: Update browsing-live.md

**Files:**
- Modify: `claude-web-only/fetch-reddit/references/browsing-live.md:93`

**Step 1: Update the Instance failover limitation bullet**

Find the Limitations section. Replace:
```markdown
- **Instance failover:** The script tries multiple Redlib instances in order. If all fail, it reports which instances were tried and why each failed.
```
with:
```markdown
- **Instance failover:** At the start of each chat, the first `live-*` command fetches the current instance list from the official Redlib registry (`github.com/redlib-org/redlib-instances`). The script then tries instances in order until one returns valid content. If all fail — typically because Reddit is blocking that instance's API calls — it reports each failure reason explicitly. Fall back to archive commands in that case.
```

**Step 2: Commit**
```bash
git add claude-web-only/fetch-reddit/references/browsing-live.md
git commit -m "docs(fetch-reddit): update instance failover description to reflect dynamic fetching"
```

---

## Verification Checklist

After all tasks:

- [ ] `live-browse ClaudeAI` returns posts with `/r/ClaudeAI/comments/...` permalinks (not flair search URLs)
- [ ] `live-browse ClaudeAI` completes without error in ~5-10s (first call includes instance fetch)
- [ ] `live-post <recent_post_id> --comments 5` returns post + comments
- [ ] `live-comments <recent_post_id>` returns comments
- [ ] No `WARNING: Could not refresh` message on a normal run (confirms GitHub fetch works)
- [ ] SKILL.md domain table no longer lists dead Redlib instance domains
- [ ] troubleshooting.md has two new Redlib sections
- [ ] browsing-live.md Limitations has the updated instance failover bullet

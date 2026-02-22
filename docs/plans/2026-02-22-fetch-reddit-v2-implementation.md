# fetch-reddit v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend fetch-reddit with real-time Redlib access (Anubis PoW) and all unused Arctic Shift API capabilities.

**Architecture:** Single `fetch.py` script expansion. Redlib commands prefixed `live-`. Arctic Shift commands enhanced with new flags. SKILL.md restructured with `references/` for progressive disclosure.

**Tech Stack:** Python 3, `curl_cffi` (Arctic Shift), `requests` + `beautifulsoup4` (Redlib), `hashlib` (Anubis PoW)

---

## Task 1: Add Anubis PoW Solver to fetch.py

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py:1-58` (imports, constants section)

**Step 1: Add Redlib imports and constants**

Add after the `curl_cffi` import block (line 38), before the constants section:

```python
import hashlib
import re as _re

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "beautifulsoup4", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    from bs4 import BeautifulSoup

try:
    import requests as std_requests
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "requests", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    import requests as std_requests
```

Add to the constants section:

```python
REDLIB_INSTANCES = [
    "https://redlib.tiekoetter.com",
    "https://safereddit.com",
    "https://redlib.zaggy.nl",
    "https://red.artemislena.eu",
    "https://l.opnxng.com",
]

REDLIB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
```

**Step 2: Add `solve_anubis()` and `redlib_get()` helper functions**

Add after the existing `fmt_date()` helper:

```python
def solve_anubis(session, url):
    """Fetch a URL through Anubis PoW protection. Returns the response."""
    from urllib.parse import urlparse

    r = session.get(url, timeout=15, verify=False)

    # Check for Anubis challenge
    m = _re.search(r'id="anubis_challenge"[^>]*>(.*?)</script>', r.text, _re.DOTALL)
    if not m:
        return r  # No challenge — already authed or no Anubis

    # Parse challenge
    chal = json.loads(m.group(1))
    random_data = chal['challenge']['randomData']
    difficulty = chal['rules']['difficulty']
    zero_bytes = difficulty // 2
    check_nibble = difficulty % 2 != 0

    # Solve PoW
    nonce = 0
    while True:
        h = hashlib.sha256(f"{random_data}{nonce}".encode()).digest()
        ok = all(h[i] == 0 for i in range(zero_bytes))
        if ok and check_nibble and (h[zero_bytes] >> 4) != 0:
            ok = False
        if ok:
            break
        nonce += 1

    # Submit solution
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    session.get(
        f"{base}/.within.website/x/cmd/anubis/api/pass-challenge",
        params={
            'id': chal['challenge']['id'],
            'response': h.hex(),
            'nonce': str(nonce),
            'redir': parsed.path or '/',
            'elapsedTime': '100',
        },
        allow_redirects=True, timeout=15, verify=False
    )

    # Re-fetch with auth cookie
    return session.get(url, timeout=15, verify=False)


def redlib_get(path):
    """Try Redlib instances in order. Returns (BeautifulSoup, base_url) or exits on failure."""
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    session = std_requests.Session()
    session.headers['User-Agent'] = REDLIB_UA

    errors = []
    for base in REDLIB_INSTANCES:
        url = f"{base}{path}"
        try:
            r = solve_anubis(session, url)
            if r.status_code == 200 and "anubis" not in r.text.lower()[:500]:
                return BeautifulSoup(r.text, "html.parser"), base
            errors.append(f"{base}: got Anubis page despite solving")
        except Exception as e:
            errors.append(f"{base}: {e}")

    print("ERROR: All Redlib instances failed:", file=sys.stderr)
    for err in errors:
        print(f"  {err}", file=sys.stderr)
    sys.exit(1)
```

**Step 3: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): add Anubis PoW solver and Redlib client"
```

---

## Task 2: Add Redlib HTML Parsers

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py` (add parser functions after `redlib_get`)

**Step 1: Add `parse_redlib_posts()` function**

```python
def parse_redlib_posts(soup):
    """Parse post listing from Redlib HTML. Returns list of post dicts."""
    posts_div = soup.select_one("div#posts")
    if not posts_div:
        return []

    results = []
    for el in posts_div.select("div.post"):
        post = {}
        post["id"] = el.get("id", "")

        # Title
        title_el = el.select_one("h2.post_title")
        if title_el:
            title_link = title_el.select_one("a[href]")
            post["title"] = title_link.get_text(strip=True) if title_link else title_el.get_text(strip=True)
            post["permalink"] = title_link["href"] if title_link else ""
        else:
            continue  # skip posts without titles

        # Author
        author_el = el.select_one("a.post_author")
        post["author"] = author_el.get_text(strip=True).removeprefix("u/") if author_el else "[unknown]"

        # Subreddit
        sub_el = el.select_one("a.post_subreddit")
        post["subreddit"] = sub_el.get_text(strip=True).removeprefix("r/") if sub_el else ""

        # Score
        score_el = el.select_one("div.post_score")
        if score_el and score_el.get("title"):
            try:
                post["score"] = int(score_el["title"])
            except ValueError:
                post["score"] = 0
        else:
            post["score"] = 0

        # Comment count
        comments_el = el.select_one("a.post_comments")
        if comments_el and comments_el.get("title"):
            try:
                post["num_comments"] = int(comments_el["title"].split()[0])
            except (ValueError, IndexError):
                post["num_comments"] = 0
        else:
            post["num_comments"] = 0

        # Flair
        flair_el = el.select_one("a.post_flair")
        post["link_flair_text"] = flair_el.get_text(strip=True) if flair_el else ""

        # Timestamp
        time_el = el.select_one("span.created")
        post["time_relative"] = time_el.get_text(strip=True) if time_el else ""
        post["time_absolute"] = time_el.get("title", "") if time_el else ""

        # NSFW / spoiler
        post["over_18"] = bool(el.select_one("small.nsfw"))
        post["spoiler"] = bool(el.select_one("small.spoiler"))
        post["stickied"] = "stickied" in el.get("class", [])

        # Body preview
        body_el = el.select_one("div.post_body.post_preview")
        post["body_preview"] = body_el.get_text(strip=True)[:300] if body_el else ""

        results.append(post)

    return results


def parse_redlib_post_detail(soup):
    """Parse a single post detail page. Returns post dict."""
    el = soup.select_one("div.post.highlighted")
    if not el:
        el = soup.select_one("div.post")
    if not el:
        return None

    post = {}
    post["id"] = el.get("id", "")

    # Title (h1 on detail page)
    title_el = el.select_one("h1.post_title")
    if title_el:
        # Remove flair/nsfw/spoiler tags to get clean title
        for tag in title_el.select("a.post_flair, small.nsfw, small.spoiler"):
            tag.decompose()
        post["title"] = title_el.get_text(strip=True)
    else:
        post["title"] = "[untitled]"

    # Re-parse flair from a fresh copy if needed
    flair_el = el.select_one("a.post_flair")
    post["link_flair_text"] = flair_el.get_text(strip=True) if flair_el else ""

    # Author, subreddit, score (same selectors as listing)
    author_el = el.select_one("a.post_author")
    post["author"] = author_el.get_text(strip=True).removeprefix("u/") if author_el else "[unknown]"

    sub_el = el.select_one("a.post_subreddit")
    post["subreddit"] = sub_el.get_text(strip=True).removeprefix("r/") if sub_el else ""

    score_el = el.select_one("div.post_score")
    if score_el and score_el.get("title"):
        try:
            post["score"] = int(score_el["title"])
        except ValueError:
            post["score"] = 0
    else:
        post["score"] = 0

    # Comment count
    count_el = soup.select_one("p#comment_count")
    if count_el:
        try:
            post["num_comments"] = int(count_el.get_text(strip=True).split()[0])
        except (ValueError, IndexError):
            post["num_comments"] = 0
    else:
        post["num_comments"] = 0

    # Timestamp
    time_el = el.select_one("span.created")
    post["time_relative"] = time_el.get_text(strip=True) if time_el else ""
    post["time_absolute"] = time_el.get("title", "") if time_el else ""

    # Flags
    post["over_18"] = bool(el.select_one("small.nsfw"))
    post["spoiler"] = bool(el.select_one("small.spoiler"))
    post["locked"] = False  # Not reliably detectable from Redlib HTML

    # Full body
    body_el = el.select_one("div.post_body")
    if body_el and "post_preview" not in body_el.get("class", []):
        post["body"] = body_el.get_text(separator="\n", strip=True)
    else:
        post["body"] = ""

    # Upvote ratio
    ratio_el = el.select_one("div.post_footer p")
    if ratio_el:
        ratio_text = ratio_el.get_text(strip=True)
        if "%" in ratio_text:
            post["upvote_ratio"] = ratio_text.split("%")[0] + "%"

    return post


def parse_redlib_comments(soup, limit=DEFAULT_COMMENT_LIMIT):
    """Parse comments from a Redlib post page. Returns list of formatted strings."""

    def _parse_comment(el, depth=0):
        """Recursively parse a comment and its replies."""
        results = []

        author_el = el.select_one(":scope > details.comment_right > summary.comment_data > a.comment_author")
        if not author_el:
            return results
        author = author_el.get_text(strip=True)
        is_op = "op" in author_el.get("class", [])

        score_el = el.select_one(":scope > div.comment_left > p.comment_score")
        score_raw = score_el.get("title", "0") if score_el else "0"
        try:
            score = int(score_raw)
        except ValueError:
            score = 0

        body_el = el.select_one(":scope > details.comment_right > div.comment_body")
        body = body_el.get_text(separator="\n", strip=True) if body_el else ""

        if not body or body in ("[deleted]", "[removed]"):
            return results

        results.append({
            "author": author,
            "score": score,
            "body": body,
            "depth": depth,
            "is_op": is_op,
        })

        # Parse replies
        replies_el = el.select_one(":scope > details.comment_right > blockquote.replies")
        if replies_el:
            for child in replies_el.select(":scope > div.comment"):
                results.extend(_parse_comment(child, depth + 1))

        return results

    all_comments = []
    for thread in soup.select("div.thread > div.comment"):
        all_comments.extend(_parse_comment(thread))

    # Sort by score descending, take top N
    all_comments.sort(key=lambda c: c["score"], reverse=True)
    top = all_comments[:limit]

    formatted = []
    for c in top:
        indent = "  " * c["depth"]
        op_tag = " [OP]" if c["is_op"] else ""
        header = f"{indent}**{c['author']}**{op_tag} (↑{c['score']})"
        body_lines = "\n".join(f"{indent}{line}" for line in c["body"].splitlines())
        formatted.append(f"{header}\n{body_lines}")

    return formatted, len(all_comments)
```

**Step 2: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): add Redlib HTML parsers for posts and comments"
```

---

## Task 3: Add live-browse, live-post, live-comments Commands

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py` (add command functions and argparse entries)

**Step 1: Add `cmd_live_browse()` function**

Add after the existing `cmd_user()`:

```python
def cmd_live_browse(args):
    sort = args.sort or "hot"
    path = f"/r/{args.subreddit}/{sort}"
    soup, base_url = redlib_get(path)
    posts = parse_redlib_posts(soup)
    if not posts:
        print(f"No posts found in r/{args.subreddit} (live). Redlib HTML may have changed or the subreddit may not exist.")
        return
    print(f"# r/{args.subreddit} — {len(posts)} {sort} posts (live via Redlib)\n")
    for p in posts:
        flair = f" [{p['link_flair_text']}]" if p.get("link_flair_text") else ""
        nsfw = " 🔞" if p.get("over_18") else ""
        pin = " 📌" if p.get("stickied") else ""
        preview = ""
        if p.get("body_preview"):
            snippet = p["body_preview"][:200].replace("\n", " ")
            preview = f"\n  > {snippet}{'…' if len(p['body_preview']) > 200 else ''}"
        print(f"- **{p['title']}**{flair}{nsfw}{pin} | u/{p['author']} | ↑{p['score']} | {p['num_comments']} comments | {p['time_relative']}")
        print(f"  `{p['id']}` — {base_url}{p.get('permalink', '')}{preview}")
        print()
```

**Step 2: Add `cmd_live_post()` function**

```python
def cmd_live_post(args):
    post_id = args.post_id.removeprefix("t3_")
    # Try to construct the Redlib URL — we need the subreddit
    # Redlib accepts /comments/ID format
    path = f"/comments/{post_id}"
    soup, base_url = redlib_get(path)
    post = parse_redlib_post_detail(soup)
    if not post:
        print(f"Could not parse post {post_id} from Redlib. HTML structure may have changed.")
        return

    nsfw = " 🔞 NSFW" if post.get("over_18") else ""
    flair = f" | **Flair:** {post['link_flair_text']}" if post.get("link_flair_text") else ""
    ratio = f" | **Upvoted:** {post.get('upvote_ratio', 'N/A')}" if post.get("upvote_ratio") else ""

    print(f"## {post['title']}{nsfw}")
    print(f"**ID:** {post['id']} | **Author:** u/{post['author']} | **r/{post['subreddit']}**{flair}")
    print(f"**Score:** {post['score']} | **Comments:** {post['num_comments']} | **Posted:** {post['time_relative']}{ratio}")
    print(f"**Source:** {base_url}/comments/{post_id}")

    if post.get("body"):
        print(f"\n{post['body']}")

    if args.comments is not None:
        print()
        comments, total = parse_redlib_comments(soup, args.comments)
        if comments:
            print(f"---\n### Top {len(comments)} Comments (from {total} parsed, sorted by score)\n")
            for block in comments:
                print(block)
                print()
        else:
            print("*No comments found.*")
```

**Step 3: Add `cmd_live_comments()` function**

```python
def cmd_live_comments(args):
    post_id = args.post_id.removeprefix("t3_")
    path = f"/comments/{post_id}"
    soup, base_url = redlib_get(path)
    comments, total = parse_redlib_comments(soup, args.limit)
    if not comments:
        print(f"No comments found for post {post_id} (live).")
        return
    print(f"---\n### Top {len(comments)} Comments (from {total} parsed, sorted by score) — live via Redlib\n")
    for block in comments:
        print(block)
        print()
```

**Step 4: Add argparse entries for the new commands**

Add to the `main()` function, before `args = parser.parse_args()`:

```python
p_live_browse = sub.add_parser("live-browse", help="Browse real-time posts via Redlib")
p_live_browse.add_argument("subreddit")
p_live_browse.add_argument("--sort", choices=["hot", "new", "rising", "top"], default="hot",
                           help="Sort order (default: hot)")

p_live_post = sub.add_parser("live-post", help="Fetch a post with real-time data via Redlib")
p_live_post.add_argument("post_id")
p_live_post.add_argument("--comments", type=int, metavar="N",
                         help="Also fetch top N comments")

p_live_comments = sub.add_parser("live-comments", help="Fetch real-time comments via Redlib")
p_live_comments.add_argument("post_id")
p_live_comments.add_argument("--limit", type=int, default=DEFAULT_COMMENT_LIMIT,
                             help=f"Number of top comments (default: {DEFAULT_COMMENT_LIMIT})")
```

Update the command dispatch dict in `main()`:

```python
{"post": cmd_post, "comments": cmd_comments, "browse": cmd_browse,
 "search": cmd_search, "user": cmd_user,
 "live-browse": cmd_live_browse, "live-post": cmd_live_post,
 "live-comments": cmd_live_comments}[args.cmd](args)
```

**Step 5: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): add live-browse, live-post, live-comments commands"
```

---

## Task 4: Expand Arctic Shift browse and search Commands

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py` (modify `cmd_browse`, `cmd_search`, argparse)

**Step 1: Enhance `cmd_browse()` with new parameters**

Replace the existing `cmd_browse()`:

```python
def cmd_browse(args):
    params = {
        "subreddit": args.subreddit,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    }
    if args.flair:
        params["link_flair_text"] = args.flair
    if args.after:
        params["after"] = args.after
    if args.before:
        params["before"] = args.before
    if args.nsfw:
        params["over_18"] = "true"
    if args.author:
        params["author"] = args.author

    data = get(f"{BASE}/api/posts/search", params)
    posts = data.get("data", [])
    if not posts:
        print(f"No posts found in r/{args.subreddit}")
        return

    # Build header with active filters
    filters = []
    if args.flair:
        filters.append(f"flair: {args.flair}")
    if args.after:
        filters.append(f"after: {args.after}")
    if args.before:
        filters.append(f"before: {args.before}")
    filter_str = f" ({', '.join(filters)})" if filters else ""

    print(f"# r/{args.subreddit} — {len(posts)} recent posts{filter_str}\n")
    for p in posts:
        _print_post_digest(p)

    # Pagination hint
    if len(posts) == args.limit:
        last_ts = posts[-1].get("created_utc")
        if last_ts:
            print(f"<!-- next_page: --before {last_ts} -->")
```

**Step 2: Enhance `cmd_search()` with new parameters**

Replace the existing `cmd_search()`:

```python
def cmd_search(args):
    params = {
        "subreddit": args.subreddit,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    }

    # Determine search mode
    if args.title_only:
        params["title"] = args.keywords
    elif args.body_only:
        params["selftext"] = args.keywords
    else:
        params["query"] = args.keywords

    if args.flair:
        params["link_flair_text"] = args.flair
    if args.after:
        params["after"] = args.after
    if args.before:
        params["before"] = args.before
    if args.author:
        params["author"] = args.author

    data = get(f"{BASE}/api/posts/search", params)
    posts = data.get("data", [])
    if not posts:
        print(f"No posts found in r/{args.subreddit} matching '{args.keywords}'")
        return
    print(f"# Search: '{args.keywords}' in r/{args.subreddit} — {len(posts)} results\n")
    for p in posts:
        _print_post_digest(p)

    # Pagination hint
    if len(posts) == args.limit:
        last_ts = posts[-1].get("created_utc")
        if last_ts:
            print(f"<!-- next_page: --before {last_ts} -->")
```

**Step 3: Update argparse for browse and search**

Replace the existing `p_browse` and `p_search` blocks:

```python
p_browse = sub.add_parser("browse", help="Browse recent posts in a subreddit")
p_browse.add_argument("subreddit")
p_browse.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                      help=f"Number of posts (default: {DEFAULT_POST_LIMIT})")
p_browse.add_argument("--flair", help="Filter by flair (exact match)")
p_browse.add_argument("--after", help="Posts after this time (e.g., 7d, 2024-01-01)")
p_browse.add_argument("--before", help="Posts before this time")
p_browse.add_argument("--nsfw", action="store_true", help="Include NSFW posts")
p_browse.add_argument("--author", help="Filter by author")

p_search = sub.add_parser("search", help="Search posts by keyword in a subreddit")
p_search.add_argument("subreddit")
p_search.add_argument("keywords")
p_search.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                      help=f"Number of results (default: {DEFAULT_POST_LIMIT})")
p_search.add_argument("--title-only", action="store_true", help="Search titles only")
p_search.add_argument("--body-only", action="store_true", help="Search post bodies only")
p_search.add_argument("--flair", help="Filter by flair (exact match)")
p_search.add_argument("--after", help="Posts after this time")
p_search.add_argument("--before", help="Posts before this time")
p_search.add_argument("--author", help="Filter by author")
```

**Step 4: Update `cmd_user()` with time filters**

Add `--after` and `--before` to user command argparse:

```python
p_user = sub.add_parser("user", help="Fetch a user's recent posts and comments")
p_user.add_argument("username")
p_user.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                    help=f"Number of each (default: {DEFAULT_POST_LIMIT})")
p_user.add_argument("--after", help="Activity after this time")
p_user.add_argument("--before", help="Activity before this time")
```

Update `cmd_user()` to pass time params:

```python
def cmd_user(args):
    print(f"# u/{args.username} — Recent activity\n")

    post_params = {
        "author": args.username,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    }
    if args.after:
        post_params["after"] = args.after
    if args.before:
        post_params["before"] = args.before

    posts = get(f"{BASE}/api/posts/search", post_params).get("data", [])
    if posts:
        print(f"## Posts ({len(posts)})\n")
        for p in posts:
            permalink = p.get("permalink") or f"/r/{p['subreddit']}/comments/{p['id']}/"
            print(f"- **{p['title']}** in r/{p['subreddit']} | ↑{p['score']} | {fmt_date(p['created_utc'])}")
            print(f"  `{p['id']}` — https://reddit.com{permalink}")
            print()

    comment_params = {
        "author": args.username,
        "sort": "desc",
        "limit": args.limit,
        "fields": COMMENT_FIELDS,
    }
    if args.after:
        comment_params["after"] = args.after
    if args.before:
        comment_params["before"] = args.before

    comments = get(f"{BASE}/api/comments/search", comment_params).get("data", [])
    if comments:
        print(f"## Comments ({len(comments)})\n")
        for c in comments:
            body = (c.get("body") or "").strip()
            if not body or body in ("[deleted]", "[removed]"):
                continue
            snippet = body[:300].replace("\n", " ")
            post_id = (c.get("link_id") or "").removeprefix("t3_")
            print(f"- ↑{c.get('score', 0)} in r/{c.get('subreddit', '?')} | {fmt_date(c['created_utc'])}")
            print(f"  > {snippet}{'…' if len(body) > 300 else ''}")
            print(f"  Post: `{post_id}`")
            print()
```

**Step 5: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): add flair/time/title/body filters to browse and search"
```

---

## Task 5: Add subreddit-info and user-info Commands

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py`

**Step 1: Add `cmd_subreddit_info()` function**

```python
def cmd_subreddit_info(args):
    data = get(f"{BASE}/api/subreddits/search", {
        "subreddit": args.subreddit,
        "limit": 1,
    })
    subs = data.get("data", [])
    if not subs:
        print(f"No subreddit found: r/{args.subreddit}")
        return

    s = subs[0]
    nsfw = " 🔞 NSFW" if s.get("over18") else ""
    print(f"# r/{s.get('display_name', args.subreddit)}{nsfw}\n")
    print(f"**Subscribers:** {s.get('subscribers', 'N/A'):,}")
    if s.get("active_user_count"):
        print(f"**Active users:** {s['active_user_count']:,}")
    print(f"**Created:** {fmt_date(s['created_utc'])}" if s.get("created_utc") else "")

    title = s.get("title", "")
    if title:
        print(f"**Title:** {title}")

    desc = s.get("public_description", "")
    if desc:
        print(f"\n{desc.strip()}")

    # Long description
    long_desc = s.get("description", "")
    if long_desc and long_desc != desc:
        print(f"\n---\n{long_desc.strip()[:1000]}")
```

**Step 2: Add `cmd_user_info()` function**

```python
def cmd_user_info(args):
    data = get(f"{BASE}/api/users/search", {
        "author": args.username,
        "limit": 1,
    })
    users = data.get("data", [])
    if not users:
        print(f"No user found: u/{args.username}")
        return

    u = users[0]
    meta = u.get("_meta", {})

    print(f"# u/{u.get('author', args.username)}\n")

    if meta.get("total_karma"):
        print(f"**Total karma:** {meta['total_karma']:,}")
    if meta.get("post_karma") is not None:
        print(f"**Post karma:** {meta['post_karma']:,} | **Comment karma:** {meta.get('comment_karma', 0):,}")
    if meta.get("num_posts") is not None:
        print(f"**Posts:** {meta['num_posts']:,} | **Comments:** {meta.get('num_comments', 0):,}")

    if meta.get("earliest_post_at"):
        print(f"**First post:** {fmt_date(meta['earliest_post_at'])}")
    if meta.get("last_post_at"):
        print(f"**Last post:** {fmt_date(meta['last_post_at'])}")
    if meta.get("last_comment_at"):
        print(f"**Last comment:** {fmt_date(meta['last_comment_at'])}")
```

**Step 3: Add argparse entries**

```python
p_sub_info = sub.add_parser("subreddit-info", help="Get subreddit metadata")
p_sub_info.add_argument("subreddit")

p_user_info = sub.add_parser("user-info", help="Get user profile stats")
p_user_info.add_argument("username")
```

Update dispatch dict:

```python
{"post": cmd_post, "comments": cmd_comments, "browse": cmd_browse,
 "search": cmd_search, "user": cmd_user,
 "live-browse": cmd_live_browse, "live-post": cmd_live_post,
 "live-comments": cmd_live_comments,
 "subreddit-info": cmd_subreddit_info, "user-info": cmd_user_info,
 }[args.cmd](args)
```

**Step 4: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "feat(fetch-reddit): add subreddit-info and user-info commands"
```

---

## Task 6: Update SKILL.md (lean version)

**Files:**
- Modify: `claude-web-only/fetch-reddit/SKILL.md`

**Step 1: Rewrite SKILL.md**

Replace the entire file with the lean version. Keep the YAML frontmatter, prerequisites, and purpose sections largely intact. Replace the Cookbook section with a command reference table and routing guidance. Point to `references/` for detailed scenarios.

Key changes:
- Add Redlib domains to the prerequisites domain allowlist
- Add `beautifulsoup4` and `requests` to dependency notes
- Replace verbose Cookbook with a quick-reference command table
- Add source routing guidance (when to use `live-*` vs archive)
- Reference the `references/` directory for detailed usage

The updated SKILL.md should follow this structure:

```
---
name: fetch-reddit
description: [updated to mention both Redlib and Arctic Shift]
---

# Prerequisites
[Updated with Redlib domains]

# Purpose
[Updated to explain dual-source architecture]

# Quick Reference
[Command table with all 11 commands, their flags, and one-line descriptions]

# Source Routing
[When to use live-* vs archive commands — the decision guide for the LLM]

# Detailed Usage
[Point to references/ directory files]

# Troubleshooting
[Updated with Redlib-specific issues]
```

**Step 2: Commit**

```bash
git add claude-web-only/fetch-reddit/SKILL.md
git commit -m "docs(fetch-reddit): rewrite SKILL.md with lean command reference"
```

---

## Task 7: Create references/ Directory

**Files:**
- Create: `claude-web-only/fetch-reddit/references/browsing-live.md`
- Create: `claude-web-only/fetch-reddit/references/browsing-archive.md`
- Create: `claude-web-only/fetch-reddit/references/searching.md`
- Create: `claude-web-only/fetch-reddit/references/posts-and-comments.md`
- Create: `claude-web-only/fetch-reddit/references/user-and-subreddit-info.md`
- Create: `claude-web-only/fetch-reddit/references/troubleshooting.md`

**Step 1: Create `browsing-live.md`**

Cover:
- `live-browse SUBREDDIT [--sort hot|new|rising|top]` — when to use, example output
- `live-post POST_ID [--comments N]` — reading posts with real-time scores
- `live-comments POST_ID [--limit N]` — fetching comment threads
- Example triggers: "What's trending?", "Show me hot posts", "Read this post with current scores"
- Note: Redlib has no search — use Arctic Shift `search` for keyword queries

**Step 2: Create `browsing-archive.md`**

Cover:
- `browse SUBREDDIT [--flair F] [--after T] [--before T] [--nsfw] [--author U] [--limit N]`
- Pagination via `--before TIMESTAMP` using the `<!-- next_page -->` hint
- Filter combinations (flair + time range, author + subreddit)
- Example triggers: "Show me Bug-flaired posts", "Posts from last week", "What did user X post in subreddit Y?"

**Step 3: Create `searching.md`**

Cover:
- `search SUBREDDIT "query" [--title-only] [--body-only] [--flair F] [--after T] [--before T] [--author U] [--limit N]`
- Full-text vs title-only vs body-only search modes
- Combining with flair and time filters
- Limitation: search requires a subreddit (no cross-Reddit search)
- Example triggers: "Find posts about X in r/Y", "Search titles for Z"

**Step 4: Create `posts-and-comments.md`**

Cover:
- `post POST_ID [--comments N]` — archive post fetch
- `comments POST_ID [--limit N]` — standalone comment fetch
- How to extract post IDs from Reddit URLs
- Score-sorting behavior (fetch 100, sort, return top N)

**Step 5: Create `user-and-subreddit-info.md`**

Cover:
- `user USERNAME [--limit N] [--after T] [--before T]` — activity history
- `user-info USERNAME` — profile stats (karma, counts, dates)
- `subreddit-info SUBREDDIT` — metadata (subscribers, description, rules)
- Example triggers: "Tell me about r/X", "What's u/Y's karma?"

**Step 6: Create `troubleshooting.md`**

Migrate existing troubleshooting from SKILL.md and add:
- Redlib-specific: Anubis solver failures, instance failover, HTML parse errors
- "All Redlib instances failed" — what to tell the user
- "Redlib HTML format may have changed" — fallback to Arctic Shift
- Existing: curl_cffi install, Arctic Shift connection, free tier, empty results

**Step 7: Commit**

```bash
git add claude-web-only/fetch-reddit/references/
git commit -m "docs(fetch-reddit): add reference files for progressive disclosure"
```

---

## Task 8: Update fetch.py Docstring and Script Header

**Files:**
- Modify: `claude-web-only/fetch-reddit/scripts/fetch.py:1-12`

**Step 1: Update the module docstring**

```python
#!/usr/bin/env python3
"""
Reddit content fetcher via Arctic Shift (archive) and Redlib (real-time).
Returns clean markdown formatted for LLM ingestion.

Archive commands (Arctic Shift):
  python fetch.py post POST_ID [--comments N]
  python fetch.py browse SUBREDDIT [--flair F] [--after T] [--before T] [--nsfw] [--limit N]
  python fetch.py search SUBREDDIT "keywords" [--title-only] [--body-only] [--flair F] [--after T] [--before T] [--limit N]
  python fetch.py comments POST_ID [--limit N]
  python fetch.py user USERNAME [--limit N] [--after T] [--before T]
  python fetch.py subreddit-info SUBREDDIT
  python fetch.py user-info USERNAME

Live commands (Redlib):
  python fetch.py live-browse SUBREDDIT [--sort hot|new|rising|top]
  python fetch.py live-post POST_ID [--comments N]
  python fetch.py live-comments POST_ID [--limit N]
"""
```

**Step 2: Commit**

```bash
git add claude-web-only/fetch-reddit/scripts/fetch.py
git commit -m "docs(fetch-reddit): update script docstring with all commands"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Anubis PoW solver + Redlib client | fetch.py |
| 2 | Redlib HTML parsers | fetch.py |
| 3 | live-browse, live-post, live-comments commands | fetch.py |
| 4 | Enhanced browse/search/user with filters | fetch.py |
| 5 | subreddit-info and user-info commands | fetch.py |
| 6 | Lean SKILL.md rewrite | SKILL.md |
| 7 | Reference files for progressive disclosure | references/*.md |
| 8 | Updated docstring | fetch.py |

Total: 8 tasks, ~8 commits, 8 files touched/created.

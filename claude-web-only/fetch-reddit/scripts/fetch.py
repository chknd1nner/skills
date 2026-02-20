#!/usr/bin/env python3
"""
Arctic Shift Reddit fetch script.
Returns clean markdown formatted for LLM ingestion.

Usage:
  python fetch.py post POST_ID [--comments N]
  python fetch.py browse SUBREDDIT [--limit N]
  python fetch.py search SUBREDDIT "keywords" [--limit N]
  python fetch.py comments POST_ID [--limit N]
  python fetch.py user USERNAME [--limit N]
"""

import sys
import json
import argparse
from datetime import datetime, timezone

try:
    from curl_cffi import requests
except ImportError:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "curl_cffi", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            "ERROR: Failed to install required dependency 'curl_cffi'.\n"
            f"pip exited with code {result.returncode}.\n"
            f"{result.stderr.strip()}\n\n"
            "This may be caused by a network issue (e.g. blocked request or 403 from PyPI), "
            "a permissions problem, or an incompatible Python environment. "
            "Try running `pip install curl_cffi` manually to diagnose.",
            file=sys.stderr
        )
        sys.exit(1)
    from curl_cffi import requests

# ── Constants ─────────────────────────────────────────────────────────────────

BASE = "https://arctic-shift.photon-reddit.com"

# Fields valid for /search endpoints (broader set)
SEARCH_FIELDS = "id,title,author,selftext,score,num_comments,created_utc,subreddit,link_flair_text,over_18,url"

# Fields valid for /comments endpoints
COMMENT_FIELDS = "id,author,body,score,parent_id,link_id,created_utc"

# Post keys to keep when fetching by /ids (filter in Python, fields= is fragile here)
POST_KEEP = {"id","title","author","selftext","score","num_comments","created_utc",
             "subreddit","link_flair_text","over_18","url","permalink",
             "is_self","is_video","locked","stickied","domain","is_gallery"}

COMMENT_FETCH_SIZE = 100    # fetch this many from API before trimming
DEFAULT_COMMENT_LIMIT = 20  # return this many to LLM unless --limit passed
DEFAULT_POST_LIMIT = 25

# ── Helpers ───────────────────────────────────────────────────────────────────

def get(url, params=None):
    try:
        r = requests.get(url, params=params, impersonate="chrome", timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def fmt_date(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_post(p):
    lines = []
    flair  = f" | **Flair:** {p['link_flair_text']}" if p.get("link_flair_text") else ""
    locked = " 🔒 LOCKED" if p.get("locked") else ""
    nsfw   = " 🔞 NSFW"   if p.get("over_18") else ""

    lines.append(f"## {p['title']}{locked}{nsfw}")
    lines.append(f"**ID:** {p['id']} | **Author:** u/{p['author']} | **r/{p['subreddit']}**{flair}")
    lines.append(f"**Score:** {p['score']} | **Comments:** {p['num_comments']} | **Posted:** {fmt_date(p['created_utc'])}")

    permalink = p.get("permalink") or f"/r/{p['subreddit']}/comments/{p['id']}/"
    lines.append(f"**URL:** https://reddit.com{permalink}")

    body = (p.get("selftext") or "").strip()
    if body and body not in ("[deleted]", "[removed]"):
        lines.append("")
        lines.append(body)
    else:
        url = p.get("url") or ""
        if url and not url.startswith("https://www.reddit.com/r/"):
            domain = p.get("domain") or ""
            if p.get("is_video") or domain == "v.redd.it":
                tag = "Video"
            elif "gallery" in url:
                tag = "Gallery"
            elif domain in ("i.redd.it",):
                tag = "Image"
            else:
                tag = f"Link — {domain}" if domain else "Link"
            lines.append(f"\n*[{tag}: {url}]*")

    return "\n".join(lines)


def fmt_comment(c, depth=0):
    body = (c.get("body") or "").strip()
    if not body or body in ("[deleted]", "[removed]"):
        return None
    indent = "  " * depth
    author = f"u/{c['author']}" if c.get("author") and c["author"] != "[deleted]" else "[deleted]"
    score = c.get("score", 0)
    header = f"{indent}**{author}** (↑{score})"
    body_indented = "\n".join(f"{indent}{line}" for line in body.splitlines())
    return f"{header}\n{body_indented}"


def top_comments(comments, limit):
    """Fetch COMMENT_FETCH_SIZE, sort by score desc, return top N formatted."""
    valid = [c for c in comments
             if (c.get("body") or "").strip() not in ("", "[deleted]", "[removed]")]
    valid.sort(key=lambda c: c.get("score", 0), reverse=True)
    top = valid[:limit]
    result = []
    for c in top:
        pid = c.get("parent_id", "")
        depth = 0 if pid.startswith("t3_") else 1
        fmt = fmt_comment(c, depth)
        if fmt:
            result.append(fmt)
    return result, len(valid)

# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_post(args):
    post_id = args.post_id.removeprefix("t3_")
    data = get(f"{BASE}/api/posts/ids", {"ids": post_id})
    posts = data.get("data", [])
    if not posts:
        print(f"No post found with ID: {post_id}")
        return
    p = {k: v for k, v in posts[0].items() if k in POST_KEEP}
    print(fmt_post(p))

    if args.comments is not None:
        print()
        _print_comments(post_id, args.comments)


def cmd_comments(args):
    post_id = args.post_id.removeprefix("t3_")
    _print_comments(post_id, args.limit)


def _print_comments(post_id, limit):
    data = get(f"{BASE}/api/comments/search", {
        "link_id": post_id,
        "limit": COMMENT_FETCH_SIZE,
        "fields": COMMENT_FIELDS,
    })
    comments = data.get("data", [])
    if not comments:
        print("*No comments found.*")
        return
    top, total_valid = top_comments(comments, limit)
    fetched = len(comments)
    print(f"---\n### Top {len(top)} Comments (fetched {fetched}, {total_valid} non-deleted, sorted by score)\n")
    for block in top:
        print(block)
        print()


def cmd_browse(args):
    data = get(f"{BASE}/api/posts/search", {
        "subreddit": args.subreddit,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    })
    posts = data.get("data", [])
    if not posts:
        print(f"No posts found in r/{args.subreddit}")
        return
    print(f"# r/{args.subreddit} — {len(posts)} recent posts\n")
    for p in posts:
        _print_post_digest(p)


def cmd_search(args):
    data = get(f"{BASE}/api/posts/search", {
        "subreddit": args.subreddit,
        "query": args.keywords,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    })
    posts = data.get("data", [])
    if not posts:
        print(f"No posts found in r/{args.subreddit} matching '{args.keywords}'")
        return
    print(f"# Search: '{args.keywords}' in r/{args.subreddit} — {len(posts)} results\n")
    for p in posts:
        _print_post_digest(p)


def _print_post_digest(p):
    flair = f" [{p['link_flair_text']}]" if p.get("link_flair_text") else ""
    body = (p.get("selftext") or "").strip()
    preview = ""
    if body and body not in ("[deleted]", "[removed]"):
        snippet = body[:200].replace("\n", " ")
        preview = f"\n  > {snippet}{'…' if len(body) > 200 else ''}"
    permalink = p.get("permalink") or f"/r/{p['subreddit']}/comments/{p['id']}/"
    print(f"- **{p['title']}**{flair} | u/{p['author']} | ↑{p['score']} | {p['num_comments']} comments | {fmt_date(p['created_utc'])}")
    print(f"  `{p['id']}` — https://reddit.com{permalink}{preview}")
    print()


def cmd_user(args):
    print(f"# u/{args.username} — Recent activity\n")

    posts = get(f"{BASE}/api/posts/search", {
        "author": args.username,
        "sort": "desc",
        "limit": args.limit,
        "fields": SEARCH_FIELDS,
    }).get("data", [])
    if posts:
        print(f"## Posts ({len(posts)})\n")
        for p in posts:
            permalink = p.get("permalink") or f"/r/{p['subreddit']}/comments/{p['id']}/"
            print(f"- **{p['title']}** in r/{p['subreddit']} | ↑{p['score']} | {fmt_date(p['created_utc'])}")
            print(f"  `{p['id']}` — https://reddit.com{permalink}")
            print()

    comments = get(f"{BASE}/api/comments/search", {
        "author": args.username,
        "sort": "desc",
        "limit": args.limit,
        "fields": COMMENT_FIELDS,
    }).get("data", [])
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

# ── Argument parsing ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Reddit content via Arctic Shift")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_post = sub.add_parser("post", help="Fetch a post by ID")
    p_post.add_argument("post_id")
    p_post.add_argument("--comments", type=int, metavar="N",
                        help="Also fetch top N comments")

    p_comments = sub.add_parser("comments", help="Fetch top N comments for a post")
    p_comments.add_argument("post_id")
    p_comments.add_argument("--limit", type=int, default=DEFAULT_COMMENT_LIMIT,
                            help=f"Number of top comments (default: {DEFAULT_COMMENT_LIMIT})")

    p_browse = sub.add_parser("browse", help="Browse recent posts in a subreddit")
    p_browse.add_argument("subreddit")
    p_browse.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                          help=f"Number of posts (default: {DEFAULT_POST_LIMIT})")

    p_search = sub.add_parser("search", help="Search posts by keyword in a subreddit")
    p_search.add_argument("subreddit")
    p_search.add_argument("keywords")
    p_search.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                          help=f"Number of results (default: {DEFAULT_POST_LIMIT})")

    p_user = sub.add_parser("user", help="Fetch a user's recent posts and comments")
    p_user.add_argument("username")
    p_user.add_argument("--limit", type=int, default=DEFAULT_POST_LIMIT,
                        help=f"Number of each (default: {DEFAULT_POST_LIMIT})")

    args = parser.parse_args()
    {"post": cmd_post, "comments": cmd_comments, "browse": cmd_browse,
     "search": cmd_search, "user": cmd_user}[args.cmd](args)


if __name__ == "__main__":
    main()

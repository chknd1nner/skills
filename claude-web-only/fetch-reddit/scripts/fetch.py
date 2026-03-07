#!/usr/bin/env python3
"""
Reddit content fetcher via Redlib (real-time).
Returns clean markdown formatted for LLM ingestion.

Commands:
  python fetch.py live-browse SUBREDDIT [--sort hot|new|rising|top]
  python fetch.py live-post POST_ID [--comments N]
  python fetch.py live-comments POST_ID [--limit N]
"""

import sys
import json
import argparse
import hashlib
import re as _re
import subprocess
from datetime import datetime, timezone

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "beautifulsoup4", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    from bs4 import BeautifulSoup

try:
    import requests
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "requests", "--break-system-packages", "-q"],
        capture_output=True, text=True
    )
    import requests

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_COMMENT_LIMIT = 20  # return this many to LLM unless --limit passed

REDLIB_INSTANCES = [
    "https://redlib.freedit.eu",
]

REDLIB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_instances_fetched = False


def fetch_redlib_instances():
    """Fetch current Redlib instance list from the official registry. Returns URL list or None on error."""
    try:
        r = requests.get(
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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

    session = requests.Session()
    session.headers['User-Agent'] = REDLIB_UA

    errors = []
    for base in get_redlib_instances():
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

    print("ERROR: All Redlib instances failed:", file=sys.stderr)
    for err in errors:
        print(f"  {err}", file=sys.stderr)
    sys.exit(1)


def parse_redlib_posts(soup):
    """Parse post listing from Redlib HTML. Returns list of post dicts."""
    posts_div = soup.select_one("div#posts")
    if not posts_div:
        return []

    results = []
    for el in posts_div.select("div.post"):
        post = {}
        post["id"] = el.get("id", "")

        title_el = el.select_one("h2.post_title")
        if title_el:
            title_link = title_el.select_one("a:not(.post_flair)[href]")
            post["title"] = title_link.get_text(strip=True) if title_link else title_el.get_text(strip=True)
            post["permalink"] = title_link["href"] if title_link else ""
        else:
            continue  # skip posts without titles

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

        comments_el = el.select_one("a.post_comments")
        if comments_el and comments_el.get("title"):
            try:
                post["num_comments"] = int(comments_el["title"].split()[0])
            except (ValueError, IndexError):
                post["num_comments"] = 0
        else:
            post["num_comments"] = 0

        flair_el = el.select_one("a.post_flair")
        post["link_flair_text"] = flair_el.get_text(strip=True) if flair_el else ""

        time_el = el.select_one("span.created")
        post["time_relative"] = time_el.get_text(strip=True) if time_el else ""
        post["time_absolute"] = time_el.get("title", "") if time_el else ""

        post["over_18"] = bool(el.select_one("small.nsfw"))
        post["spoiler"] = bool(el.select_one("small.spoiler"))
        post["stickied"] = "stickied" in el.get("class", [])

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

    title_el = el.select_one("h1.post_title")
    if title_el:
        # Remove flair/nsfw/spoiler tags to get clean title
        for tag in title_el.select("a.post_flair, small.nsfw, small.spoiler"):
            tag.decompose()
        post["title"] = title_el.get_text(strip=True)
    else:
        post["title"] = "[untitled]"

    flair_el = el.select_one("a.post_flair")
    post["link_flair_text"] = flair_el.get_text(strip=True) if flair_el else ""

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

    count_el = soup.select_one("p#comment_count")
    if count_el:
        try:
            post["num_comments"] = int(count_el.get_text(strip=True).split()[0])
        except (ValueError, IndexError):
            post["num_comments"] = 0
    else:
        post["num_comments"] = 0

    time_el = el.select_one("span.created")
    post["time_relative"] = time_el.get_text(strip=True) if time_el else ""
    post["time_absolute"] = time_el.get("title", "") if time_el else ""

    post["over_18"] = bool(el.select_one("small.nsfw"))
    post["spoiler"] = bool(el.select_one("small.spoiler"))
    post["locked"] = False  # Not reliably detectable from Redlib HTML

    body_el = el.select_one("div.post_body")
    if body_el and "post_preview" not in body_el.get("class", []):
        post["body"] = body_el.get_text(separator="\n", strip=True)
    else:
        post["body"] = ""

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


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_live_browse(args):
    sort = args.sort or "hot"
    path = f"/r/{args.subreddit}/{sort}"
    soup, base_url = redlib_get(path)
    posts = parse_redlib_posts(soup)
    if not posts:
        page_title = soup.find("title")
        title_text = page_title.get_text(strip=True) if page_title else "unknown"
        print(f"No posts found in r/{args.subreddit}. Page title was: '{title_text}'.")
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


def cmd_live_post(args):
    post_id = args.post_id.removeprefix("t3_")
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


def cmd_live_comments(args):
    post_id = args.post_id.removeprefix("t3_")
    path = f"/comments/{post_id}"
    soup, base_url = redlib_get(path)
    comments, total = parse_redlib_comments(soup, args.limit)
    if not comments:
        page_title = soup.find("title")
        title_text = page_title.get_text(strip=True) if page_title else "unknown"
        print(f"No comments found for post {post_id}. Page title was: '{title_text}'.")
        return
    print(f"---\n### Top {len(comments)} Comments (from {total} parsed, sorted by score) — live via Redlib\n")
    for block in comments:
        print(block)
        print()


# ── Argument parsing ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Reddit content via Redlib")
    sub = parser.add_subparsers(dest="cmd", required=True)

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

    args = parser.parse_args()
    {
        "live-browse": cmd_live_browse,
        "live-post": cmd_live_post,
        "live-comments": cmd_live_comments,
    }[args.cmd](args)


if __name__ == "__main__":
    main()

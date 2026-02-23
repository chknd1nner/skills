# Posts and Comments

Fetch individual posts and their comment threads. Both archive (Arctic Shift) and live (Redlib) versions are available.

## Fetching a post

### Archive (Arctic Shift)

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post POST_ID [--comments N]
```

Returns the full post with title, author, score, body text, URL, and metadata. Optionally includes top N comments sorted by score.

### Live (Redlib)

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID [--comments N]
```

Same output format but with real-time scores and current content.

### When to use which

| Situation | Command |
|---|---|
| Post is > 36 hours old | `post` (archive) |
| Want current score/vote count | `live-post` |
| Post may have been edited recently | `live-post` |
| Need reliable structured data | `post` (archive) |

## Fetching comments standalone

### Archive (Arctic Shift)

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py comments POST_ID [--limit N]
```

Fetches up to 100 comments from the API, sorts by score descending, returns the top N (default: 20).

### Live (Redlib)

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID [--limit N]
```

Parses the full comment tree from Redlib HTML, preserving reply depth. Sorts by score, returns top N.

## Extracting post IDs from URLs

Post IDs are the alphanumeric segment after `/comments/` in a Reddit URL:

```
https://reddit.com/r/ClaudeAI/comments/1r7vovv/some_title_here/
                                        ^^^^^^^^
                                        POST_ID = 1r7vovv
```

The script also accepts the `t3_` prefix and strips it automatically:
```bash
# Both work
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post 1r7vovv
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post t3_1r7vovv
```

## Comment sorting behavior

Both archive and live comment fetching use the same approach:
1. Fetch a batch of comments (archive: 100 from API; live: all visible on page)
2. Filter out `[deleted]` and `[removed]` comments
3. Sort by score descending
4. Return the top N

This means you get the highest-quality comments regardless of their position in the thread. Increase `--limit` for busy threads where you want more breadth.

## Examples

```bash
# Quick read of a post
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post 1r7vovv

# Post with discussion
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py post 1r7vovv --comments 20

# Just the comments, more of them
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py comments 1r7vovv --limit 40

# Live version with current scores
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv --comments 20
```

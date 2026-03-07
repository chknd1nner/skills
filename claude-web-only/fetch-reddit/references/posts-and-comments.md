# Posts and Comments

Fetch individual posts and their comment threads via Redlib (real-time).

## Fetching a post

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post POST_ID [--comments N]
```

Returns the post with title, author, score, comment count, upvote ratio, body text, and optionally top N comments.

## Fetching comments standalone

```bash
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments POST_ID [--limit N]
```

Parses the full comment tree from Redlib HTML, preserving reply depth. Sorts by score, returns top N (default: 20).

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
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post t3_1r7vovv
```

## Comment sorting behavior

1. Fetch all comments visible on the Redlib page
2. Filter out `[deleted]` and `[removed]` comments
3. Sort by score descending
4. Return the top N

This means you get the highest-quality comments regardless of their position in the thread. Increase `--limit` for busy threads where you want more breadth.

## Examples

```bash
# Post only
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv

# Post with top 20 comments
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-post 1r7vovv --comments 20

# Just the comments, more of them
python3 /mnt/skills/user/fetch-reddit/scripts/fetch.py live-comments 1r7vovv --limit 40
```

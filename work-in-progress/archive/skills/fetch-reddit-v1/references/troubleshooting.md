# Troubleshooting

Use these to diagnose failures and give the user a specific, actionable response — not a generic "something went wrong".

## Dependency install failures

### `curl_cffi` install fails with 403 or connection error

**Cause:** Network egress is completely disabled — not just domain-restricted. PyPI is included in the default "Package managers only" allowlist, so a failure here means the egress toggle is off entirely.

**Tell the user:**
> "The `curl_cffi` install failed — since PyPI is accessible by default when network egress is on, this usually means the egress toggle is off entirely. Please check Settings → Capabilities and confirm 'Allow network egress' is turned on. Start a new chat after enabling it."

### `beautifulsoup4` or `requests` install fails

**Cause:** Same as above — network egress is off. These packages are on PyPI and should install fine when egress is enabled.

**Tell the user:**
> "The dependency install failed. Please check Settings → Capabilities and confirm 'Allow network egress' is turned on."

## Arctic Shift API errors

### Connection error to Arctic Shift

**Cause:** The domain allowlist is set to "Package managers only", which excludes `arctic-shift.photon-reddit.com`. The script can install packages but not reach the API.

**Tell the user:**
> "I can reach PyPI but not the Arctic Shift API — this means network egress is on but the domain allowlist is set to 'Package managers only', which blocks external APIs. Please go to Settings → Capabilities → Allow network egress → Domain allowlist and either select 'All domains', or choose 'Package managers + specific domains' and add `arctic-shift.photon-reddit.com`. Start a new chat once changed."

### Empty results from Arctic Shift

Distinguish between these cases:
- **Very new posts (< 36h):** Normal — Arctic Shift has indexing lag. Suggest using `live-browse` or `live-post` instead.
- **Score/comment count shows 1/0:** Normal for fresh content. The post exists but metrics haven't been updated.
- **Private or banned subreddit:** API returns empty with no error. Tell the user the subreddit may be private or not exist.
- **Misspelled subreddit/username:** Check for typos.

## Redlib errors

### "All Redlib instances failed"

**Cause:** Every instance in the failover list is down, blocked, or returning errors. The error output lists each instance and its failure reason.

**Tell the user:**
> "All Redlib instances are currently unavailable. This can happen when instances go down temporarily. You can try again later, or use the archive commands (`browse`, `search`, `post`, `comments`) which use Arctic Shift instead — these work for content older than ~36 hours."

### "Anubis challenge format may have changed"

**Cause:** The Anubis PoW protection has been updated and the solver can't parse the new format.

**Tell the user:**
> "The Anubis proof-of-work challenge format has changed since this skill was last updated. Live commands (`live-browse`, `live-post`, `live-comments`) won't work until the solver is updated. Archive commands still work normally for content older than ~36 hours."

### "Redlib HTML may have changed"

**Cause:** Redlib updated their HTML structure and the parsers can't find expected elements.

**Tell the user:**
> "Redlib's HTML format has changed and the parser can't extract post data. Use archive commands (`browse`, `search`, `post`) as a fallback — these work for content older than ~36 hours."

### Connection errors to specific Redlib instances

The script automatically fails over to the next instance. You'll only see an error if all instances fail. Common per-instance failures:
- TLS/SSL errors — instance has certificate issues
- 502/503 — instance is overloaded or down
- Cloudflare challenge — instance is behind additional protection
- Timeout — instance is slow to respond

### Redlib returns a page but posts are empty, or page title is an error message

**Cause:** The Redlib instance loaded successfully (Anubis solved, cookie set) but Reddit's API rejected that instance's requests. Redlib serves its own error page as HTTP 200 — common titles: "Backend temporarily unavailable. Retrying..." or "Error: Failed to parse page JSON data".

The script now detects these and skips to the next instance. If all instances show this error, Reddit is throttling all currently-known Redlib instance IPs.

**Tell the user:**
> "All Redlib instances are currently being blocked by Reddit's API. This happens periodically as Reddit tightens its crackdown on alternative frontends. Archive commands (`browse`, `search`, `post`, `comments`) still work via Arctic Shift for content older than ~36 hours."

### Warning: Could not refresh Redlib instance list from GitHub

**Cause:** The request to `raw.githubusercontent.com` timed out or failed. The script falls back to its bundled instance list automatically — live commands will still work if the bundled instances are up.

**If you see this warning repeatedly:**
> "The skill couldn't reach GitHub to refresh the Redlib instance list and is using a potentially stale fallback. Check that `raw.githubusercontent.com` is accessible under your domain allowlist settings."

## Free tier limitations

Free tier users may only have access to "Package managers only" and cannot add external domains.

**Tell the user:**
> "This skill needs access to external APIs which requires your domain allowlist to be set beyond 'Package managers only'. Free tier may not support this — check Settings → Capabilities to see what options are available to you, or refer to the [network egress documentation](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)."

Do not attempt to run the script until confirmed.

## General debugging

If the script produces unexpected output:
1. Check the error message — the script provides specific diagnostics
2. Try the archive version of the command if a live command fails (or vice versa)
3. Verify the subreddit name or post ID is correct
4. Check if the subreddit is private, quarantined, or banned

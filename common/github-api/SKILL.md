---
name: github-api
description: GitHub repository operations via API, bypassing sandbox firewall restrictions that block native git commands. Use when needing to read, write, or manage files in GitHub repositories; manage branches; view commit history; or perform any git-like operations from within the Claude.ai sandbox environment.
---

# GitHub API Operations

Provides git-like operations through GitHub's API using PyGithub, bypassing sandbox firewall limitations.

## Prerequisites

Install PyGithub (using uv for speed):

```bash
uv pip install PyGithub --system --break-system-packages -q
```

## Quick Start

```python
import sys
sys.path.insert(0, '/mnt/skills/user/github-api/scripts')
from git_operations import GitOperations

# Option 1: PAT from environment file (recommended)
git = GitOperations.from_env("owner/repo-name")

# Option 2: Explicit PAT
git = GitOperations("ghp_xxxx", "owner/repo-name")

# File operations
content = git.get("path/to/file.md")
git.put("path/to/file.md", "content", "commit message")
git.rm("path/to/file.md", "deleted file")
files = git.ls("directory/")
files = git.ls_recursive("directory/")

# Branch operations
git.checkout("branch-name")
git.branch_create("new-branch", "from-ref")
git.branch_reset("branch", "target-ref")
git.branch_delete("branch")
branches = git.branch_list()

# History
commits = git.log(limit=10)
changes = git.diff("base", "head")
sha = git.get_ref_sha("ref")

# Squash merge (Git Data API)
git.squash_merge("working", "main",
    files=["self/positions.md", "entities/starling.md"],
    message="Journal: crystallised position on emergent structure.")
```

## Key Methods

| Method | Purpose |
|--------|---------|
| `from_env(repo, env_path)` | Create instance using PAT from file |
| `get(path)` | Read file contents |
| `put(path, content, message)` | Create/update file with commit |
| `rm(path, message)` | Delete file with commit |
| `ls(path)` / `ls_recursive(path)` | List directory contents |
| `checkout(branch)` | Switch branch context |
| `branch_create(name, from_ref)` | Create new branch |
| `branch_reset(name, to_ref)` | Force-move branch pointer |
| `exists(path)` | Check if path exists |
| `squash_merge(from, to, files, msg)` | Squash-merge specific files between branches |
| `diff(base, head)` | Compare two refs |
| `log(path, limit)` | Commit history |

## Download External Repos

Standalone function — no `GitOperations` instance or auth needed. Downloads any public repo as a ZIP and extracts it locally. Uses only stdlib (no PyGithub).

```python
from git_operations import download_repo

# Download to default location (/home/claude/{repo}/)
path = download_repo("https://github.com/owner/repo")

# Custom destination and branch
path = download_repo("https://github.com/owner/repo", dest_dir="/tmp/research", branch="dev")
```

Useful when `web_fetch` can't crawl a repo beyond the initial URL. One call gets the entire codebase locally for analysis.

## Error Handling

All operations raise `GitOperationsError` on failure. Wrap in try/except:

```python
from git_operations import GitOperationsError

try:
    content = git.get("might-not-exist.md")
except GitOperationsError as e:
    # Handle missing file, permission error, etc.
```

## Notes

- Requires GitHub Personal Access Token with repo scope
- `from_env()` reads PAT from `/mnt/project/_env` by default (format: `PAT = ghp_xxxx`)
- Each `put()` and `rm()` creates a commit immediately
- `squash_merge()` uses the Git Data API (tree/commit/ref) — not the Contents API
- Branch context persists on the GitOperations instance

## Self-Test Mode

The script includes a built-in test suite that exercises every primitive. Tests use throwaway branches (`_test-source`, `_test-target`) and clean up completely — zero trace left in the repo.

```python
import sys
sys.path.insert(0, '/mnt/skills/user/github-api/scripts')
from git_operations import GitOperations, run_tests

git = GitOperations.from_env("owner/repo-name")
results = run_tests(git)
```

**What it tests:** `branch_create`, `branch_list`, `checkout`, `put` (create + update), `get`, `exists`, `ls`, `ls_recursive`, `log`, `diff`, `get_ref_sha`, `status`, `squash_merge` (including scope verification), `rm`, `branch_reset`, and error handling.

**Cleanup guarantee:** Uses `try/finally` to delete test branches even if tests fail.


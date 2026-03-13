#!/usr/bin/env python3
"""
GitOperations - GitHub API wrapper with git CLI-like semantics.
Bypasses sandbox firewall by using GitHub REST API instead of git protocol.
"""

import json
import os
import time
import zipfile
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from github import Github, Auth, GithubException, InputGitTreeElement
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileInfo:
    name: str
    path: str
    type: str  # 'file' or 'dir'
    size: Optional[int] = None
    sha: Optional[str] = None


@dataclass
class CommitInfo:
    sha: str
    message: str
    author: str
    date: str


class GitOperationsError(Exception):
    """Raised when a git operation fails."""
    pass


class GitOperations:
    """
    Git-like operations via GitHub API.
    Maintains current branch context like a working directory.
    """
    
    def __init__(self, token: str, repo_name: str, branch: str = "main"):
        self.repo_name = repo_name
        self.branch = branch
        self._github = Github(auth=Auth.Token(token))
        self._repo = self._github.get_repo(repo_name)
    
    @classmethod
    def from_env(
        cls, 
        repo: str, 
        env_path: str = "/mnt/project/_env",
        branch: str = "main"
    ) -> "GitOperations":
        """
        Create GitOperations using PAT from environment file.
        
        Args:
            repo: GitHub repository (owner/name)
            env_path: Path to file containing 'PAT = <token>'
            branch: Initial branch (default: main)
            
        Returns:
            Configured GitOperations instance
            
        Example:
            git = GitOperations.from_env("owner/repo")
            content = git.get("README.md")
        """
        with open(env_path) as f:
            for line in f.read().strip().split('\n'):
                if line.startswith('PAT'):
                    token = line.split('=', 1)[1].strip()
                    return cls(token, repo, branch)
        raise ValueError(f"PAT not found in {env_path}")
    
    # === Internal: Consistency Retry ===
    
    def _retry_on_consistency_delay(
        self, fn, max_retries: int = 5, initial_delay: float = 0.2
    ):
        """
        Retry a function with exponential backoff for GitHub API
        eventual consistency. After mutations (put/rm), reads may
        briefly return 404 before the change propagates.
        """
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                return fn()
            except GithubException as e:
                if e.status == 404 and attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
    
    # === File Operations ===
    
    def get(self, path: str) -> str:
        """Read file contents. Retries on 404 for eventual consistency."""
        try:
            contents = self._retry_on_consistency_delay(
                lambda: self._repo.get_contents(path, ref=self.branch)
            )
            if isinstance(contents, list):
                raise GitOperationsError(f"Path '{path}' is a directory")
            return contents.decoded_content.decode('utf-8')
        except GithubException as e:
            if e.status == 404:
                raise GitOperationsError(f"File not found: {path}")
            raise GitOperationsError(f"Failed to get '{path}': {e}")
    
    def put(self, path: str, content: str, message: str) -> str:
        """Create or update file. Returns commit SHA."""
        try:
            existing = self._repo.get_contents(path, ref=self.branch)
            result = self._repo.update_file(
                path=path, message=message, content=content,
                sha=existing.sha, branch=self.branch
            )
        except GithubException as e:
            if e.status == 404:
                result = self._repo.create_file(
                    path=path, message=message, content=content,
                    branch=self.branch
                )
            else:
                raise GitOperationsError(f"Failed to put '{path}': {e}")
        return result['commit'].sha
    
    def rm(self, path: str, message: str) -> bool:
        """Delete file. Returns True on success."""
        try:
            contents = self._repo.get_contents(path, ref=self.branch)
            self._repo.delete_file(
                path=path, message=message,
                sha=contents.sha, branch=self.branch
            )
            return True
        except GithubException as e:
            if e.status == 404:
                raise GitOperationsError(f"File not found: {path}")
            raise GitOperationsError(f"Failed to delete '{path}': {e}")
    
    def ls(self, path: str = "") -> list[FileInfo]:
        """List directory contents (one level)."""
        try:
            contents = self._repo.get_contents(path, ref=self.branch)
            if not isinstance(contents, list):
                contents = [contents]
            return [
                FileInfo(
                    name=item.name, path=item.path,
                    type='dir' if item.type == 'dir' else 'file',
                    size=item.size if item.type != 'dir' else None,
                    sha=item.sha
                )
                for item in contents
            ]
        except GithubException as e:
            if e.status == 404:
                raise GitOperationsError(f"Path not found: {path}")
            raise GitOperationsError(f"Failed to list '{path}': {e}")
    
    def ls_recursive(self, path: str = "") -> list[FileInfo]:
        """
        List all files recursively using a single API call (Git Tree).
        Much faster than walking directories — one request vs N.
        """
        try:
            branch_sha = self.get_ref_sha(self.branch)
            tree_data = self._repo.get_git_tree(branch_sha, recursive=True)

            result = []
            for item in tree_data.tree:
                if item.type != 'blob':
                    continue
                if path and not item.path.startswith(path if path.endswith('/') else path + '/'):
                    # Also include exact match (path itself is a file)
                    if item.path != path:
                        continue

                result.append(FileInfo(
                    name=item.path.split('/')[-1],
                    path=item.path,
                    type='file',
                    size=item.size,
                    sha=item.sha
                ))
            return result
        except GithubException as e:
            raise GitOperationsError(f"Failed to list recursive '{path}': {e}")
    
    def exists(self, path: str) -> bool:
        """Check if path exists. Retries for eventual consistency."""
        try:
            self._retry_on_consistency_delay(
                lambda: self._repo.get_contents(path, ref=self.branch)
            )
            return True
        except GithubException:
            return False
    
    # === Branch Operations ===
    
    def checkout(self, branch: str) -> None:
        """Switch branch context."""
        try:
            self._repo.get_branch(branch)
            self.branch = branch
        except GithubException:
            raise GitOperationsError(f"Branch not found: {branch}")
    
    def branch_list(self) -> list[str]:
        """List all branches."""
        return [b.name for b in self._repo.get_branches()]
    
    def branch_create(self, name: str, from_ref: Optional[str] = None) -> str:
        """Create branch from ref (default: current branch). Returns SHA."""
        sha = self.get_ref_sha(from_ref or self.branch)
        try:
            self._repo.create_git_ref(ref=f"refs/heads/{name}", sha=sha)
            return sha
        except GithubException as e:
            if "Reference already exists" in str(e):
                raise GitOperationsError(f"Branch already exists: {name}")
            raise GitOperationsError(f"Failed to create branch '{name}': {e}")
    
    def branch_delete(self, name: str) -> bool:
        """Delete branch. Cannot delete current branch."""
        if name == self.branch:
            raise GitOperationsError(f"Cannot delete current branch: {name}")
        try:
            self._repo.get_git_ref(f"heads/{name}").delete()
            return True
        except GithubException as e:
            if e.status == 404:
                raise GitOperationsError(f"Branch not found: {name}")
            raise GitOperationsError(f"Failed to delete branch '{name}': {e}")
    
    def branch_reset(self, name: str, to_ref: str) -> str:
        """Force-move branch to point at ref. Returns new SHA."""
        target_sha = self.get_ref_sha(to_ref)
        try:
            self._repo.get_git_ref(f"heads/{name}").edit(sha=target_sha, force=True)
            return target_sha
        except GithubException as e:
            if e.status == 404:
                raise GitOperationsError(f"Branch not found: {name}")
            raise GitOperationsError(f"Failed to reset '{name}': {e}")
    
    # === History ===
    
    def log(self, path: Optional[str] = None, limit: int = 10) -> list[CommitInfo]:
        """Get commit history, optionally filtered by path."""
        kwargs = {'sha': self.branch}
        if path:
            kwargs['path'] = path
        commits = self._repo.get_commits(**kwargs)
        return [
            CommitInfo(
                sha=c.sha[:7],
                message=c.commit.message.split('\n')[0],
                author=c.commit.author.name,
                date=c.commit.author.date.isoformat()
            )
            for i, c in enumerate(commits) if i < limit
        ]
    
    def diff(self, base: str, head: str) -> list[dict]:
        """Compare two refs. Returns list of changed files."""
        try:
            comparison = self._repo.compare(base, head)
            return [
                {
                    'filename': f.filename,
                    'status': f.status,
                    'additions': f.additions,
                    'deletions': f.deletions,
                    'patch': getattr(f, 'patch', None)
                }
                for f in comparison.files
            ]
        except GithubException as e:
            raise GitOperationsError(f"Failed to diff '{base}..{head}': {e}")
    
    def get_ref_sha(self, ref: str) -> str:
        """Get SHA that ref points to."""
        try:
            return self._repo.get_branch(ref).commit.sha
        except GithubException:
            pass
        try:
            return self._repo.get_commit(ref).sha
        except GithubException:
            pass
        raise GitOperationsError(f"Ref not found: {ref}")
    
    # === Squash Merge ===

    def squash_merge(
        self,
        from_branch: str,
        to_branch: str,
        files: list[str],
        message: str
    ) -> str:
        """
        Squash-merge specific files from one branch onto another.

        Creates a new commit on to_branch whose tree is to_branch's current
        tree with the specified files replaced by their from_branch versions.
        The from_branch is NOT reset — it naturally converges as files are
        merged.

        Args:
            from_branch: Source branch (e.g. 'working')
            to_branch:   Target branch (e.g. 'main')
            files:       File paths to merge (e.g. ['self/positions.md'])
            message:     Commit message (the journal entry)

        Returns:
            SHA of the new squash commit on to_branch

        Example:
            git.squash_merge('working', 'main',
                files=['self/positions.md', 'entities/starling.md'],
                message='Journal: landed on emergent structure position.')
        """
        if not files:
            raise GitOperationsError("No files specified for squash merge")

        try:
            # Get current to_branch state
            to_ref = self._repo.get_git_ref(f'heads/{to_branch}')
            to_commit = self._repo.get_git_commit(to_ref.object.sha)
            to_tree = to_commit.tree

            # Read files directly from from_branch ref — no checkout needed
            tree_elements = []
            for file_path in files:
                try:
                    blob = self._repo.get_contents(file_path, ref=from_branch)
                    tree_elements.append(InputGitTreeElement(
                        path=file_path,
                        mode='100644',
                        type='blob',
                        content=blob.decoded_content.decode('utf-8')
                    ))
                except GithubException as e:
                    if e.status == 404:
                        raise GitOperationsError(
                            f"File not found on '{from_branch}': {file_path}"
                        )
                    raise

            # Create new tree layered on top of to_branch's tree
            new_tree = self._repo.create_git_tree(
                tree_elements, base_tree=to_tree
            )

            # Create squash commit on to_branch
            squash_commit = self._repo.create_git_commit(
                message=message,
                tree=new_tree,
                parents=[to_commit]
            )

            # Advance to_branch ref
            to_ref.edit(squash_commit.sha)

            return squash_commit.sha

        except GitOperationsError:
            raise
        except GithubException as e:
            raise GitOperationsError(f"Squash merge failed: {e}")

    # === Utility ===
    
    def status(self) -> dict:
        """Current repo/branch info."""
        return {
            'repo': self.repo_name,
            'branch': self.branch,
            'branches': self.branch_list()
        }
    
    def __repr__(self) -> str:
        return f"GitOperations({self.repo_name}, branch={self.branch})"


# =============================================================================
# STANDALONE UTILITIES (no GitOperations instance needed)
# =============================================================================

def download_repo(github_url: str, dest_dir: str = None, branch: str = None) -> str:
    """
    Download a public GitHub repo to a local directory.

    No auth needed, no PyGithub dependency — uses only stdlib.
    Downloads the repo as a ZIP archive and extracts it.

    Args:
        github_url: GitHub repo URL (e.g. "https://github.com/owner/repo")
        dest_dir:   Where to extract (default: /home/claude/{repo})
        branch:     Branch to download (default: auto-detect via API)

    Returns:
        Path to the extracted directory

    Example:
        path = download_repo("https://github.com/owner/repo")
        # Files are now at /home/claude/repo/
    """
    # Parse owner/repo from URL
    parts = urlparse(github_url.rstrip('/')).path.strip('/').split('/')
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {github_url}")
    owner, repo = parts[0], parts[1]

    if dest_dir is None:
        dest_dir = f"/home/claude/{repo}"

    # Detect default branch if not specified (1 unauthenticated API call)
    if branch is None:
        req = Request(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"User-Agent": "Python", "Accept": "application/vnd.github+json"}
        )
        with urlopen(req, timeout=30) as resp:
            branch = json.loads(resp.read())["default_branch"]
        print(f"Default branch: {branch}")

    # Download ZIP (does not count against API rate limit)
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
    print(f"Downloading {zip_url} ...")
    req = Request(zip_url, headers={"User-Agent": "Python"})
    with urlopen(req, timeout=300) as resp:
        data = resp.read()
    print(f"Downloaded {len(data) / 1024 / 1024:.1f} MB")

    # Extract, stripping the top-level wrapper directory
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        top = {name.split('/')[0] for name in zf.namelist()}
        prefix = top.pop() + '/' if len(top) == 1 else ''
        for member in zf.infolist():
            if prefix and member.filename.startswith(prefix):
                member.filename = member.filename[len(prefix):]
            if member.filename:
                zf.extract(member, dest_dir)

    print(f"Extracted to {dest_dir}")
    return dest_dir


# =============================================================================
# SELF-TEST
# =============================================================================

def run_tests(git: "GitOperations") -> dict:
    """
    Exercise every GitOperations primitive against throwaway test branches.
    
    Creates `_test-source` and `_test-target` branches, runs all operations,
    then deletes both branches — zero trace left in the repo.
    
    Args:
        git: A connected GitOperations instance
        
    Returns:
        dict with 'passed', 'failed', 'errors' counts and details
    """
    results = {'passed': 0, 'failed': 0, 'errors': [], 'tests': []}
    original_branch = git.branch
    
    # Track branches we create for guaranteed cleanup
    test_branches = []
    
    def record(name, passed, detail=""):
        results['tests'].append({'name': name, 'passed': passed, 'detail': detail})
        if passed:
            results['passed'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"{name}: {detail}")
    
    try:
        # === SETUP: Create test branches from main ===
        print("🔧 Setting up test branches...")
        main_sha = git.get_ref_sha('main')
        
        git.branch_create('_test-source', 'main')
        test_branches.append('_test-source')
        git.branch_create('_test-target', 'main')
        test_branches.append('_test-target')
        
        record('branch_create', True, 'Created _test-source and _test-target')
        
        # === TEST: branch_list ===
        print("📋 Testing branch_list...")
        branches = git.branch_list()
        ok = '_test-source' in branches and '_test-target' in branches
        record('branch_list', ok,
               f"Found test branches: {ok}")
        
        # === TEST: checkout ===
        print("🔀 Testing checkout...")
        git.checkout('_test-source')
        record('checkout', git.branch == '_test-source',
               f"Branch is now: {git.branch}")
        
        # === TEST: put (create) ===
        print("📝 Testing put (create file)...")
        sha = git.put('_test/hello.md', '# Hello\n\nTest content.\n',
                       'test: create file')
        record('put_create', len(sha) > 0, f"Commit SHA: {sha[:7]}")
        
        # === TEST: get ===
        print("📖 Testing get...")
        content = git.get('_test/hello.md')
        record('get', content == '# Hello\n\nTest content.\n',
               f"Content matches: {content == '# Hello\nTest content.\n' if len(content) < 50 else 'truncated'}")
        
        # === TEST: put (update) ===
        print("✏️  Testing put (update file)...")
        sha2 = git.put('_test/hello.md', '# Hello\n\nUpdated content.\n',
                        'test: update file')
        updated = git.get('_test/hello.md')
        record('put_update', 'Updated' in updated,
               f"Content updated: {'Updated' in updated}")
        
        # === TEST: exists ===
        print("❓ Testing exists...")
        record('exists_true', git.exists('_test/hello.md'),
               "Existing file returns True")
        record('exists_false', not git.exists('_test/nonexistent.md'),
               "Missing file returns False")
        
        # === TEST: ls ===
        print("📂 Testing ls...")
        items = git.ls('_test')
        names = [f.name for f in items]
        record('ls', 'hello.md' in names,
               f"Found: {names}")
        
        # === TEST: put a second file for ls_recursive ===
        git.put('_test/sub/nested.md', '# Nested\n', 'test: nested file')
        
        # === TEST: ls_recursive ===
        print("📂 Testing ls_recursive...")
        all_files = git.ls_recursive('_test')
        paths = [f.path for f in all_files]
        record('ls_recursive',
               '_test/hello.md' in paths and '_test/sub/nested.md' in paths,
               f"Found: {paths}")
        
        # === TEST: log ===
        print("📜 Testing log...")
        commits = git.log(limit=5)
        record('log', len(commits) > 0,
               f"Got {len(commits)} commits, latest: {commits[0].message[:50] if commits else 'none'}")
        
        # === TEST: diff ===
        print("🔍 Testing diff...")
        diff = git.diff('main', '_test-source')
        filenames = [f['filename'] for f in diff]
        record('diff',
               '_test/hello.md' in filenames,
               f"Changed files: {filenames}")
        
        # === TEST: get_ref_sha ===
        print("🔑 Testing get_ref_sha...")
        sha = git.get_ref_sha('_test-source')
        record('get_ref_sha', len(sha) == 40,
               f"SHA: {sha[:7]}...")
        
        # === TEST: status ===
        print("ℹ️  Testing status...")
        s = git.status()
        record('status',
               s['repo'] == git.repo_name and '_test-source' in s['branches'],
               f"Repo: {s['repo']}, branch: {s['branch']}")
        
        # === TEST: squash_merge ===
        print("🔀 Testing squash_merge...")
        # _test-source has files, _test-target doesn't — merge one file across
        squash_sha = git.squash_merge(
            from_branch='_test-source',
            to_branch='_test-target',
            files=['_test/hello.md'],
            message='test: squash merge hello.md'
        )
        
        # Verify: file should now exist on _test-target
        git.checkout('_test-target')
        try:
            merged_content = git.get('_test/hello.md')
            record('squash_merge', 'Updated' in merged_content,
                   f"Squash SHA: {squash_sha[:7]}, content merged correctly")
        except GitOperationsError:
            record('squash_merge', False, "File not found on target after merge")
        
        # Verify: nested file should NOT be on _test-target (wasn't in files list)
        not_merged = not git.exists('_test/sub/nested.md')
        record('squash_merge_scoped', not_merged,
               f"Unspecified file correctly excluded: {not_merged}")
        
        # === TEST: rm ===
        print("🗑️  Testing rm...")
        git.checkout('_test-source')
        deleted = git.rm('_test/sub/nested.md', 'test: delete nested')
        record('rm', deleted and not git.exists('_test/sub/nested.md'),
               f"Deleted: {deleted}")
        
        # === TEST: branch_reset ===
        print("⏪ Testing branch_reset...")
        new_sha = git.branch_reset('_test-target', main_sha)
        record('branch_reset', new_sha == main_sha,
               f"Reset to: {new_sha[:7]}")
        
        # === TEST: error handling ===
        print("⚠️  Testing error handling...")
        try:
            git.get('_test/definitely-not-here.md')
            record('error_get_missing', False, "Should have raised")
        except GitOperationsError:
            record('error_get_missing', True, "Correctly raised GitOperationsError")
        
        try:
            git.squash_merge('_test-source', '_test-target', [], 'empty')
            record('error_empty_squash', False, "Should have raised")
        except GitOperationsError:
            record('error_empty_squash', True, "Correctly rejected empty file list")
        
    except Exception as e:
        record('UNEXPECTED', False, f"{type(e).__name__}: {e}")
    
    finally:
        # === CLEANUP: Delete test branches, restore original state ===
        print("\n🧹 Cleaning up...")
        git.branch = original_branch  # Avoid "can't delete current branch" errors
        if git.branch in test_branches:
            git.branch = 'main'
        
        for branch_name in test_branches:
            try:
                git.branch_delete(branch_name)
                print(f"   Deleted {branch_name}")
            except GitOperationsError as e:
                print(f"   ⚠️  Failed to delete {branch_name}: {e}")
        
        git.branch = original_branch
    
    # === REPORT ===
    print(f"\n{'='*50}")
    print(f"Results: {results['passed']} passed, {results['failed']} failed")
    print(f"{'='*50}")
    
    if results['errors']:
        print("\n❌ Failures:")
        for err in results['errors']:
            print(f"   {err}")
    else:
        print("\n✅ All tests passed!")
    
    # Verify cleanup
    remaining = [b for b in git.branch_list() if b.startswith('_test-')]
    if remaining:
        print(f"\n⚠️  Test branches still exist: {remaining}")
    else:
        print("🧹 Cleanup complete — no test artifacts remain.")
    
    return results


if __name__ == '__main__':
    import sys
    
    # When run directly, expects env file path as argument or uses default
    env_path = sys.argv[1] if len(sys.argv) > 1 else '/mnt/project/_env'
    
    # Need MEMORY_REPO from env file
    repo = None
    with open(env_path) as f:
        for line in f.read().strip().split('\n'):
            if line.strip().startswith('MEMORY_REPO'):
                repo = line.split('=', 1)[1].strip()
    
    if not repo:
        print("Error: MEMORY_REPO not found in env file")
        sys.exit(1)
    
    git = GitOperations.from_env(repo, env_path)
    print(f"Connected to {git.repo_name} on branch '{git.branch}'")
    print()
    
    results = run_tests(git)
    sys.exit(0 if results['failed'] == 0 else 1)


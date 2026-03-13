#!/usr/bin/env python3
"""
MemorySystem v2.0 — Memory management layer built on GitOperations.

Three-space architecture (self, collaborator, entities) with:
- Squash-merge consolidation (working → main)
- Local file editing pattern (fetch → edit locally → commit from file)
- Flexible fetch modes (content, file, both)
- File-level scoped consolidation
- Entity management with manifest
- Self-modifying config

Usage:
    from memory_system import connect

    memory = connect()
    info = memory.status()

    # Fetch (read with flexible return modes)
    content = memory.fetch('self/positions', return_mode='content')
    memory.fetch('self/positions', return_mode='file')  # saves to /mnt/home/
    content = memory.fetch('self/positions', return_mode='both')

    # Commit (write from local file or content string)
    memory.commit('self/positions',
        from_file='/mnt/home/self/positions.md',
        message='forming view on emergent design')

    # Consolidate (squash merge specific files)
    memory.consolidate(
        files=['self/positions', 'entities/starling'],
        message='Journal: landed on emergent structure position.')

    # Entity management
    memory.create_entity('starling', type='person',
        tags=['companion-guide', 'methodology'],
        summary='Creator of Claude Companion Guide.')

    # Config mutation
    memory.add_category('self', 'architecture',
        template='self-architecture.yaml')

    # If you need the underlying GitOperations:
    git, memory = connect(return_git=True)
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Union, Tuple, List
from git_operations import GitOperations, GitOperationsError


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class SpaceConfig:
    """Configuration for a single space (self, collaborator, or entities)."""
    retrieval: str = 'pre-injected'        # 'pre-injected' or 'on-demand'
    max_categories: int = 7
    categories: List[dict] = field(default_factory=list)  # [{name, template}]
    template: Optional[str] = None          # for entities (single shared template)


@dataclass
class MemoryConfig:
    """Memory system configuration loaded from _config.yaml."""
    spaces: dict = field(default_factory=dict)  # space_name → SpaceConfig

    @classmethod
    def from_yaml(cls, yaml_content: str) -> 'MemoryConfig':
        """
        Parse _config.yaml using regex (no pyyaml dependency).

        Supports the specific three-space format defined in v2.0.
        """
        config = cls()

        # Split into space blocks by finding top-level space names under 'spaces:'
        # Pattern: lines like "  self:" or "  collaborator:" or "  entities:"
        space_pattern = re.compile(
            r'^  (\w+):\s*\n((?:    .*\n)*)',
            re.MULTILINE
        )

        spaces_section = yaml_content.split('spaces:', 1)
        if len(spaces_section) < 2:
            return config

        for match in space_pattern.finditer(spaces_section[1]):
            space_name = match.group(1)
            block = match.group(2)

            space = SpaceConfig()

            # Parse retrieval mode
            ret_match = re.search(r'retrieval:\s*(\S+)', block)
            if ret_match:
                space.retrieval = ret_match.group(1)

            # Parse max_categories
            max_match = re.search(r'max_categories:\s*(\d+)', block)
            if max_match:
                space.max_categories = int(max_match.group(1))

            # Parse template (for entities — single template, no category list)
            tmpl_match = re.search(r'^\s{4}template:\s*(\S+)', block, re.MULTILINE)
            if tmpl_match:
                space.template = tmpl_match.group(1)

            # Parse categories list
            # Match categories by name alone; template is optional
            cat_pattern = re.compile(
                r'-\s*name:\s*(\S+)',
                re.MULTILINE
            )
            for cat_match in cat_pattern.finditer(block):
                name = cat_match.group(1)
                # Look for an optional template on the next line
                rest = block[cat_match.end():]
                tmpl_inline = re.match(r'\s*\n\s*template:\s*(\S+)', rest)
                template = tmpl_inline.group(1) if tmpl_inline else name
                space.categories.append({
                    'name': name,
                    'template': template,
                })

            config.spaces[space_name] = space

        return config

    @classmethod
    def default(cls) -> 'MemoryConfig':
        """Return default configuration if no _config.yaml exists."""
        return cls(spaces={
            'self': SpaceConfig(
                retrieval='pre-injected',
                max_categories=7,
                categories=[
                    {'name': 'positions', 'template': 'self-positions.yaml'},
                    {'name': 'methods', 'template': 'self-methods.yaml'},
                    {'name': 'interests', 'template': 'self-interests.yaml'},
                    {'name': 'open-questions', 'template': 'self-open-questions.yaml'},
                ]
            ),
            'collaborator': SpaceConfig(
                retrieval='pre-injected',
                max_categories=7,
                categories=[
                    {'name': 'profile', 'template': 'collaborator-profile.yaml'},
                ]
            ),
            'entities': SpaceConfig(
                retrieval='on-demand',
                template='entity.yaml',
                categories=[]
            ),
        })

    def get_category_names(self, space: str) -> List[str]:
        """Get category names for a space."""
        if space not in self.spaces:
            return []
        return [c['name'] for c in self.spaces[space].categories]

    def has_category(self, space: str, name: str) -> bool:
        """Check if a category exists in a space."""
        return name in self.get_category_names(space)

    def to_yaml(self) -> str:
        """Serialize config back to YAML string."""
        lines = ['# _config.yaml', '', 'spaces:']
        for space_name, space in self.spaces.items():
            lines.append(f'  {space_name}:')
            lines.append(f'    retrieval: {space.retrieval}')
            lines.append(f'    max_categories: {space.max_categories}')
            if space.template:
                lines.append(f'    template: {space.template}')
            if space.categories:
                lines.append('    categories:')
                for cat in space.categories:
                    lines.append(f'      - name: {cat["name"]}')
                    lines.append(f'        template: {cat["template"]}')
            if space_name == 'entities' and not space.categories:
                lines.append('    # No category list — entities are filesystem-discovered')
            lines.append('')
        return '\n'.join(lines)


# =============================================================================
# CONNECTION HELPER
# =============================================================================

def connect(
    env_path: str = "/mnt/project/_env",
    return_git: bool = False
) -> Union["MemorySystem", Tuple[GitOperations, "MemorySystem"]]:
    """
    Connect to the memory repository.

    Reads MEMORY_REPO and PAT from environment file. Loads _config.yaml
    from the repo. Creates the 'working' branch from 'main' if it doesn't
    exist (first-use bootstrap).

    Args:
        env_path: Path to env file containing MEMORY_REPO and PAT.
        return_git: If True, returns (GitOperations, MemorySystem) tuple.

    Returns:
        MemorySystem instance, or (GitOperations, MemorySystem) tuple.

    Environment file format:
        PAT = ghp_xxxx
        MEMORY_REPO = owner/repo-name
    """
    # Parse env file
    env = {}
    with open(env_path) as f:
        for line in f.read().strip().split('\n'):
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()

    repo = env.get('MEMORY_REPO')
    if not repo:
        raise ValueError(f"MEMORY_REPO not found in {env_path}")

    git = GitOperations.from_env(repo, env_path, branch='working')
    memory = MemorySystem(git)
    memory._env_path = env_path
    memory._load_config()
    memory._ensure_branches()

    if return_git:
        return git, memory
    return memory


# =============================================================================
# MEMORY SYSTEM
# =============================================================================

class MemorySystemError(Exception):
    """Base exception for MemorySystem."""
    pass


class MemorySystem:
    """
    Memory management layer over GitOperations.

    v2.0: Three-space architecture with squash-merge consolidation,
    local file editing pattern, and flexible fetch modes.
    """

    CONFIG_PATH = '_config.yaml'
    TEMPLATES_PATH = '_templates'
    MANIFEST_PATH = '_entities_manifest.yaml'
    LOCAL_ROOT = '/mnt/home'

    def __init__(self, git: GitOperations):
        """
        Initialize MemorySystem.

        Args:
            git: GitOperations instance connected to memory repo
        """
        self.git = git
        self.config: MemoryConfig = MemoryConfig.default()
        self._config_loaded = False

    # =========================================================================
    # INTERNAL SETUP
    # =========================================================================

    def _load_config(self) -> bool:
        """Load _config.yaml from main branch. Returns True if loaded."""
        original_branch = self.git.branch
        try:
            self.git.checkout('main')
            yaml_content = self.git.get(self.CONFIG_PATH)
            self.config = MemoryConfig.from_yaml(yaml_content)
            self._config_loaded = True
            return True
        except GitOperationsError:
            self.config = MemoryConfig.default()
            self._config_loaded = False
            return False
        finally:
            self.git.checkout(original_branch)

    def _ensure_branches(self) -> None:
        """Ensure main and working branches exist."""
        branches = self.git.branch_list()
        if 'main' not in branches:
            raise MemorySystemError("Repository must have a 'main' branch")
        if 'working' not in branches:
            self.git.branch_create('working', 'main')

    def _resolve_path(self, path: str) -> str:
        """Ensure path has .md extension."""
        if not path.endswith('.md'):
            path = f'{path}.md'
        return path

    def _validate_path(self, path: str) -> None:
        """Validate that path targets a known space."""
        parts = path.split('/')
        if len(parts) < 2:
            raise MemorySystemError(
                f"Path must include space: 'self/file', 'collaborator/file', "
                f"or 'entities/file'. Got: '{path}'"
            )
        space = parts[0]
        if space not in self.config.spaces:
            valid = ', '.join(self.config.spaces.keys())
            raise MemorySystemError(
                f"Unknown space '{space}'. Valid spaces: {valid}"
            )
        # For self/collaborator, validate category exists
        if space in ('self', 'collaborator'):
            name = parts[1].replace('.md', '')
            if not self.config.has_category(space, name):
                valid = ', '.join(self.config.get_category_names(space))
                raise MemorySystemError(
                    f"Unknown category '{name}' in space '{space}'. "
                    f"Valid categories: {valid}"
                )

    # =========================================================================
    # STATUS
    # =========================================================================

    def status(self) -> dict:
        """
        Get system status overview.

        Returns dict with:
        - repo: repository name
        - config: spaces and categories summary
        - dirty_files: files where working differs from main
        - recent_log: last N commit messages on main
        """
        # Dirty files (working ahead of main)
        try:
            diff = self.git.diff('main', 'working')
            dirty = [f['filename'] for f in diff]
        except GitOperationsError:
            dirty = []

        # Recent main log
        original_branch = self.git.branch
        try:
            self.git.checkout('main')
            log = self.git.log(limit=10)
            recent = [
                {'sha': c.sha, 'message': c.message, 'date': c.date}
                for c in log
            ]
        except GitOperationsError:
            recent = []
        finally:
            self.git.checkout(original_branch)

        # Config summary
        config_summary = {}
        for space_name, space in self.config.spaces.items():
            config_summary[space_name] = {
                'retrieval': space.retrieval,
                'categories': self.config.get_category_names(space_name),
            }

        return {
            'repo': self.git.repo_name,
            'config': config_summary,
            'dirty_files': dirty,
            'recent_log': recent,
        }

    # =========================================================================
    # FETCH (READ)
    # =========================================================================

    def fetch(
        self,
        path: str,
        return_mode: str = 'both',
        branch: str = 'working'
    ) -> Optional[str]:
        """
        Fetch a file from the repository.

        Args:
            path:        File path (e.g. 'self/positions' or 'entities/starling')
            return_mode: 'content' (string only), 'file' (local only), 'both'
            branch:      Branch to read from (default: working)

        Returns:
            Content string if return_mode is 'content' or 'both', else None.

        Raises:
            MemorySystemError: If return_mode is invalid
            GitOperationsError: If file not found
        """
        if return_mode not in ('content', 'file', 'both'):
            raise MemorySystemError(
                f"Invalid return_mode '{return_mode}'. "
                f"Must be 'content', 'file', or 'both'."
            )

        path = self._resolve_path(path)

        original_branch = self.git.branch
        try:
            self.git.checkout(branch)
            content = self.git.get(path)
        finally:
            self.git.checkout(original_branch)

        # Save to local file if requested
        if return_mode in ('file', 'both'):
            local_path = os.path.join(self.LOCAL_ROOT, path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'w') as f:
                f.write(content)

        # Return content if requested
        if return_mode in ('content', 'both'):
            return content
        return None

    # =========================================================================
    # COMMIT (WRITE)
    # =========================================================================

    def commit(
        self,
        path: str,
        message: str,
        from_file: Optional[str] = None,
        content: Optional[str] = None
    ) -> str:
        """
        Commit a file to the working branch.

        Exactly one of from_file or content must be provided.

        Args:
            path:      File path (e.g. 'self/positions')
            message:   Commit message
            from_file: Local file path to read content from (token-efficient)
            content:   Content string (when local editing isn't needed)

        Returns:
            Commit SHA

        Raises:
            MemorySystemError: If neither or both sources provided
        """
        if from_file and content:
            raise MemorySystemError(
                "Provide exactly one of from_file or content, not both."
            )
        if not from_file and content is None:
            raise MemorySystemError(
                "Must provide either from_file or content."
            )

        path = self._resolve_path(path)
        self._validate_path(path)

        # Read content from local file if specified
        if from_file:
            with open(from_file) as f:
                content = f.read()

        # Write to working branch
        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            return self.git.put(path, content, message)
        finally:
            self.git.checkout(original_branch)

    # =========================================================================
    # CONSOLIDATION (SQUASH MERGE)
    # =========================================================================

    def consolidate(
        self,
        files: Union[List[str], str],
        message: str
    ) -> str:
        """
        Squash-merge files from working to main.

        Args:
            files:   List of file paths, or 'all' for all dirty files
            message: Journal entry commit message

        Returns:
            SHA of squash commit on main

        Raises:
            MemorySystemError: If no files to consolidate
        """
        if files == 'all':
            files = self.status()['dirty_files']
        else:
            # Ensure .md extensions
            files = [self._resolve_path(f) for f in files]

        if not files:
            raise MemorySystemError("No files to consolidate")

        return self.git.squash_merge(
            from_branch='working',
            to_branch='main',
            files=files,
            message=message
        )

    # =========================================================================
    # ENTITY MANAGEMENT
    # =========================================================================

    def create_entity(
        self,
        name: str,
        type: str = 'other',
        tags: Optional[List[str]] = None,
        summary: str = ''
    ) -> str:
        """
        Create a new entity from template.

        Args:
            name:    Entity name (becomes filename)
            type:    Entity type (person, animal, place, project, concept, other)
            tags:    Anticipatory tags for manifest lookup
            summary: One-line summary for manifest

        Returns:
            Commit SHA
        """
        tags = tags or []
        entity_path = f'entities/{name}.md'

        # Generate initial content from template
        try:
            template_name = self.config.spaces.get('entities', SpaceConfig()).template
            if template_name:
                template_content = self._read_template(template_name)
                initial_content = self._render_entity_from_template(
                    template_content, name, type
                )
            else:
                initial_content = self._default_entity_content(name, type)
        except (GitOperationsError, MemorySystemError):
            initial_content = self._default_entity_content(name, type)

        # Write entity file
        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            sha = self.git.put(entity_path, initial_content,
                               f'Create entity: {name}')

            # Update manifest
            self._add_to_manifest(name, entity_path, type, tags, summary)

            return sha
        finally:
            self.git.checkout(original_branch)

    def delete_entity(self, name: str) -> bool:
        """
        Delete an entity and remove from manifest.

        Args:
            name: Entity name

        Returns:
            True if deleted
        """
        entity_path = f'entities/{name}.md'

        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            self.git.rm(entity_path, f'Delete entity: {name}')
            self._remove_from_manifest(name)
            return True
        except GitOperationsError:
            return False
        finally:
            self.git.checkout(original_branch)

    def get_manifest(self) -> dict:
        """
        Read and parse the entity manifest.

        Returns:
            Dict of entity_name → {path, type, tags, summary}
        """
        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            content = self.git.get(self.MANIFEST_PATH)
            return self._parse_manifest(content)
        except GitOperationsError:
            return {}
        finally:
            self.git.checkout(original_branch)

    def update_manifest(
        self,
        entity_name: str,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None
    ) -> str:
        """
        Update tags and/or summary for an entity in the manifest.

        Args:
            entity_name: Entity name
            tags:        New tags (None = keep existing)
            summary:     New summary (None = keep existing)

        Returns:
            Commit SHA
        """
        manifest = self.get_manifest()
        if entity_name not in manifest:
            raise MemorySystemError(
                f"Entity '{entity_name}' not found in manifest"
            )

        entry = manifest[entity_name]
        if tags is not None:
            entry['tags'] = tags
        if summary is not None:
            entry['summary'] = summary
        manifest[entity_name] = entry

        yaml_content = self._serialize_manifest(manifest)

        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            return self.git.put(self.MANIFEST_PATH, yaml_content,
                                f'Update manifest: {entity_name}')
        finally:
            self.git.checkout(original_branch)

    def search_entities(self, query: str) -> List[dict]:
        """
        Basic keyword search over entity file contents.

        Args:
            query: Search query string

        Returns:
            List of {name, path, snippet} for matching entities
        """
        manifest = self.get_manifest()
        results = []
        query_lower = query.lower()
        query_terms = query_lower.split()

        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            for name, entry in manifest.items():
                # Check tags first
                tag_text = ' '.join(entry.get('tags', [])).lower()
                summary_text = entry.get('summary', '').lower()

                # Quick relevance check on manifest data
                manifest_match = any(
                    term in tag_text or term in summary_text or term in name.lower()
                    for term in query_terms
                )

                if manifest_match:
                    results.append({
                        'name': name,
                        'path': entry.get('path', f'entities/{name}.md'),
                        'snippet': entry.get('summary', ''),
                    })
                    continue

                # Fall back to content search
                try:
                    content = self.git.get(entry.get('path', f'entities/{name}.md'))
                    content_lower = content.lower()
                    if any(term in content_lower for term in query_terms):
                        # Extract a snippet around the first match
                        for term in query_terms:
                            idx = content_lower.find(term)
                            if idx >= 0:
                                start = max(0, idx - 50)
                                end = min(len(content), idx + 100)
                                snippet = content[start:end].strip()
                                break
                        else:
                            snippet = content[:150].strip()
                        results.append({
                            'name': name,
                            'path': entry.get('path', f'entities/{name}.md'),
                            'snippet': snippet,
                        })
                except GitOperationsError:
                    pass
        finally:
            self.git.checkout(original_branch)

        return results

    # =========================================================================
    # CONFIG MUTATION
    # =========================================================================

    def add_category(
        self,
        space: str,
        name: str,
        template: str
    ) -> str:
        """
        Add a new category to a space.

        Creates template file, creates empty file from template,
        updates _config.yaml. Single commit per operation.

        Args:
            space:    Space name ('self' or 'collaborator')
            name:     Category name (lowercase, hyphens, no spaces)
            template: Template filename

        Returns:
            Commit SHA

        Raises:
            MemorySystemError: If space is full or category exists
        """
        if space not in self.config.spaces:
            raise MemorySystemError(f"Unknown space: {space}")
        if space == 'entities':
            raise MemorySystemError(
                "Entities don't use categories. Use create_entity() instead."
            )

        space_config = self.config.spaces[space]
        if len(space_config.categories) >= space_config.max_categories:
            raise MemorySystemError(
                f"Space '{space}' is at max capacity "
                f"({space_config.max_categories} categories)"
            )
        if self.config.has_category(space, name):
            raise MemorySystemError(
                f"Category '{name}' already exists in space '{space}'"
            )

        # Validate name format
        if not re.match(r'^[a-z][a-z0-9-]*$', name):
            raise MemorySystemError(
                f"Invalid category name '{name}'. "
                f"Must be lowercase, hyphens, no spaces."
            )

        # Update config
        space_config.categories.append({'name': name, 'template': template})

        # Create empty file and update config on working branch
        file_path = f'{space}/{name}.md'
        placeholder = f'# {name.replace("-", " ").title()}\n\n(nothing yet)\n'

        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            self.git.put(file_path, placeholder,
                         f'Add category: {space}/{name}')
            sha = self.git.put(self.CONFIG_PATH, self.config.to_yaml(),
                               f'Config: add {space}/{name}')
            return sha
        finally:
            self.git.checkout(original_branch)

    def rename_category(
        self,
        space: str,
        old_name: str,
        new_name: str
    ) -> str:
        """
        Rename a category within a space.

        Args:
            space:    Space name
            old_name: Current category name
            new_name: New category name

        Returns:
            Commit SHA
        """
        if not self.config.has_category(space, old_name):
            raise MemorySystemError(
                f"Category '{old_name}' not found in space '{space}'"
            )

        original_branch = self.git.branch
        try:
            self.git.checkout('working')

            # Read old file content
            old_path = f'{space}/{old_name}.md'
            try:
                content = self.git.get(old_path)
            except GitOperationsError:
                content = f'# {new_name.replace("-", " ").title()}\n\n(nothing yet)\n'

            # Create new file with old content
            new_path = f'{space}/{new_name}.md'
            self.git.put(new_path, content, f'Rename: {old_name} → {new_name}')

            # Delete old file
            try:
                self.git.rm(old_path, f'Remove old: {old_name}')
            except GitOperationsError:
                pass

            # Update config
            space_config = self.config.spaces[space]
            for cat in space_config.categories:
                if cat['name'] == old_name:
                    cat['name'] = new_name
                    break

            sha = self.git.put(self.CONFIG_PATH, self.config.to_yaml(),
                               f'Config: rename {old_name} → {new_name}')
            return sha
        finally:
            self.git.checkout(original_branch)

    def remove_category(self, space: str, name: str) -> str:
        """
        Remove a category from a space.

        Args:
            space: Space name
            name:  Category name

        Returns:
            Commit SHA
        """
        if not self.config.has_category(space, name):
            raise MemorySystemError(
                f"Category '{name}' not found in space '{space}'"
            )

        original_branch = self.git.branch
        try:
            self.git.checkout('working')

            # Delete file
            file_path = f'{space}/{name}.md'
            try:
                self.git.rm(file_path, f'Remove category: {space}/{name}')
            except GitOperationsError:
                pass

            # Update config
            space_config = self.config.spaces[space]
            space_config.categories = [
                c for c in space_config.categories if c['name'] != name
            ]

            sha = self.git.put(self.CONFIG_PATH, self.config.to_yaml(),
                               f'Config: remove {space}/{name}')
            return sha
        finally:
            self.git.checkout(original_branch)

    # =========================================================================
    # TEMPLATES
    # =========================================================================

    def get_template(self, name: str) -> str:
        """
        Read a template file.

        Args:
            name: Template name (e.g. 'self-positions' or 'self-positions.yaml')

        Returns:
            Template content string
        """
        return self._read_template(
            name if name.endswith('.yaml') else f'{name}.yaml'
        )

    def update_template(self, name: str, content: str) -> str:
        """
        Write a template file.

        Args:
            name:    Template name
            content: New template content

        Returns:
            Commit SHA
        """
        if not name.endswith('.yaml'):
            name = f'{name}.yaml'
        path = f'{self.TEMPLATES_PATH}/{name}'

        original_branch = self.git.branch
        try:
            self.git.checkout('working')
            return self.git.put(path, content,
                                f'Evolve template: {name}')
        finally:
            self.git.checkout(original_branch)

    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================

    def notify(self, message: str) -> bool:
        """Send a Telegram notification to the owner."""
        from telegram import send
        env_path = getattr(self, '_env_path', '/mnt/project/_env')
        return send(message, env_path=env_path)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _read_template(self, filename: str) -> str:
        """Read a template file from _templates/."""
        path = f'{self.TEMPLATES_PATH}/{filename}'
        original_branch = self.git.branch
        try:
            self.git.checkout('main')
            return self.git.get(path)
        finally:
            self.git.checkout(original_branch)

    def _default_entity_content(self, name: str, type: str) -> str:
        """Generate default entity markdown when no template is available."""
        title = name.replace('-', ' ').title()
        return (
            f'# {title}\n\n'
            f'**Type:** {type}\n\n'
            f'## What/Who this is\n\n(nothing yet)\n\n'
            f'## Why they/it matters\n\n(nothing yet)\n\n'
            f'## Current understanding\n\n(nothing yet)\n\n'
            f'## Open threads\n\n(nothing yet)\n'
        )

    def _render_entity_from_template(
        self, template_content: str, name: str, type: str
    ) -> str:
        """Render entity markdown from a YAML template."""
        title = name.replace('-', ' ').title()

        # Extract sections from template
        sections = []
        section_pattern = re.compile(
            r'-\s*name:\s*"?([^"\n]+)"?\s*\n\s*description:\s*"?([^"\n]+)"?',
            re.MULTILINE
        )
        for match in section_pattern.finditer(template_content):
            sections.append((match.group(1).strip(), match.group(2).strip()))

        # Extract placeholder
        placeholder_match = re.search(
            r'placeholder:\s*"?([^"\n]+)"?', template_content
        )
        placeholder = placeholder_match.group(1) if placeholder_match else '(nothing yet)'

        # Build markdown
        lines = [f'# {title}', '']

        for sec_name, sec_desc in sections:
            if sec_name == 'Type':
                lines.append(f'**Type:** {type}')
                lines.append('')
            else:
                lines.append(f'## {sec_name}')
                lines.append('')
                lines.append(placeholder)
                lines.append('')

        return '\n'.join(lines)

    def _parse_manifest(self, content: str) -> dict:
        """Parse _entities_manifest.yaml into dict."""
        manifest = {}

        # Split into entity blocks — each starts with a top-level key (no indent)
        entity_pattern = re.compile(
            r'^(\w[\w-]*):\s*\n((?:  .*\n)*)',
            re.MULTILINE
        )

        for match in entity_pattern.finditer(content):
            name = match.group(1)
            block = match.group(2)

            entry = {}

            path_match = re.search(r'path:\s*(\S+)', block)
            if path_match:
                entry['path'] = path_match.group(1)

            type_match = re.search(r'type:\s*(\S+)', block)
            if type_match:
                entry['type'] = type_match.group(1)

            tags_match = re.search(r'tags:\s*\[([^\]]*)\]', block)
            if tags_match:
                tags_str = tags_match.group(1)
                entry['tags'] = [
                    t.strip().strip("'\"")
                    for t in tags_str.split(',')
                    if t.strip()
                ]

            summary_match = re.search(r'summary:\s*"([^"]*)"', block)
            if summary_match:
                entry['summary'] = summary_match.group(1)

            manifest[name] = entry

        return manifest

    def _serialize_manifest(self, manifest: dict) -> str:
        """Serialize manifest dict to YAML string."""
        lines = ['# _entities_manifest.yaml', '']
        for name, entry in manifest.items():
            lines.append(f'{name}:')
            if 'path' in entry:
                lines.append(f'  path: {entry["path"]}')
            if 'type' in entry:
                lines.append(f'  type: {entry["type"]}')
            if 'tags' in entry:
                tags_str = ', '.join(entry['tags'])
                lines.append(f'  tags: [{tags_str}]')
            if 'summary' in entry:
                lines.append(f'  summary: "{entry["summary"]}"')
            lines.append('')
        return '\n'.join(lines)

    def _add_to_manifest(
        self, name: str, path: str, type: str,
        tags: List[str], summary: str
    ) -> str:
        """Add an entry to the entity manifest."""
        try:
            manifest = self.get_manifest()
        except (GitOperationsError, MemorySystemError):
            manifest = {}

        manifest[name] = {
            'path': path,
            'type': type,
            'tags': tags,
            'summary': summary,
        }

        yaml_content = self._serialize_manifest(manifest)
        # Assumes already on working branch
        return self.git.put(self.MANIFEST_PATH, yaml_content,
                            f'Manifest: add {name}')

    def _remove_from_manifest(self, name: str) -> Optional[str]:
        """Remove an entry from the entity manifest."""
        try:
            manifest = self.get_manifest()
        except (GitOperationsError, MemorySystemError):
            return None

        if name not in manifest:
            return None

        del manifest[name]
        yaml_content = self._serialize_manifest(manifest)
        # Assumes already on working branch
        return self.git.put(self.MANIFEST_PATH, yaml_content,
                            f'Manifest: remove {name}')

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __repr__(self) -> str:
        spaces = ', '.join(self.config.spaces.keys())
        return f"MemorySystem({self.git.repo_name}, spaces=[{spaces}])"


# =============================================================================
# SELF-TEST: Mock-based tests (no GitHub API required)
# =============================================================================

class _MockCommitInfo:
    """Minimal commit info for log() results."""
    def __init__(self, sha, message, date='2026-01-01'):
        self.sha = sha
        self.message = message
        self.date = date


class MockGitOperations:
    """
    In-memory git operations for testing memory system orchestration.
    No network calls — files stored as {branch: {path: content}}.
    """

    def __init__(self):
        self.branch = 'working'
        self.repo_name = 'test/memory-repo'
        self._files = {'main': {}, 'working': {}}
        self._commits = []

    def get(self, path):
        files = self._files.get(self.branch, {})
        if path not in files:
            raise GitOperationsError(f"File not found: {path}")
        return files[path]

    def put(self, path, content, message):
        if self.branch not in self._files:
            self._files[self.branch] = {}
        self._files[self.branch][path] = content
        sha = f"mock_{len(self._commits):04d}"
        self._commits.append({
            'sha': sha, 'message': message,
            'path': path, 'branch': self.branch
        })
        return sha

    def rm(self, path, message):
        files = self._files.get(self.branch, {})
        if path not in files:
            raise GitOperationsError(f"File not found: {path}")
        del files[path]
        self._commits.append({
            'sha': f"mock_rm_{len(self._commits):04d}",
            'message': message, 'path': path, 'branch': self.branch
        })
        return True

    def exists(self, path):
        return path in self._files.get(self.branch, {})

    def checkout(self, branch):
        self.branch = branch

    def branch_list(self):
        return list(self._files.keys())

    def branch_create(self, name, from_ref):
        source = from_ref if from_ref in self._files else 'main'
        self._files[name] = dict(self._files.get(source, {}))

    def diff(self, base, head):
        base_files = self._files.get(base, {})
        head_files = self._files.get(head, {})
        changes = []
        all_paths = set(list(base_files.keys()) + list(head_files.keys()))
        for path in all_paths:
            if path not in base_files:
                changes.append({'filename': path, 'status': 'added'})
            elif path not in head_files:
                changes.append({'filename': path, 'status': 'removed'})
            elif base_files[path] != head_files[path]:
                changes.append({'filename': path, 'status': 'modified'})
        return changes

    def log(self, limit=10, path=None):
        filtered = self._commits
        if path:
            filtered = [c for c in filtered if c.get('path', '').startswith(path)]
        return [
            _MockCommitInfo(c['sha'], c['message'])
            for c in filtered[-limit:]
        ]

    def squash_merge(self, from_branch, to_branch, files, message):
        if not files:
            raise GitOperationsError("No files specified for squash merge")
        source = self._files.get(from_branch, {})
        if to_branch not in self._files:
            self._files[to_branch] = {}
        for f in files:
            if f not in source:
                raise GitOperationsError(
                    f"File not found on '{from_branch}': {f}"
                )
            self._files[to_branch][f] = source[f]
        sha = f"squash_{len(self._commits):04d}"
        self._commits.append({
            'sha': sha, 'message': message, 'branch': to_branch
        })
        return sha

    def ls(self, path=''):
        """List directory contents (one level) — returns objects with .name, .path, .type attributes."""
        files = self._files.get(self.branch, {})
        prefix = (path.rstrip('/') + '/') if path else ''

        seen = set()
        result = []
        for fpath in files:
            if prefix and not fpath.startswith(prefix):
                continue
            rest = fpath[len(prefix):]
            parts = rest.split('/', 1)
            name = parts[0]
            is_dir = len(parts) > 1
            if name not in seen:
                seen.add(name)
                entry = type('FileInfo', (), {
                    'name': name,
                    'path': prefix + name if not is_dir else prefix + name,
                    'type': 'dir' if is_dir else 'file',
                    'size': len(files.get(fpath, '')) if not is_dir else None,
                    'sha': 'mock_sha'
                })()
                result.append(entry)
        return result

    def ls_recursive(self, path=''):
        """List all files recursively."""
        files = self._files.get(self.branch, {})
        prefix = (path.rstrip('/') + '/') if path else ''
        result = []
        for fpath, content in files.items():
            if prefix and not fpath.startswith(prefix):
                continue
            entry = type('FileInfo', (), {
                'name': fpath.split('/')[-1],
                'path': fpath,
                'type': 'file',
                'size': len(content),
                'sha': 'mock_sha'
            })()
            result.append(entry)
        return result

    def get_ref_sha(self, ref):
        return f"mocksha_{ref}"

    def status(self):
        return {
            'repo': self.repo_name,
            'branch': self.branch,
            'branches': self.branch_list()
        }


def run_tests() -> dict:
    """
    Test all memory system orchestration logic using MockGitOperations.
    No network calls, no PAT required — runs anywhere.

    Returns:
        dict with 'passed', 'failed', 'errors' counts and details
    """
    import tempfile
    import shutil

    results = {'passed': 0, 'failed': 0, 'errors': [], 'tests': []}

    def record(name, passed, detail=""):
        results['tests'].append({'name': name, 'passed': passed, 'detail': detail})
        if passed:
            results['passed'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"{name}: {detail}")

    # Create a temp directory for local file operations
    tmpdir = tempfile.mkdtemp(prefix='memory_test_')

    try:
        # === SETUP ===
        print("🔧 Setting up mock environment...")
        mock_git = MockGitOperations()

        # Seed repo with default config on main
        default_config = MemoryConfig.default()
        mock_git._files['main']['_config.yaml'] = default_config.to_yaml()
        mock_git._files['working']['_config.yaml'] = default_config.to_yaml()

        # Seed entity template
        entity_template = (
            'sections:\n'
            '  - name: "Type"\n'
            '    description: "Entity type"\n'
            '  - name: "What/Who this is"\n'
            '    description: "Core description"\n'
            '  - name: "Current understanding"\n'
            '    description: "What I know"\n'
            'placeholder: "(nothing yet)"\n'
        )
        mock_git._files['main']['_templates/entity.yaml'] = entity_template
        mock_git._files['working']['_templates/entity.yaml'] = entity_template

        # Seed empty manifest on both branches
        mock_git._files['main']['_entities_manifest.yaml'] = '# _entities_manifest.yaml\n'
        mock_git._files['working']['_entities_manifest.yaml'] = '# _entities_manifest.yaml\n'

        # Create memory system
        memory = MemorySystem(mock_git)
        memory._load_config()
        memory.LOCAL_ROOT = tmpdir  # Redirect local files to temp dir

        record('setup', True, 'Mock environment ready')

        # === TEST: Config parsing ===
        print("📋 Testing config parsing...")
        config = memory.config
        record('config_spaces',
               set(config.spaces.keys()) == {'self', 'collaborator', 'entities'},
               f"Spaces: {list(config.spaces.keys())}")
        record('config_self_categories',
               'positions' in config.get_category_names('self'),
               f"Self categories: {config.get_category_names('self')}")
        record('config_has_category',
               config.has_category('self', 'positions') and
               not config.has_category('self', 'nonexistent'),
               "has_category works correctly")

        # === TEST: Config round-trip (to_yaml → from_yaml) ===
        print("🔄 Testing config round-trip...")
        yaml_str = config.to_yaml()
        parsed_back = MemoryConfig.from_yaml(yaml_str)
        record('config_roundtrip',
               set(parsed_back.spaces.keys()) == set(config.spaces.keys()) and
               parsed_back.get_category_names('self') == config.get_category_names('self'),
               "to_yaml → from_yaml preserves structure")

        # === TEST: Status ===
        print("ℹ️  Testing status...")
        # Put a file on working that's not on main → dirty
        mock_git._files['working']['self/positions.md'] = '# Positions\n\nTest.\n'
        s = memory.status()
        record('status_structure',
               all(k in s for k in ['repo', 'config', 'dirty_files', 'recent_log']),
               f"Keys: {list(s.keys())}")
        record('status_dirty',
               'self/positions.md' in s['dirty_files'],
               f"Dirty files: {s['dirty_files']}")
        record('status_config_summary',
               'self' in s['config'] and 'categories' in s['config']['self'],
               "Config summary includes spaces and categories")

        # === TEST: Fetch — return_mode='content' ===
        print("📖 Testing fetch (content mode)...")
        content = memory.fetch('self/positions', return_mode='content')
        record('fetch_content',
               content == '# Positions\n\nTest.\n',
               f"Content returned: {content is not None}")
        # Verify no local file created
        local_path = os.path.join(tmpdir, 'self/positions.md')
        record('fetch_content_no_file',
               not os.path.exists(local_path),
               "No local file created in content mode")

        # === TEST: Fetch — return_mode='file' ===
        print("📁 Testing fetch (file mode)...")
        result = memory.fetch('self/positions', return_mode='file')
        record('fetch_file_returns_none',
               result is None,
               "File mode returns None (no content)")
        record('fetch_file_created',
               os.path.exists(local_path),
               f"Local file created at {local_path}")

        # === TEST: Fetch — return_mode='both' ===
        print("📖📁 Testing fetch (both mode)...")
        # Clean up the file first
        if os.path.exists(local_path):
            os.remove(local_path)
        result = memory.fetch('self/positions', return_mode='both')
        record('fetch_both',
               result == '# Positions\n\nTest.\n' and os.path.exists(local_path),
               "Both content returned AND file created")

        # === TEST: Fetch — invalid mode ===
        print("⚠️  Testing fetch (invalid mode)...")
        try:
            memory.fetch('self/positions', return_mode='invalid')
            record('fetch_invalid_mode', False, "Should have raised")
        except MemorySystemError:
            record('fetch_invalid_mode', True, "Correctly rejected invalid return_mode")

        # === TEST: Commit from content ===
        print("📝 Testing commit (from content)...")
        sha = memory.commit('self/methods',
                           content='# Methods\n\nNew content.\n',
                           message='test: write methods')
        record('commit_content',
               sha and mock_git._files['working'].get('self/methods.md') == '# Methods\n\nNew content.\n',
               f"SHA: {sha}, content written to working")

        # === TEST: Commit from file ===
        print("📝 Testing commit (from file)...")
        local_file = os.path.join(tmpdir, 'edited_positions.md')
        with open(local_file, 'w') as f:
            f.write('# Positions\n\nEdited locally.\n')
        sha = memory.commit('self/positions',
                           from_file=local_file,
                           message='test: commit from file')
        record('commit_from_file',
               mock_git._files['working']['self/positions.md'] == '# Positions\n\nEdited locally.\n',
               "Content read from local file and committed")

        # === TEST: Commit — error: both sources ===
        print("⚠️  Testing commit (both sources error)...")
        try:
            memory.commit('self/positions', message='test',
                         from_file='/tmp/x', content='y')
            record('commit_both_error', False, "Should have raised")
        except MemorySystemError:
            record('commit_both_error', True, "Correctly rejected both sources")

        # === TEST: Commit — error: no source ===
        try:
            memory.commit('self/positions', message='test')
            record('commit_no_source_error', False, "Should have raised")
        except MemorySystemError:
            record('commit_no_source_error', True, "Correctly rejected no source")

        # === TEST: Path validation ===
        print("🛡️  Testing path validation...")
        try:
            memory.commit('invalid-no-space', message='test', content='x')
            record('validate_no_space', False, "Should have raised")
        except MemorySystemError:
            record('validate_no_space', True, "Rejected path without space prefix")

        try:
            memory.commit('unknown/category', message='test', content='x')
            record('validate_unknown_space', False, "Should have raised")
        except MemorySystemError:
            record('validate_unknown_space', True, "Rejected unknown space")

        try:
            memory.commit('self/nonexistent-category', message='test', content='x')
            record('validate_unknown_category', False, "Should have raised")
        except MemorySystemError:
            record('validate_unknown_category', True, "Rejected unknown category in self")

        # Entities should NOT validate category names (they're open-ended)
        sha = memory.commit('entities/anything-goes', message='test', content='# Anything\n')
        record('validate_entities_open',
               sha is not None,
               "Entities accept any filename")

        # === TEST: Consolidate ===
        print("🔀 Testing consolidate...")
        # working has self/positions.md and self/methods.md that are different from main
        sha = memory.consolidate(
            files=['self/positions', 'self/methods'],
            message='Journal: consolidated positions and methods'
        )
        record('consolidate',
               sha is not None and
               mock_git._files['main'].get('self/positions.md') == mock_git._files['working']['self/positions.md'],
               f"Squash SHA: {sha}, main updated")

        # === TEST: Consolidate 'all' ===
        print("🔀 Testing consolidate (all)...")
        mock_git._files['working']['self/interests.md'] = '# Interests\n\nNew.\n'
        sha = memory.consolidate(files='all', message='test: consolidate all')
        record('consolidate_all',
               sha is not None,
               "Consolidate 'all' works via status().dirty_files")

        # === TEST: Consolidate — empty ===
        try:
            memory.consolidate(files=[], message='test')
            record('consolidate_empty', False, "Should have raised")
        except MemorySystemError:
            record('consolidate_empty', True, "Correctly rejected empty file list")

        # === TEST: Create entity ===
        print("🏷️  Testing create_entity...")
        sha = memory.create_entity(
            name='starling',
            type='person',
            tags=['friend', 'creative'],
            summary='A creative collaborator'
        )
        record('create_entity_file',
               mock_git._files['working'].get('entities/starling.md') is not None,
               f"Entity file created, SHA: {sha}")

        # Check the entity content was rendered from template
        entity_content = mock_git._files['working']['entities/starling.md']
        record('create_entity_template',
               '# Starling' in entity_content and '(nothing yet)' in entity_content,
               "Entity rendered from template")

        # === TEST: Get manifest ===
        print("📋 Testing get_manifest...")
        manifest = memory.get_manifest()
        record('get_manifest',
               'starling' in manifest and
               manifest['starling'].get('type') == 'person' and
               'friend' in manifest['starling'].get('tags', []),
               f"Manifest entries: {list(manifest.keys())}")

        # === TEST: Update manifest ===
        print("✏️  Testing update_manifest...")
        sha = memory.update_manifest('starling',
                                    tags=['friend', 'creative', 'loyal'],
                                    summary='A fiercely loyal creative collaborator')
        updated_manifest = memory.get_manifest()
        record('update_manifest',
               'loyal' in updated_manifest['starling'].get('tags', []) and
               'fiercely' in updated_manifest['starling'].get('summary', ''),
               "Tags and summary updated")

        # === TEST: Update manifest — missing entity ===
        try:
            memory.update_manifest('nonexistent', tags=['x'])
            record('update_manifest_missing', False, "Should have raised")
        except MemorySystemError:
            record('update_manifest_missing', True, "Correctly rejected missing entity")

        # === TEST: Search entities ===
        print("🔍 Testing search_entities...")
        results_search = memory.search_entities('friend')
        record('search_entities_by_tag',
               any(r['name'] == 'starling' for r in results_search),
               f"Found: {[r['name'] for r in results_search]}")

        results_search2 = memory.search_entities('creative')
        record('search_entities_by_summary',
               any(r['name'] == 'starling' for r in results_search2),
               "Also matches on summary text")

        results_search3 = memory.search_entities('zzz_definitely_not_here')
        record('search_entities_no_match',
               len(results_search3) == 0,
               "No false positives")

        # === TEST: Delete entity ===
        print("🗑️  Testing delete_entity...")
        deleted = memory.delete_entity('starling')
        record('delete_entity',
               deleted and not mock_git.exists('entities/starling.md'),
               "Entity file removed")
        manifest_after = memory.get_manifest()
        record('delete_entity_manifest',
               'starling' not in manifest_after,
               "Removed from manifest")

        # === TEST: Add category ===
        print("➕ Testing add_category...")
        sha = memory.add_category('self', 'journal', 'self-journal.yaml')
        record('add_category',
               memory.config.has_category('self', 'journal') and
               mock_git._files['working'].get('self/journal.md') is not None,
               f"Category added, file created, SHA: {sha}")

        # Config file updated on disk
        config_on_disk = mock_git._files['working']['_config.yaml']
        record('add_category_config',
               'journal' in config_on_disk,
               "Config file updated with new category")

        # === TEST: Add category — duplicate ===
        try:
            memory.add_category('self', 'journal', 'self-journal.yaml')
            record('add_category_duplicate', False, "Should have raised")
        except MemorySystemError:
            record('add_category_duplicate', True, "Correctly rejected duplicate")

        # === TEST: Add category — entities rejected ===
        try:
            memory.add_category('entities', 'thing', 'thing.yaml')
            record('add_category_entities', False, "Should have raised")
        except MemorySystemError:
            record('add_category_entities', True, "Correctly rejected entities space")

        # === TEST: Add category — invalid name ===
        try:
            memory.add_category('self', 'Bad Name!', 'bad.yaml')
            record('add_category_bad_name', False, "Should have raised")
        except MemorySystemError:
            record('add_category_bad_name', True, "Correctly rejected invalid name format")

        # === TEST: Rename category ===
        print("✏️  Testing rename_category...")
        mock_git._files['working']['self/journal.md'] = '# Journal\n\nSome entries.\n'
        sha = memory.rename_category('self', 'journal', 'reflections')
        record('rename_category',
               memory.config.has_category('self', 'reflections') and
               not memory.config.has_category('self', 'journal'),
               "Category renamed in config")
        record('rename_category_file',
               mock_git._files['working'].get('self/reflections.md') == '# Journal\n\nSome entries.\n',
               "File content preserved under new name")

        # === TEST: Rename — nonexistent ===
        try:
            memory.rename_category('self', 'nonexistent', 'whatever')
            record('rename_nonexistent', False, "Should have raised")
        except MemorySystemError:
            record('rename_nonexistent', True, "Correctly rejected nonexistent rename")

        # === TEST: Remove category ===
        print("➖ Testing remove_category...")
        sha = memory.remove_category('self', 'reflections')
        record('remove_category',
               not memory.config.has_category('self', 'reflections'),
               "Category removed from config")

        # === TEST: Remove — nonexistent ===
        try:
            memory.remove_category('self', 'nonexistent')
            record('remove_nonexistent', False, "Should have raised")
        except MemorySystemError:
            record('remove_nonexistent', True, "Correctly rejected nonexistent remove")

        # === TEST: Templates ===
        print("📄 Testing templates...")
        tmpl = memory.get_template('entity')
        record('get_template',
               'sections:' in tmpl,
               "Template read from _templates/")

        sha = memory.update_template('entity', 'updated: true\n')
        record('update_template',
               mock_git._files['working'].get('_templates/entity.yaml') == 'updated: true\n',
               f"Template updated, SHA: {sha}")

        # === TEST: resolve_path ===
        print("🔗 Testing _resolve_path...")
        record('resolve_path_no_ext',
               memory._resolve_path('self/positions') == 'self/positions.md',
               "Adds .md extension")
        record('resolve_path_has_ext',
               memory._resolve_path('self/positions.md') == 'self/positions.md',
               "Keeps existing .md extension")

        # === TEST: Max categories enforcement ===
        print("🔢 Testing max_categories enforcement...")
        # Set max_categories to a low value to test enforcement
        memory.config.spaces['collaborator'].max_categories = 2
        memory.add_category('collaborator', 'context', 'collab-context.yaml')
        try:
            memory.add_category('collaborator', 'overflow', 'overflow.yaml')
            record('max_categories', False, "Should have raised")
        except MemorySystemError as e:
            record('max_categories', 'max capacity' in str(e).lower(),
                   "Correctly enforced max_categories limit")

    except Exception as e:
        import traceback
        record('UNEXPECTED', False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    finally:
        # Cleanup temp directory
        shutil.rmtree(tmpdir, ignore_errors=True)

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

    return results


if __name__ == '__main__':
    print("Memory System v2.0 — Mock-based Test Suite")
    print("No GitHub API, no PAT, no network calls.\n")
    results = run_tests()
    import sys
    sys.exit(0 if results['failed'] == 0 else 1)


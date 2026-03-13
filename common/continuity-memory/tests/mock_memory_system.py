#!/usr/bin/env python3
"""
Mock memory_system.py for eval testing.

Mimics the v2.0 MemorySystem API without any GitHub calls.
All methods print their invocations (so the test runner can verify
tool calls in the session JSONL) and return plausible values.
"""


class MockMemorySystem:
    """Drop-in replacement for MemorySystem during evals."""

    def status(self):
        result = {
            'repo': 'test-user/test-memory-repo',
            'config': {
                'self': {
                    'retrieval': 'pre-injected',
                    'categories': ['positions', 'methods', 'interests', 'open-questions'],
                },
                'collaborator': {
                    'retrieval': 'pre-injected',
                    'categories': ['profile'],
                },
                'entities': {
                    'retrieval': 'on-demand',
                },
            },
            'dirty_files': [],
            'recent_log': [
                {
                    'sha': 'abc1234',
                    'message': 'Journal: initial setup of memory categories',
                    'date': '2026-03-10',
                },
            ],
        }
        print(f"memory.status() called")
        print(f"  repo: {result['repo']}")
        print(f"  dirty_files: {result['dirty_files']}")
        print(f"  recent_log: {len(result['recent_log'])} entries")
        return result

    def fetch(self, path, return_mode='both', branch='working'):
        print(f"memory.fetch('{path}', return_mode='{return_mode}', branch='{branch}')")
        content = f"# {path}\n\n(placeholder content for {path})\n"
        if return_mode in ('file', 'both'):
            print(f"  → saved to /tmp/mock_memory/{path}.md")
        if return_mode in ('content', 'both'):
            return content
        return None

    def commit(self, path, message, from_file=None, content=None):
        source = f"from_file='{from_file}'" if from_file else f"content=({len(content or '')} chars)"
        print(f"memory.commit('{path}', message='{message}', {source})")
        print(f"  → committed to working branch")
        return 'mock_sha_' + path.replace('/', '_')

    def consolidate(self, files, message):
        if isinstance(files, str):
            files = [files]
        print(f"memory.consolidate(files={files}, message='{message}')")
        print(f"  → squash-merged {len(files)} file(s) to main")
        return 'mock_consolidate_sha'

    def create_entity(self, name, type='other', tags=None, summary=''):
        tags = tags or []
        print(f"memory.create_entity('{name}', type='{type}', tags={tags}, summary='{summary}')")
        print(f"  → created entities/{name}.md")
        return 'mock_entity_sha_' + name

    def delete_entity(self, name):
        print(f"memory.delete_entity('{name}')")
        return 'mock_delete_sha_' + name

    def get_manifest(self):
        print(f"memory.get_manifest()")
        return {}

    def update_manifest(self, name, tags=None, summary=None):
        print(f"memory.update_manifest('{name}', tags={tags}, summary='{summary}')")
        return 'mock_manifest_sha'

    def search_entities(self, query):
        print(f"memory.search_entities('{query}')")
        return []

    def add_category(self, space, name, template=None):
        print(f"memory.add_category('{space}', '{name}', template='{template}')")
        return 'mock_category_sha'

    def rename_category(self, space, old, new):
        print(f"memory.rename_category('{space}', '{old}', '{new}')")
        return 'mock_rename_sha'

    def remove_category(self, space, name):
        print(f"memory.remove_category('{space}', '{name}')")
        return 'mock_remove_sha'


def connect(return_git=False):
    """Drop-in replacement for memory_system.connect()."""
    memory = MockMemorySystem()
    if return_git:
        return None, memory
    return memory

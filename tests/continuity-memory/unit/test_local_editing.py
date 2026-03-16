#!/usr/bin/env python3
"""
Tests for MemorySystem section editing methods (local-file-only).

These test the refactored methods that read/write local files at LOCAL_ROOT
without any GitHub fetch or commit operations.

Run with: python3 -m pytest test_local_editing.py -v
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / 'common' / 'continuity-memory' / 'scripts'
GITHUB_API_DIR = Path(__file__).parent.parent.parent.parent / 'common' / 'github-api' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(GITHUB_API_DIR))

from memory_system import MemorySystem, MockGitOperations, MemoryConfig, SECTION_EDIT_AVAILABLE

pytestmark = pytest.mark.skipif(
    not SECTION_EDIT_AVAILABLE,
    reason="tree-sitter-markdown not installed"
)

SAMPLE_POSITIONS = """# Positions

## Token efficiency is a first-class constraint

**Position:** Every token matters.

**Confidence:** high

---

## Code comments should explain why

**Position:** Comments explain intent, not mechanics.

**Confidence:** high
"""

SAMPLE_QUESTIONS = """# Open Questions

## Does vector search add value?

Still investigating whether embeddings help.

---

## How much entity detail is too much?

Need to find the right granularity.

---

## Gemini CLI for cross-model delegation?

Exploring whether this is viable.
"""

SAMPLE_MULTI_LEVEL = """# Document Title

## Overview

Top-level overview content here.

### Overview

Nested overview with more specific detail.

## Unique Section

This section has no duplicates at any level.
"""


@pytest.fixture
def memory():
    """Create a MemorySystem with local temp directory and sample files."""
    tmpdir = tempfile.mkdtemp(prefix='memory_test_')
    mock_git = MockGitOperations()

    # Seed default config
    default_config = MemoryConfig.default()
    mock_git._files['main']['_config.yaml'] = default_config.to_yaml()
    mock_git._files['working']['_config.yaml'] = default_config.to_yaml()

    mem = MemorySystem(mock_git)
    mem.config = default_config
    mem.LOCAL_ROOT = tmpdir

    # Write sample files to local directory
    for subdir in ['self', 'collaborator', 'entities']:
        os.makedirs(os.path.join(tmpdir, subdir), exist_ok=True)

    with open(os.path.join(tmpdir, 'self', 'positions.md'), 'w') as f:
        f.write(SAMPLE_POSITIONS)

    with open(os.path.join(tmpdir, 'self', 'open-questions.md'), 'w') as f:
        f.write(SAMPLE_QUESTIONS)

    with open(os.path.join(tmpdir, 'self', 'multi-level.md'), 'w') as f:
        f.write(SAMPLE_MULTI_LEVEL)

    yield mem

    shutil.rmtree(tmpdir, ignore_errors=True)


# =============================================================================
# list_sections
# =============================================================================

class TestListSectionsLocal:
    """Tests for list_sections reading from local files."""

    def test_returns_list_of_dicts(self, memory):
        result = memory.list_sections('self/positions')
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], dict)
        assert 'text' in result[0]
        assert 'level' in result[0]

    def test_finds_all_headings(self, memory):
        result = memory.list_sections('self/positions')
        texts = [h['text'] for h in result]
        assert 'Positions' in texts
        assert 'Token efficiency is a first-class constraint' in texts
        assert 'Code comments should explain why' in texts

    def test_correct_levels(self, memory):
        result = memory.list_sections('self/positions')
        h1 = [h for h in result if h['text'] == 'Positions'][0]
        h2 = [h for h in result if 'Token' in h['text']][0]
        assert h1['level'] == 1
        assert h2['level'] == 2

    def test_file_not_found_raises(self, memory):
        with pytest.raises(FileNotFoundError, match="Fetch it first"):
            memory.list_sections('self/nonexistent')


# =============================================================================
# get_section
# =============================================================================

class TestGetSectionLocal:
    """Tests for get_section reading from local files."""

    def test_returns_content(self, memory):
        content = memory.get_section('self/positions', 'Token efficiency')
        assert content is not None
        assert 'Every token matters' in content

    def test_returns_none_for_missing(self, memory):
        content = memory.get_section('self/positions', 'Nonexistent')
        assert content is None

    def test_with_level(self, memory):
        content = memory.get_section('self/multi-level', 'Overview', level=2)
        assert content is not None
        assert 'Top-level overview' in content

    def test_with_level_3(self, memory):
        content = memory.get_section('self/multi-level', 'Overview', level=3)
        assert content is not None
        assert 'Nested overview' in content


# =============================================================================
# section_exists
# =============================================================================

class TestSectionExistsLocal:
    """Tests for section_exists reading from local files."""

    def test_exists(self, memory):
        assert memory.section_exists('self/positions', 'Token efficiency')

    def test_not_exists(self, memory):
        assert not memory.section_exists('self/positions', 'Nonexistent')

    def test_with_level(self, memory):
        assert memory.section_exists('self/multi-level', 'Overview', level=2)
        assert memory.section_exists('self/multi-level', 'Overview', level=3)
        assert not memory.section_exists('self/multi-level', 'Overview', level=4)

    def test_ambiguous_returns_false(self, memory):
        """Ambiguous matches return False rather than raising."""
        assert not memory.section_exists('self/multi-level', 'Overview')


# =============================================================================
# replace_section
# =============================================================================

class TestReplaceSectionLocal:
    """Tests for replace_section writing to local files."""

    def test_returns_local_path(self, memory):
        result = memory.replace_section(
            'self/positions', 'Token efficiency', 'Updated content.'
        )
        assert result.endswith('self/positions.md')
        assert os.path.exists(result)

    def test_edits_file_on_disk(self, memory):
        local_path = memory.replace_section(
            'self/positions', 'Token efficiency', 'New position text.'
        )
        with open(local_path) as f:
            content = f.read()
        assert 'New position text.' in content
        assert 'Every token matters' not in content

    def test_preserves_other_sections(self, memory):
        local_path = memory.replace_section(
            'self/positions', 'Token efficiency', 'Replaced.'
        )
        with open(local_path) as f:
            content = f.read()
        assert 'Code comments should explain why' in content

    def test_with_level_parameter(self, memory):
        local_path = memory.replace_section(
            'self/multi-level', 'Overview', 'Level-specific.', level=2
        )
        with open(local_path) as f:
            content = f.read()
        assert 'Level-specific.' in content

    def test_does_not_touch_git(self, memory):
        """Verify no git operations (fetch/commit) are called."""
        commits_before = len(memory.git._commits)
        memory.replace_section('self/positions', 'Token efficiency', 'X.')
        assert len(memory.git._commits) == commits_before

    def test_not_found_raises(self, memory):
        with pytest.raises(ValueError, match="not found"):
            memory.replace_section('self/positions', 'Nonexistent', 'X.')

    def test_file_not_found_raises(self, memory):
        with pytest.raises(FileNotFoundError, match="Fetch it first"):
            memory.replace_section('self/nonexistent', 'X', 'Y.')


# =============================================================================
# add_entry
# =============================================================================

class TestAddEntryLocal:
    """Tests for add_entry writing to local files."""

    def test_append_to_end(self, memory):
        local_path = memory.add_entry(
            'self/positions', '## New Position\n\n**Position:** Something new.'
        )
        with open(local_path) as f:
            content = f.read()
        assert 'New Position' in content
        assert content.index('Code comments') < content.index('New Position')

    def test_insert_after(self, memory):
        local_path = memory.add_entry(
            'self/positions',
            '## Inserted\n\nInserted content.',
            after='Token efficiency'
        )
        with open(local_path) as f:
            content = f.read()
        lines = content.split('\n')
        token_idx = next(i for i, l in enumerate(lines) if 'Token efficiency' in l)
        inserted_idx = next(i for i, l in enumerate(lines) if 'Inserted' in l)
        comments_idx = next(i for i, l in enumerate(lines) if 'Code comments' in l)
        assert token_idx < inserted_idx < comments_idx

    def test_returns_local_path(self, memory):
        result = memory.add_entry(
            'self/positions', '## New\n\nContent.'
        )
        assert result.endswith('self/positions.md')

    def test_with_after_level(self, memory):
        local_path = memory.add_entry(
            'self/multi-level',
            '## Inserted\n\nContent.',
            after='Overview',
            after_level=2
        )
        with open(local_path) as f:
            content = f.read()
        assert 'Inserted' in content

    def test_does_not_touch_git(self, memory):
        commits_before = len(memory.git._commits)
        memory.add_entry('self/positions', '## New\n\nContent.')
        assert len(memory.git._commits) == commits_before


# =============================================================================
# remove_section
# =============================================================================

class TestRemoveSectionLocal:
    """Tests for remove_section writing to local files."""

    def test_removes_section(self, memory):
        local_path = memory.remove_section('self/open-questions', 'entity detail')
        with open(local_path) as f:
            content = f.read()
        assert 'entity detail' not in content
        assert 'vector search' in content
        assert 'Gemini CLI' in content

    def test_returns_local_path(self, memory):
        result = memory.remove_section('self/open-questions', 'entity detail')
        assert result.endswith('self/open-questions.md')

    def test_with_level_parameter(self, memory):
        local_path = memory.remove_section(
            'self/multi-level', 'Overview', level=3
        )
        with open(local_path) as f:
            content = f.read()
        assert '### Overview' not in content
        assert '## Overview' in content

    def test_does_not_touch_git(self, memory):
        commits_before = len(memory.git._commits)
        memory.remove_section('self/open-questions', 'entity detail')
        assert len(memory.git._commits) == commits_before

    def test_raises_on_not_found(self, memory):
        with pytest.raises(ValueError, match="not found"):
            memory.remove_section('self/open-questions', 'Nonexistent')

    def test_file_not_found_raises(self, memory):
        with pytest.raises(FileNotFoundError, match="Fetch it first"):
            memory.remove_section('self/nonexistent', 'X')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

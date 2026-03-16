# Section Editing Refactor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor section editing tools to operate on local files only (no internal fetch/commit), add `level` parameter for heading disambiguation, and add ambiguity detection to prevent silent data loss.

**Architecture:** Pure functions (`_find_section`, `_replace_section_content`, etc.) gain a `level` parameter and ambiguity detection. MemorySystem methods (`replace_section`, `add_entry`, etc.) are rewritten to read/write local files at `LOCAL_ROOT` instead of fetching from GitHub and committing. The model controls orchestration — it decides when to fetch and when to commit.

**Tech Stack:** Python 3, tree-sitter-markdown, pytest

---

## Chunk 1: Pure function changes (level + ambiguity)

### Task 1: Add level parameter and ambiguity detection to `_find_section`

**Files:**
- Modify: `common/continuity-memory/scripts/memory_system.py:158-181`
- Test: `tests/continuity-memory/unit/test_section_editing.py`

- [ ] **Step 1: Write failing tests for level parameter**

Add to `tests/continuity-memory/unit/test_section_editing.py` — new class after `TestEdgeCases`:

```python
class TestLevelParameter:
    """Tests for heading level disambiguation."""

    MULTI_LEVEL_DOC = """# Document Title

## Overview

Top-level overview content.

### Overview

Nested overview with more detail.

## Methods

Some methods here.

### Methods

Nested methods detail.
"""

    SAME_LEVEL_DOC = """# Document Title

## Summary

First summary section.

---

## Summary

Second summary section with different content.
"""

    def test_find_without_level_returns_first_match(self):
        section = _find_section(self.MULTI_LEVEL_DOC, 'Overview')
        assert section is not None
        assert section.heading.level == 2

    def test_find_with_level_2(self):
        section = _find_section(self.MULTI_LEVEL_DOC, 'Overview', level=2)
        assert section is not None
        assert section.heading.level == 2
        content = section.get_content(self.MULTI_LEVEL_DOC.encode('utf-8'))
        assert 'Top-level overview' in content

    def test_find_with_level_3(self):
        section = _find_section(self.MULTI_LEVEL_DOC, 'Overview', level=3)
        assert section is not None
        assert section.heading.level == 3
        content = section.get_content(self.MULTI_LEVEL_DOC.encode('utf-8'))
        assert 'Nested overview' in content

    def test_find_with_wrong_level_returns_none(self):
        section = _find_section(self.MULTI_LEVEL_DOC, 'Overview', level=4)
        assert section is None

    def test_ambiguous_same_level_raises_error(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            _find_section(self.SAME_LEVEL_DOC, 'Summary')

    def test_ambiguous_error_message_includes_locations(self):
        with pytest.raises(ValueError) as exc_info:
            _find_section(self.SAME_LEVEL_DOC, 'Summary')
        msg = str(exc_info.value)
        assert 'level 2' in msg
        assert 'line' in msg

    def test_ambiguous_different_levels_raises_without_level(self):
        doc = """# Title

## Overview

Content A.

### Overview

Content B.
"""
        with pytest.raises(ValueError, match="Ambiguous"):
            _find_section(doc, 'Overview')

    def test_ambiguous_resolved_by_level(self):
        doc = """# Title

## Overview

Content A.

### Overview

Content B.
"""
        section = _find_section(doc, 'Overview', level=2)
        assert section is not None
        assert section.heading.level == 2

    def test_unique_heading_no_level_needed(self):
        doc = """# Title

## First Section

Content.

## Second Section

More content.
"""
        section = _find_section(doc, 'First Section')
        assert section is not None
        assert section.heading.text == 'First Section'

    def test_same_level_ambiguity_not_resolved_by_level(self):
        """Even with level specified, two matches at that level is still ambiguous."""
        with pytest.raises(ValueError, match="Ambiguous"):
            _find_section(self.SAME_LEVEL_DOC, 'Summary', level=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/continuity-memory/unit/test_section_editing.py::TestLevelParameter -v`
Expected: FAIL — `_find_section` doesn't accept `level` parameter yet

- [ ] **Step 3: Implement level parameter and ambiguity detection in `_find_section`**

Replace `_find_section` in `common/continuity-memory/scripts/memory_system.py:158-181`:

```python
def _find_section(doc: str | bytes, target_heading: str, level: Optional[int] = None) -> Optional[SectionInfo]:
    """Find a section by heading text (case-insensitive partial match).

    Args:
        doc: Document content (str or bytes)
        target_heading: Heading text to search for (partial match)
        level: Optional heading level (1-6) to disambiguate

    Returns:
        SectionInfo if exactly one match found, None if no match.

    Raises:
        ValueError: If multiple headings match (ambiguous).
    """
    source = _ensure_bytes(doc)
    headings = _list_sections(source)
    target_lower = target_heading.lower()

    # Find all matching headings
    matches = []
    for i, heading in enumerate(headings):
        if target_lower in heading.text.lower():
            if level is not None and heading.level != level:
                continue
            matches.append((i, heading))

    if not matches:
        return None

    if len(matches) > 1:
        locations = ', '.join(
            f"'{m[1].text}' (level {m[1].level}, line {m[1].line + 1})"
            for m in matches
        )
        raise ValueError(
            f"Ambiguous heading '{target_heading}': matches {len(matches)} sections: "
            f"{locations}. Use a more specific heading text or specify level= to disambiguate."
        )

    i, heading = matches[0]

    # Find section end (next heading at same or higher level)
    section_end = len(source)
    for next_heading in headings[i + 1:]:
        if next_heading.level <= heading.level:
            section_end = next_heading.start_byte
            break

    content_start = heading.end_byte
    while content_start < len(source) and source[content_start:content_start+1] in (b'\n', b'\r'):
        content_start += 1

    return SectionInfo(
        heading=heading,
        content_start_byte=content_start,
        section_end_byte=section_end
    )
```

Add `Optional` import at top if not already present (it is — line 63).

- [ ] **Step 4: Run level parameter tests**

Run: `python3 -m pytest tests/continuity-memory/unit/test_section_editing.py::TestLevelParameter -v`
Expected: All PASS

- [ ] **Step 5: Run ALL existing tests to check for regressions**

Run: `python3 -m pytest tests/continuity-memory/unit/test_section_editing.py -v`
Expected: All PASS — existing sample files have unique headings, so no ambiguity errors triggered

- [ ] **Step 6: Commit**

```bash
git add common/continuity-memory/scripts/memory_system.py tests/continuity-memory/unit/test_section_editing.py
git commit -m "feat: add level parameter and ambiguity detection to _find_section"
```

---

### Task 2: Propagate level parameter to `_replace_section_content`, `_add_section_entry`, `_remove_section`

**Files:**
- Modify: `common/continuity-memory/scripts/memory_system.py:184-241`
- Test: `tests/continuity-memory/unit/test_section_editing.py`

- [ ] **Step 1: Write failing tests for level propagation**

Add to `tests/continuity-memory/unit/test_section_editing.py` — new class:

```python
class TestLevelPropagation:
    """Tests that level parameter propagates through replace/add/remove."""

    DOC_WITH_AMBIGUITY = """# Title

## Overview

Top-level content.

### Overview

Nested content.
"""

    def test_replace_section_with_level(self):
        result = _replace_section_content(
            self.DOC_WITH_AMBIGUITY, 'Overview', 'Replaced top-level.', level=2
        )
        assert 'Replaced top-level.' in result
        assert 'Nested content.' in result  # H3 section untouched

    def test_replace_section_with_level_3(self):
        result = _replace_section_content(
            self.DOC_WITH_AMBIGUITY, 'Overview', 'Replaced nested.', level=3
        )
        assert 'Replaced nested.' in result
        assert 'Top-level content.' in result  # H2 section untouched

    def test_replace_section_ambiguous_without_level(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            _replace_section_content(
                self.DOC_WITH_AMBIGUITY, 'Overview', 'New content.'
            )

    def test_remove_section_with_level(self):
        result = _remove_section(self.DOC_WITH_AMBIGUITY, 'Overview', level=3)
        assert '### Overview' not in result
        assert '## Overview' in result  # H2 preserved

    def test_remove_section_ambiguous_without_level(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            _remove_section(self.DOC_WITH_AMBIGUITY, 'Overview')

    def test_add_entry_after_with_level(self):
        result = _add_section_entry(
            self.DOC_WITH_AMBIGUITY,
            '## New Section\n\nNew content.',
            after='Overview',
            after_level=2
        )
        # New section should appear after H2 Overview (which includes nested H3)
        lines = result.split('\n')
        new_idx = next(i for i, l in enumerate(lines) if 'New Section' in l)
        h2_idx = next(i for i, l in enumerate(lines) if l.startswith('## Overview'))
        assert new_idx > h2_idx

    def test_add_entry_after_ambiguous_without_level(self):
        with pytest.raises(ValueError, match="Ambiguous"):
            _add_section_entry(
                self.DOC_WITH_AMBIGUITY,
                '## New\n\nContent.',
                after='Overview'
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/continuity-memory/unit/test_section_editing.py::TestLevelPropagation -v`
Expected: FAIL — functions don't accept `level` parameter yet

- [ ] **Step 3: Add level parameter to pure functions**

In `common/continuity-memory/scripts/memory_system.py`, update the three functions:

```python
def _replace_section_content(doc: str | bytes, target_heading: str, new_content: str, level: Optional[int] = None) -> str:
    """Replace a section's content (keeping the heading)."""
    source = _ensure_bytes(doc)
    section = _find_section(source, target_heading, level)
    if section is None:
        raise ValueError(f"Section '{target_heading}' not found")

    new_doc = (
        source[:section.content_start_byte] +
        new_content.strip().encode('utf-8') + b'\n\n' +
        source[section.section_end_byte:]
    )
    return new_doc.decode('utf-8')


def _add_section_entry(doc: str | bytes, new_content: str, after: Optional[str] = None, after_level: Optional[int] = None) -> str:
    """Add a new entry to the document."""
    source = _ensure_bytes(doc)

    if after is None:
        result = source.rstrip() + b'\n\n---\n\n' + new_content.strip().encode('utf-8') + b'\n'
        return result.decode('utf-8')

    section = _find_section(source, after, after_level)
    if section is None:
        raise ValueError(f"Section '{after}' not found")

    insert_point = section.section_end_byte
    new_doc = (
        source[:insert_point].rstrip() +
        b'\n\n---\n\n' +
        new_content.strip().encode('utf-8') + b'\n\n' +
        source[insert_point:].lstrip()
    )
    return new_doc.decode('utf-8')


def _remove_section(doc: str | bytes, target_heading: str, level: Optional[int] = None) -> str:
    """Remove a section entirely."""
    source = _ensure_bytes(doc)
    section = _find_section(source, target_heading, level)
    if section is None:
        raise ValueError(f"Section '{target_heading}' not found")

    remove_start = section.start_byte
    remove_end = section.section_end_byte

    # Look back for separator (---) to remove it too
    lookback = source[max(0, remove_start - 10):remove_start].decode('utf-8')
    match = re.search(r'---\s*$', lookback)
    if match:
        remove_start -= (len(lookback) - match.start())

    new_doc = (
        source[:remove_start].rstrip() + b'\n\n' +
        source[remove_end:].lstrip()
    )
    return new_doc.decode('utf-8').strip() + '\n'
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/continuity-memory/unit/test_section_editing.py -v`
Expected: All PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add common/continuity-memory/scripts/memory_system.py tests/continuity-memory/unit/test_section_editing.py
git commit -m "feat: propagate level parameter to replace/add/remove pure functions"
```

---

## Chunk 2: Refactor MemorySystem methods to local-file-only

### Task 3: Rewrite MemorySystem section methods as local file tools

**Files:**
- Modify: `common/continuity-memory/scripts/memory_system.py:681-852`
- Create: `tests/continuity-memory/unit/test_local_editing.py`

- [ ] **Step 1: Write failing tests for local-file section methods**

Create `tests/continuity-memory/unit/test_local_editing.py`:

```python
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

    yield mem

    shutil.rmtree(tmpdir, ignore_errors=True)


class TestListSectionsLocal:
    """Tests for list_sections reading from local files."""

    def test_returns_text_and_level(self, memory):
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
        content = memory.get_section('self/positions', 'Token efficiency', level=2)
        assert content is not None


class TestSectionExistsLocal:
    """Tests for section_exists reading from local files."""

    def test_exists(self, memory):
        assert memory.section_exists('self/positions', 'Token efficiency')

    def test_not_exists(self, memory):
        assert not memory.section_exists('self/positions', 'Nonexistent')

    def test_with_level(self, memory):
        assert memory.section_exists('self/positions', 'Token efficiency', level=2)
        assert not memory.section_exists('self/positions', 'Token efficiency', level=3)


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
        assert 'Every token matters' not in content  # old content gone

    def test_preserves_other_sections(self, memory):
        local_path = memory.replace_section(
            'self/positions', 'Token efficiency', 'Replaced.'
        )
        with open(local_path) as f:
            content = f.read()
        assert 'Code comments should explain why' in content

    def test_with_level_parameter(self, memory):
        local_path = memory.replace_section(
            'self/positions', 'Token efficiency', 'Level-specific.', level=2
        )
        with open(local_path) as f:
            content = f.read()
        assert 'Level-specific.' in content

    def test_does_not_touch_git(self, memory):
        """Verify no git operations (fetch/commit) are called."""
        commits_before = len(memory.git._commits)
        memory.replace_section('self/positions', 'Token efficiency', 'X.')
        assert len(memory.git._commits) == commits_before


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

    def test_does_not_touch_git(self, memory):
        commits_before = len(memory.git._commits)
        memory.add_entry('self/positions', '## New\n\nContent.')
        assert len(memory.git._commits) == commits_before


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
            'self/open-questions', 'entity detail', level=2
        )
        with open(local_path) as f:
            content = f.read()
        assert 'entity detail' not in content

    def test_does_not_touch_git(self, memory):
        commits_before = len(memory.git._commits)
        memory.remove_section('self/open-questions', 'entity detail')
        assert len(memory.git._commits) == commits_before

    def test_raises_on_not_found(self, memory):
        with pytest.raises(ValueError, match="not found"):
            memory.remove_section('self/open-questions', 'Nonexistent')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/continuity-memory/unit/test_local_editing.py -v`
Expected: FAIL — methods still do GitHub fetch/commit, don't read local files

- [ ] **Step 3: Rewrite MemorySystem section methods**

Replace the section methods block in `common/continuity-memory/scripts/memory_system.py:681-852` with:

```python
    # =========================================================================
    # SECTION-LEVEL OPERATIONS (local file tools)
    # =========================================================================

    def _local_path(self, path: str) -> str:
        """Resolve a memory path to a local file path under LOCAL_ROOT."""
        return os.path.join(self.LOCAL_ROOT, self._resolve_path(path))

    def _read_local(self, path: str) -> str:
        """Read a local file. Raises FileNotFoundError with helpful message."""
        local_path = self._local_path(path)
        try:
            with open(local_path) as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Local file not found: {local_path}. "
                f"Fetch it first with memory.fetch('{path}', return_mode='file')."
            )

    def _write_local(self, path: str, content: str) -> str:
        """Write content to a local file. Returns the local file path."""
        local_path = self._local_path(path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w') as f:
            f.write(content)
        return local_path

    def list_sections(self, path: str) -> List[dict]:
        """
        List all section headings in a local file.

        Args:
            path: File path (e.g. 'self/positions')

        Returns:
            List of {'text': heading_text, 'level': heading_level}
        """
        content = self._read_local(path)
        headings = _list_sections(content)
        return [{'text': h.text, 'level': h.level} for h in headings]

    def section_exists(self, path: str, heading: str, level: Optional[int] = None) -> bool:
        """
        Check if a section exists in a local file.

        Args:
            path:    File path
            heading: Heading text to find (partial match)
            level:   Optional heading level to disambiguate

        Returns:
            True if exactly one matching section exists
        """
        content = self._read_local(path)
        try:
            return _find_section(content, heading, level) is not None
        except ValueError:
            return False  # Ambiguous matches — caller should specify level

    def get_section(self, path: str, heading: str, level: Optional[int] = None) -> Optional[str]:
        """
        Get a section's content (without heading) from a local file.

        Args:
            path:    File path
            heading: Heading text to find
            level:   Optional heading level to disambiguate

        Returns:
            Section content string, or None if not found
        """
        content = self._read_local(path)
        section = _find_section(content, heading, level)
        if section is None:
            return None
        return section.get_content(content.encode('utf-8'))

    def replace_section(
        self,
        path: str,
        heading: str,
        content: str,
        level: Optional[int] = None
    ) -> str:
        """
        Replace a section's content in a local file (keeping the heading).

        Reads the file from LOCAL_ROOT, applies the edit, writes back.
        Does NOT commit — call memory.commit() separately.

        Args:
            path:    File path (e.g. 'self/positions')
            heading: Heading text to find (partial match)
            content: New section content (without heading)
            level:   Optional heading level to disambiguate

        Returns:
            Local file path (pass to memory.commit(from_file=...))

        Raises:
            ValueError: If section not found or ambiguous
            FileNotFoundError: If local file doesn't exist
        """
        current = self._read_local(path)
        new_content = _replace_section_content(current, heading, content, level)
        return self._write_local(path, new_content)

    def add_entry(
        self,
        path: str,
        content: str,
        after: Optional[str] = None,
        after_level: Optional[int] = None
    ) -> str:
        """
        Add a new entry to a local collection file.

        Reads the file from LOCAL_ROOT, appends/inserts entry, writes back.
        Does NOT commit — call memory.commit() separately.

        Args:
            path:        File path (e.g. 'self/positions')
            content:     New entry content (with heading)
            after:       Insert after this heading (default: append to end)
            after_level: Optional heading level for 'after' disambiguation

        Returns:
            Local file path (pass to memory.commit(from_file=...))

        Raises:
            ValueError: If 'after' heading not found or ambiguous
            FileNotFoundError: If local file doesn't exist
        """
        current = self._read_local(path)
        new_content = _add_section_entry(current, content, after, after_level)
        return self._write_local(path, new_content)

    def remove_section(
        self,
        path: str,
        heading: str,
        level: Optional[int] = None
    ) -> str:
        """
        Remove a section from a local file.

        Reads the file from LOCAL_ROOT, removes the section, writes back.
        Does NOT commit — call memory.commit() separately.

        Args:
            path:    File path
            heading: Heading text to find and remove
            level:   Optional heading level to disambiguate

        Returns:
            Local file path (pass to memory.commit(from_file=...))

        Raises:
            ValueError: If section not found or ambiguous
            FileNotFoundError: If local file doesn't exist
        """
        current = self._read_local(path)
        new_content = _remove_section(current, heading, level)
        return self._write_local(path, new_content)
```

- [ ] **Step 4: Run all tests**

Run: `python3 -m pytest tests/continuity-memory/unit/ -v`
Expected: All PASS across both test files

- [ ] **Step 5: Commit**

```bash
git add common/continuity-memory/scripts/memory_system.py tests/continuity-memory/unit/test_local_editing.py
git commit -m "refactor: section editing methods now operate on local files only"
```

---

### Task 4: Update mock for eval testing

**Files:**
- Modify: `tests/continuity-memory/evals/mock_memory_system.py`

- [ ] **Step 1: Add section editing stubs to mock**

Add to `MockMemorySystem` class in `tests/continuity-memory/evals/mock_memory_system.py`:

```python
    def list_sections(self, path):
        print(f"memory.list_sections('{path}')")
        return [{'text': 'Example Section', 'level': 2}]

    def section_exists(self, path, heading, level=None):
        print(f"memory.section_exists('{path}', '{heading}', level={level})")
        return True

    def get_section(self, path, heading, level=None):
        print(f"memory.get_section('{path}', '{heading}', level={level})")
        return f"(placeholder content for section '{heading}')"

    def replace_section(self, path, heading, content, level=None):
        print(f"memory.replace_section('{path}', '{heading}', content=({len(content)} chars), level={level})")
        return f'/tmp/mock_memory/{path}.md'

    def add_entry(self, path, content, after=None, after_level=None):
        print(f"memory.add_entry('{path}', content=({len(content)} chars), after={after}, after_level={after_level})")
        return f'/tmp/mock_memory/{path}.md'

    def remove_section(self, path, heading, level=None):
        print(f"memory.remove_section('{path}', '{heading}', level={level})")
        return f'/tmp/mock_memory/{path}.md'
```

- [ ] **Step 2: Commit**

```bash
git add tests/continuity-memory/evals/mock_memory_system.py
git commit -m "chore: add section editing stubs to eval mock"
```

---

### Task 5: Update the inline self-test in memory_system.py

**Files:**
- Modify: `common/continuity-memory/scripts/memory_system.py` (the `run_tests()` function near bottom)

The inline `run_tests()` function (line 1633+) calls the old method signatures with `message=` parameters and expects commit SHAs back. It needs updating to match the new local-file-only interface.

- [ ] **Step 1: Review which inline tests call section methods**

Check if `run_tests()` calls `replace_section`, `add_entry`, or `remove_section`. If it does, update to new signatures (no `message`, expect local path return). If it doesn't, no changes needed.

- [ ] **Step 2: Update if needed and run**

Run: `python3 common/continuity-memory/scripts/memory_system.py`
Expected: All inline tests pass

- [ ] **Step 3: Commit if changed**

```bash
git add common/continuity-memory/scripts/memory_system.py
git commit -m "chore: update inline self-test for new section method signatures"
```

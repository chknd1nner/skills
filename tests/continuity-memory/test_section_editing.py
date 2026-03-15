#!/usr/bin/env python3
"""
Unit tests for section editing functions in memory_system.py.

Tests the pure functions that handle markdown section parsing and manipulation.
Uses sample memory files as fixtures for realistic test cases.

Run with: python3 -m pytest test_section_editing.py -v
"""

import sys
from pathlib import Path

# Add the scripts directories to path
SCRIPTS_DIR = Path(__file__).parent.parent.parent / 'common' / 'continuity-memory' / 'scripts'
GITHUB_API_DIR = Path(__file__).parent.parent.parent / 'common' / 'github-api' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(GITHUB_API_DIR))

from memory_system import (
    _find_section,
    _list_sections,
    _replace_section_content,
    _add_section_entry,
    _remove_section,
    SECTION_EDIT_AVAILABLE,
)

import pytest

# Skip all tests if tree-sitter not available
pytestmark = pytest.mark.skipif(
    not SECTION_EDIT_AVAILABLE,
    reason="tree-sitter-markdown not installed"
)

# Fixtures directory
SAMPLES_DIR = Path(__file__).parent / 'sample-memories'


def load_sample(path: str) -> str:
    """Load a sample memory file."""
    return (SAMPLES_DIR / path).read_text()


# =============================================================================
# _list_sections tests
# =============================================================================

class TestListSections:
    """Tests for _list_sections function."""

    def test_finds_all_headings_in_positions(self):
        doc = load_sample('self/positions.md')
        headings = _list_sections(doc)

        texts = [h.text for h in headings]
        assert 'Positions' in texts
        assert 'Token efficiency is a first-class design constraint' in texts
        assert 'Code comments should explain why, not what' in texts
        assert 'Small models cannot do abstractive summarisation' in texts

    def test_heading_levels_correct(self):
        doc = load_sample('self/positions.md')
        headings = _list_sections(doc)

        # First heading is H1
        assert headings[0].level == 1
        assert headings[0].text == 'Positions'

        # Section headings are H2
        for h in headings[1:]:
            assert h.level == 2

    def test_finds_nested_headings_in_methods(self):
        doc = load_sample('self/methods.md')
        headings = _list_sections(doc)

        texts = [h.text for h in headings]
        # Should find H3 substeps
        assert 'Substep: Document capabilities' in texts
        assert 'Substep: Design around actuals' in texts

    def test_ignores_headings_in_code_fences(self):
        doc = load_sample('self/methods.md')
        headings = _list_sections(doc)

        texts = [h.text for h in headings]
        # These appear inside code fences and should NOT be found
        assert 'This heading inside a fence should NOT be parsed' not in texts
        assert 'Neither should this one' not in texts
        assert 'More hash characters' not in texts

    def test_ignores_headings_in_indented_code(self):
        doc = load_sample('self/methods.md')
        headings = _list_sections(doc)

        texts = [h.text for h in headings]
        # These appear in indented code blocks and should NOT be found
        assert 'This is indented code (4 spaces)' not in texts
        assert 'Also not a heading' not in texts


# =============================================================================
# _find_section tests
# =============================================================================

class TestFindSection:
    """Tests for _find_section function."""

    def test_finds_exact_match(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Token efficiency is a first-class design constraint')

        assert section is not None
        assert section.heading.text == 'Token efficiency is a first-class design constraint'

    def test_finds_partial_match(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Token efficiency')

        assert section is not None
        assert 'Token efficiency' in section.heading.text

    def test_finds_case_insensitive(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'token EFFICIENCY')

        assert section is not None
        assert 'Token efficiency' in section.heading.text

    def test_returns_none_for_nonexistent(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'This heading does not exist')

        assert section is None

    def test_section_content_excludes_heading(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Token efficiency')

        content = section.get_content(doc.encode('utf-8'))
        assert '## Token efficiency' not in content
        assert '**Position:**' in content

    def test_section_full_includes_heading(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Token efficiency')

        full = section.get_full(doc.encode('utf-8'))
        assert '## Token efficiency' in full
        assert '**Position:**' in full

    def test_section_boundary_at_same_level(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Token efficiency')

        content = section.get_content(doc.encode('utf-8'))
        # Should NOT include the next H2 section
        assert 'Code comments should explain why' not in content
        # Should include content up to separator
        assert 'silent success, visible failure' in content

    def test_section_boundary_includes_subsections(self):
        doc = load_sample('self/methods.md')
        section = _find_section(doc, 'Test-first systematic exploration')

        content = section.get_content(doc.encode('utf-8'))
        # Should include H3 subsections
        assert 'Substep: Document capabilities' in content
        assert 'Substep: Design around actuals' in content

    def test_section_at_end_of_file(self):
        doc = load_sample('self/positions.md')
        section = _find_section(doc, 'Small models cannot do abstractive')

        content = section.get_content(doc.encode('utf-8'))
        # Last section should capture to EOF
        assert 'May change as architectures improve' in content

    def test_finds_section_in_collaborator_profile(self):
        doc = load_sample('collaborator/profile.md')
        section = _find_section(doc, 'Current context')

        assert section is not None
        content = section.get_content(doc.encode('utf-8'))
        assert 'Novel in Chapter 4' in content


# =============================================================================
# _replace_section_content tests
# =============================================================================

class TestReplaceSectionContent:
    """Tests for _replace_section_content function."""

    def test_basic_replacement(self):
        doc = load_sample('self/positions.md')
        new_content = "**Position:** Updated understanding of token efficiency."

        result = _replace_section_content(doc, 'Token efficiency', new_content)

        # Heading preserved
        assert '## Token efficiency is a first-class design constraint' in result
        # New content present
        assert 'Updated understanding of token efficiency' in result
        # Old content gone
        assert 'context window pressure is constant' not in result

    def test_replacement_preserves_other_sections(self):
        doc = load_sample('self/positions.md')
        new_content = "**Position:** New content here."

        result = _replace_section_content(doc, 'Token efficiency', new_content)

        # Other sections unchanged
        assert 'Code comments should explain why, not what' in result
        assert 'Small models cannot do abstractive summarisation' in result

    def test_replacement_with_multiline_content(self):
        doc = load_sample('self/positions.md')
        new_content = """**Position:** Line one.

**How I got here:** Line two.

**Confidence:** medium"""

        result = _replace_section_content(doc, 'Token efficiency', new_content)

        assert 'Line one' in result
        assert 'Line two' in result
        assert 'medium' in result

    def test_raises_on_section_not_found(self):
        doc = load_sample('self/positions.md')

        with pytest.raises(ValueError, match="not found"):
            _replace_section_content(doc, 'Nonexistent heading', 'content')


# =============================================================================
# _add_section_entry tests
# =============================================================================

class TestAddSectionEntry:
    """Tests for _add_section_entry function."""

    def test_append_to_end(self):
        doc = load_sample('self/positions.md')
        new_entry = """## New position on testing

**Position:** Tests should be fast and deterministic.

**Confidence:** high"""

        result = _add_section_entry(doc, new_entry)

        # New entry at end
        assert result.strip().endswith('**Confidence:** high')
        # Separator added
        assert '---\n\n## New position on testing' in result

    def test_insert_after_specific_section(self):
        doc = load_sample('self/positions.md')
        new_entry = """## Inserted position

**Position:** This goes after token efficiency."""

        result = _add_section_entry(doc, new_entry, after='Token efficiency')

        # Should appear between Token efficiency and Code comments
        lines = result.split('\n')
        token_idx = next(i for i, l in enumerate(lines) if 'Token efficiency' in l)
        inserted_idx = next(i for i, l in enumerate(lines) if 'Inserted position' in l)
        comments_idx = next(i for i, l in enumerate(lines) if 'Code comments' in l)

        assert token_idx < inserted_idx < comments_idx

    def test_raises_on_after_not_found(self):
        doc = load_sample('self/positions.md')

        with pytest.raises(ValueError, match="not found"):
            _add_section_entry(doc, '## New', after='Nonexistent')


# =============================================================================
# _remove_section tests
# =============================================================================

class TestRemoveSection:
    """Tests for _remove_section function."""

    def test_remove_middle_section(self):
        doc = load_sample('self/open-questions.md')

        result = _remove_section(doc, 'How much entity detail')

        # Section removed
        assert 'How much entity detail' not in result
        # Other sections preserved
        assert 'Does vector search add value' in result
        assert 'Gemini CLI for cross-model' in result

    def test_remove_first_section(self):
        doc = load_sample('self/open-questions.md')

        result = _remove_section(doc, 'Does vector search')

        assert 'Does vector search' not in result
        assert 'How much entity detail' in result

    def test_remove_last_section(self):
        doc = load_sample('self/open-questions.md')

        result = _remove_section(doc, 'Gemini CLI')

        assert 'Gemini CLI' not in result
        assert 'Does vector search' in result
        assert 'How much entity detail' in result

    def test_removes_preceding_separator(self):
        doc = load_sample('self/open-questions.md')

        result = _remove_section(doc, 'How much entity detail')

        # Should not leave double separators
        assert '---\n\n---' not in result

    def test_raises_on_section_not_found(self):
        doc = load_sample('self/open-questions.md')

        with pytest.raises(ValueError, match="not found"):
            _remove_section(doc, 'Nonexistent question')


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and tricky markdown patterns."""

    def test_escaped_hash_not_parsed_as_heading(self):
        doc = r"""# Real Heading

Some text with \## escaped hash.

## Another Real Heading

Content here.
"""
        headings = _list_sections(doc)
        texts = [h.text for h in headings]

        assert 'Real Heading' in texts
        assert 'Another Real Heading' in texts
        # Escaped hash should not create a heading
        assert len(headings) == 2

    def test_hash_in_inline_code_not_parsed(self):
        doc = """# Heading

Use `## not a heading` in code.

## Real Second Heading

More content.
"""
        headings = _list_sections(doc)
        texts = [h.text for h in headings]

        assert len(headings) == 2
        assert 'Heading' in texts
        assert 'Real Second Heading' in texts

    def test_extended_code_fence_with_info_string(self):
        doc = """# Methods

## Example method

```python {linenos=true}
# Comment that looks like heading
## Another comment
def foo():
    pass
```

## Next method

Content.
"""
        headings = _list_sections(doc)
        texts = [h.text for h in headings]

        assert 'Methods' in texts
        assert 'Example method' in texts
        assert 'Next method' in texts
        assert len(headings) == 3

    def test_empty_section(self):
        doc = """# Title

## Empty section

## Next section

Content here.
"""
        section = _find_section(doc, 'Empty section')
        content = section.get_content(doc.encode('utf-8'))

        # Empty section should have empty content
        assert content.strip() == ''

    def test_section_with_only_whitespace(self):
        doc = """# Title

## Whitespace section



## Next section

Content.
"""
        section = _find_section(doc, 'Whitespace section')
        content = section.get_content(doc.encode('utf-8'))

        assert content.strip() == ''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

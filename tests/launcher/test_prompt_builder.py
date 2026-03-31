import os
import tempfile
from launcher.prompt_builder import assemble_prompt


class TestAssemblePrompt:
    def test_writes_single_fragment_to_temp_file(self):
        fragments = ["# Memory System\n\nSome content here."]
        path = assemble_prompt(fragments, user_appends=[])
        assert os.path.exists(path)
        content = open(path).read()
        assert "# Memory System" in content
        assert "Some content here." in content
        os.unlink(path)

    def test_concatenates_multiple_fragments(self):
        fragments = ["Fragment A content.", "Fragment B content."]
        path = assemble_prompt(fragments, user_appends=[])
        content = open(path).read()
        assert "Fragment A content." in content
        assert "Fragment B content." in content
        os.unlink(path)

    def test_appends_user_content_at_end(self):
        fragments = ["Module content."]
        user_appends = ["User appended text."]
        path = assemble_prompt(fragments, user_appends=user_appends)
        content = open(path).read()
        idx_module = content.index("Module content.")
        idx_user = content.index("User appended text.")
        assert idx_user > idx_module
        os.unlink(path)

    def test_returns_none_when_no_content(self):
        result = assemble_prompt(fragments=[], user_appends=[])
        assert result is None

    def test_handles_user_appends_only(self):
        path = assemble_prompt(fragments=[], user_appends=["Only user content."])
        content = open(path).read()
        assert "Only user content." in content
        os.unlink(path)

    def test_appends_user_file_content(self, tmp_path):
        user_file = tmp_path / "extra.md"
        user_file.write_text("Content from file.")
        fragments = ["Module content."]
        user_appends = ["Inline append.", f"file:{user_file}"]
        path = assemble_prompt(fragments, user_appends=user_appends)
        content = open(path).read()
        assert "Inline append." in content
        assert "Content from file." in content
        os.unlink(path)

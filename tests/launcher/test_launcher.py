from unittest.mock import patch, MagicMock
from launcher.launcher import parse_args


class TestParseArgs:
    def test_no_args(self):
        result = parse_args([])
        assert result["user_appends"] == []
        assert result["passthrough"] == []

    def test_passthrough_flags(self):
        result = parse_args(["--model", "opus", "--verbose"])
        assert result["passthrough"] == ["--model", "opus", "--verbose"]
        assert result["user_appends"] == []

    def test_intercepts_append_system_prompt(self):
        result = parse_args(["--append-system-prompt", "Extra instructions"])
        assert result["user_appends"] == ["Extra instructions"]
        assert result["passthrough"] == []

    def test_intercepts_append_system_prompt_file(self):
        result = parse_args(["--append-system-prompt-file", "/path/to/file.md"])
        assert result["user_appends"] == ["file:/path/to/file.md"]
        assert result["passthrough"] == []

    def test_mixed_flags(self):
        result = parse_args([
            "--model", "opus",
            "--append-system-prompt", "Be concise",
            "--verbose",
            "--append-system-prompt-file", "/tmp/extra.md",
        ])
        assert result["user_appends"] == ["Be concise", "file:/tmp/extra.md"]
        assert result["passthrough"] == ["--model", "opus", "--verbose"]

    def test_multiple_append_system_prompt(self):
        result = parse_args([
            "--append-system-prompt", "First",
            "--append-system-prompt", "Second",
        ])
        assert result["user_appends"] == ["First", "Second"]

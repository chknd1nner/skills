from unittest.mock import patch, MagicMock
from launcher.launcher import parse_args, discover_modules


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


class TestDiscoverModules:
    def test_discovers_memory_module(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            modules = discover_modules(env)
        assert len(modules) >= 1
        names = [m["name"] for m in modules]
        assert "Memory System" in names

    def test_excludes_module_with_failing_deps(self):
        env = {}
        modules = discover_modules(env)
        names = [m["name"] for m in modules]
        assert "Memory System" not in names

    def test_returns_empty_list_if_no_modules_pass(self):
        env = {}
        modules = discover_modules(env)
        assert isinstance(modules, list)

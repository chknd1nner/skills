import os
import tempfile
import pytest
from launcher.config import parse_env


class TestParseEnv:
    def test_parses_key_value_pairs(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PAT=ghp_abc123\nMEMORY_REPO=owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_handles_spaces_around_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("PAT = ghp_abc123\nMEMORY_REPO = owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_skips_empty_lines_and_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nPAT=ghp_abc123\n\n# another\nMEMORY_REPO=owner/repo\n")
        result = parse_env(str(env_file))
        assert result == {"PAT": "ghp_abc123", "MEMORY_REPO": "owner/repo"}

    def test_returns_empty_dict_if_file_missing(self, tmp_path):
        result = parse_env(str(tmp_path / ".env"))
        assert result == {}

    def test_returns_empty_dict_if_no_path(self):
        result = parse_env(None)
        assert result == {}

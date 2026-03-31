import os
import tempfile
import pytest
from launcher.config import parse_env, load_state, save_state


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


class TestStateFile:
    def test_load_returns_empty_dict_if_missing(self, tmp_path):
        result = load_state(str(tmp_path / ".claude-launcher-state.json"))
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / ".claude-launcher-state.json")
        state = {
            "memory": {
                "enabled": True,
                "selected_files": {
                    "self/positions": True,
                    "self/methods": True,
                    "collaborator/profile": True,
                },
                "templates_enabled": True,
                "entity_manifest_enabled": True,
            }
        }
        save_state(path, state)
        loaded = load_state(path)
        assert loaded == state

    def test_save_overwrites_existing(self, tmp_path):
        path = str(tmp_path / ".claude-launcher-state.json")
        save_state(path, {"memory": {"enabled": True}})
        save_state(path, {"memory": {"enabled": False}})
        loaded = load_state(path)
        assert loaded == {"memory": {"enabled": False}}

    def test_load_returns_empty_dict_on_corrupt_json(self, tmp_path):
        path = tmp_path / ".claude-launcher-state.json"
        path.write_text("not valid json{{{")
        result = load_state(str(path))
        assert result == {}

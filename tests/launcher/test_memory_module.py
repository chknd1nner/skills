import shutil
from unittest.mock import patch, MagicMock
from launcher.modules.memory.module import check_dependencies


class TestCheckDependencies:
    def test_available_when_all_deps_present(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is True
        assert result["name"] == "Memory System"
        assert result["reason"] is None

    def test_unavailable_when_pat_missing(self):
        env = {"MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "PAT" in result["reason"]

    def test_unavailable_when_memory_repo_missing(self):
        env = {"PAT": "ghp_abc"}
        with patch("shutil.which", return_value="/usr/bin/mdedit"):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "MEMORY_REPO" in result["reason"]

    def test_unavailable_when_mdedit_missing(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        with patch("shutil.which", return_value=None):
            result = check_dependencies(env)
        assert result["available"] is False
        assert "mdedit" in result["reason"]

    def test_unavailable_when_env_empty(self):
        result = check_dependencies({})
        assert result["available"] is False

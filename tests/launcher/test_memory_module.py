import shutil
from unittest.mock import patch, MagicMock
from launcher.modules.memory.module import check_dependencies, build_tui_section


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


SAMPLE_CONFIG_YAML = """# _config.yaml

spaces:
  self:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: positions
        template: self-positions.yaml
      - name: methods
        template: self-methods.yaml
  collaborator:
    retrieval: pre-injected
    max_categories: 7
    categories:
      - name: profile
        template: collaborator-profile.yaml
  entities:
    retrieval: on-demand
    template: entity.yaml
"""


class TestBuildTuiSection:
    def test_returns_items_from_config(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {}
        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML
        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, saved_state)
        labels = [item["label"] for item in items]
        assert "Enable memory system" in labels
        assert "self/positions" in labels
        assert "self/methods" in labels
        assert "collaborator/profile" in labels
        assert "Templates" in labels
        assert "Entity manifest" in labels

    def test_defaults_all_enabled_no_saved_state(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML
        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, {})
        for item in items:
            if item.get("type") != "separator":
                assert item["default"] is True

    def test_respects_saved_state(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {
            "enabled": True,
            "selected_files": {"self/positions": False, "self/methods": True},
            "templates_enabled": False,
            "entity_manifest_enabled": True,
        }
        mock_git = MagicMock()
        mock_git.get.return_value = SAMPLE_CONFIG_YAML
        with patch("launcher.modules.memory.module._connect_lightweight", return_value=mock_git):
            items = build_tui_section(env, saved_state)
        item_map = {i["label"]: i for i in items if i.get("type") != "separator"}
        assert item_map["self/positions"]["default"] is False
        assert item_map["self/methods"]["default"] is True
        assert item_map["Templates"]["default"] is False
        assert item_map["Entity manifest"]["default"] is True

    def test_falls_back_to_saved_state_on_fetch_failure(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        saved_state = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": True},
            "templates_enabled": True,
            "entity_manifest_enabled": True,
        }
        with patch("launcher.modules.memory.module._connect_lightweight", side_effect=Exception("network")):
            items = build_tui_section(env, saved_state)
        labels = [i["label"] for i in items if i.get("type") != "separator"]
        assert "self/positions" in labels
        assert "collaborator/profile" in labels

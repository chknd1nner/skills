import shutil
from unittest.mock import patch, MagicMock
from launcher.modules.memory.module import check_dependencies, build_tui_section, build_prompt


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


SAMPLE_POSITIONS_CONTENT = "# Positions\n\n## Test position\n\n**Position:** Testing.\n"
SAMPLE_PROFILE_CONTENT = "# Max\n\n## Who they are\n\nTest collaborator.\n"
SAMPLE_TEMPLATE_CONTENT = "name: positions\nspace: self\n"
SAMPLE_MANIFEST_CONTENT = "starling:\n  type: person\n  summary: Test entity\n"


class TestBuildPrompt:
    def _make_mock_memory(self):
        mock = MagicMock()
        mock.git.repo_name = "owner/test-repo"
        mock.LOCAL_ROOT = "/tmp/test-repo"
        mock.config = MagicMock()
        space_self = MagicMock()
        space_self.categories = [{"name": "positions", "template": "self-positions.yaml"}]
        space_collab = MagicMock()
        space_collab.categories = [{"name": "profile", "template": "collaborator-profile.yaml"}]
        mock.config.spaces = {
            "self": space_self, "collaborator": space_collab,
            "entities": MagicMock(categories=[]),
        }
        return mock

    def test_builds_prompt_with_selected_files(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": True},
            "templates_enabled": False, "entity_manifest_enabled": False,
        }
        mock_memory = self._make_mock_memory()
        def mock_fetch(path, return_mode='both', branch='working'):
            if 'positions' in path: return SAMPLE_POSITIONS_CONTENT
            if 'profile' in path: return SAMPLE_PROFILE_CONTENT
            return ""
        mock_memory.fetch.side_effect = mock_fetch
        mock_memory.status.return_value = {
            "repo": "owner/test-repo", "dirty_files": [],
            "recent_log": [{"sha": "abc1234", "message": "test commit", "date": "2026-03-31T10:00:00"}],
        }
        mock_memory.git.log = MagicMock(return_value=[MagicMock(date="2026-03-30T10:00:00")])
        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)
        assert '<memory file="self/positions"' in result
        assert '<memory file="collaborator/profile"' in result
        assert SAMPLE_POSITIONS_CONTENT in result
        assert SAMPLE_PROFILE_CONTENT in result
        assert "## Per-response loop" in result
        assert "## Forbidden phrases" in result

    def test_excludes_unchecked_files(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True,
            "selected_files": {"self/positions": True, "collaborator/profile": False},
            "templates_enabled": False, "entity_manifest_enabled": False,
        }
        mock_memory = self._make_mock_memory()
        mock_memory.fetch.return_value = SAMPLE_POSITIONS_CONTENT
        mock_memory.status.return_value = {"repo": "owner/test-repo", "dirty_files": [], "recent_log": []}
        mock_memory.git.log = MagicMock(return_value=[MagicMock(date="2026-03-30T10:00:00")])
        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)
        assert '<memory file="self/positions"' in result
        assert '<memory file="collaborator/profile"' not in result

    def test_includes_templates_when_selected(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True, "selected_files": {"self/positions": True},
            "templates_enabled": True, "entity_manifest_enabled": False,
        }
        mock_memory = self._make_mock_memory()
        mock_memory.fetch.return_value = SAMPLE_POSITIONS_CONTENT
        mock_memory.get_template.return_value = SAMPLE_TEMPLATE_CONTENT
        mock_memory.status.return_value = {"repo": "owner/test-repo", "dirty_files": [], "recent_log": []}
        mock_memory.git.log = MagicMock(return_value=[MagicMock(date="2026-03-30T10:00:00")])
        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)
        assert "<memory-template" in result

    def test_includes_manifest_when_selected(self):
        env = {"PAT": "ghp_abc", "MEMORY_REPO": "owner/repo"}
        selections = {
            "enabled": True, "selected_files": {},
            "templates_enabled": False, "entity_manifest_enabled": True,
        }
        mock_memory = self._make_mock_memory()
        def mock_fetch(path, return_mode='both', branch='working'):
            if 'manifest' in path: return SAMPLE_MANIFEST_CONTENT
            return ""
        mock_memory.fetch.side_effect = mock_fetch
        mock_memory.status.return_value = {"repo": "owner/test-repo", "dirty_files": [], "recent_log": []}
        mock_memory.git.log = MagicMock(return_value=[])
        with patch("launcher.modules.memory.module._connect_full", return_value=mock_memory):
            result = build_prompt(env, selections)
        assert "<memory-entity-manifest" in result

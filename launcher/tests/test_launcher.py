"""Tests for launcher module."""

from launcher.launcher import (
    collect_hooks,
    collect_mcp_entries,
    selections_to_module_state,
)


class MockModuleWithMCP:
    @staticmethod
    def build_mcp_entries(env, selections):
        return [
            {
                "name": "test-mcp",
                "type": "stdio",
                "command": "/bin/test",
                "args": [],
                "env": {},
            }
        ]


class MockModuleWithoutMCP:
    pass


class MockModuleWithMultipleMCP:
    @staticmethod
    def build_mcp_entries(env, selections):
        return [
            {"name": "mcp-a", "type": "stdio", "command": "/bin/a"},
            {"name": "mcp-b", "type": "http", "command": "http://localhost:8080"},
        ]


def test_collect_mcp_entries_from_enabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithMCP}]
    module_states = {"test_module": {"enabled": True}}

    result = collect_mcp_entries(modules, module_states, {})

    assert "test-mcp" in result
    assert result["test-mcp"]["type"] == "stdio"
    assert result["test-mcp"]["command"] == "/bin/test"


def test_collect_mcp_entries_skips_disabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithMCP}]
    module_states = {"test_module": {"enabled": False}}

    result = collect_mcp_entries(modules, module_states, {})

    assert result == {}


def test_collect_mcp_entries_skips_module_without_build_mcp_entries():
    modules = [{"name": "Legacy Module", "module": MockModuleWithoutMCP}]
    module_states = {"legacy_module": {"enabled": True}}

    result = collect_mcp_entries(modules, module_states, {})

    assert result == {}


def test_collect_mcp_entries_handles_multiple_servers():
    modules = [{"name": "Multi MCP", "module": MockModuleWithMultipleMCP}]
    module_states = {"multi_mcp": {"enabled": True}}

    result = collect_mcp_entries(modules, module_states, {})

    assert "mcp-a" in result
    assert "mcp-b" in result
    assert result["mcp-a"]["command"] == "/bin/a"
    assert result["mcp-b"]["type"] == "http"


def test_selections_to_module_state_handles_prefixed_keys():
    """Test that module-scoped keys are correctly parsed."""
    all_items = [
        {
            "type": "toggle",
            "key": "memory_system:enabled",
            "module_name": "Memory System",
            "default": True,
        },
        {
            "type": "toggle",
            "key": "codebase-memory_mcp:enabled",
            "module_name": "Codebase-Memory MCP",
            "default": True,
        },
    ]
    selections = {"memory_system:enabled": True, "codebase-memory_mcp:enabled": False}

    result = selections_to_module_state(selections, all_items)

    assert result["memory_system"]["enabled"] is True
    assert result["codebase-memory_mcp"]["enabled"] is False


class MockModuleWithHooks:
    @staticmethod
    def build_hooks(env, selections):
        return {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Grep|Glob|Read|Search",
                        "hooks": [{"type": "command", "command": "/path/gate.sh"}],
                    }
                ]
            }
        }


class MockModuleWithEmptyHooks:
    @staticmethod
    def build_hooks(env, selections):
        return {}


def test_collect_hooks_from_enabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithHooks}]
    module_states = {"test_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert len(result) == 1
    assert "hooks" in result[0]
    assert "PreToolUse" in result[0]["hooks"]


def test_collect_hooks_skips_disabled_module():
    modules = [{"name": "Test Module", "module": MockModuleWithHooks}]
    module_states = {"test_module": {"enabled": False}}

    result = collect_hooks(modules, module_states, {})

    assert result == []


def test_collect_hooks_skips_module_without_build_hooks():
    modules = [{"name": "Legacy Module", "module": MockModuleWithoutMCP}]
    module_states = {"legacy_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert result == []


def test_collect_hooks_skips_empty_fragment():
    modules = [{"name": "Empty Module", "module": MockModuleWithEmptyHooks}]
    module_states = {"empty_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert result == []

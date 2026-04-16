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


class MockModuleWithRaisingHooks:
    @staticmethod
    def build_hooks(env, selections):
        raise RuntimeError("hook build failed")


def test_collect_hooks_swallows_module_exception():
    modules = [{"name": "Bad Module", "module": MockModuleWithRaisingHooks}]
    module_states = {"bad_module": {"enabled": True}}

    result = collect_hooks(modules, module_states, {})

    assert result == []


def test_collect_hooks_aggregates_multiple_modules():
    modules = [
        {"name": "Module A", "module": MockModuleWithHooks},
        {"name": "Module B", "module": MockModuleWithHooks},
    ]
    module_states = {
        "module_a": {"enabled": True},
        "module_b": {"enabled": True},
    }

    result = collect_hooks(modules, module_states, {})

    assert len(result) == 2
    assert all("hooks" in frag for frag in result)


from unittest.mock import patch
from launcher.launcher import run_tui


def _toggle_item(key, default=True, label=None):
    return {
        "type": "toggle",
        "key": key,
        "label": label or key,
        "default": default,
        "module_name": "Test",
        "group": "master",
    }


def _radio_item(key, options, default, requires_enabled=None, label="Mode"):
    item = {
        "type": "radio",
        "key": key,
        "label": label,
        "options": options,
        "default": default,
        "group": "settings",
        "module_name": "Test",
    }
    if requires_enabled is not None:
        item["requires_enabled"] = requires_enabled
    return item


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_runs_radio_when_gate_true(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"test:enabled": True}
    mock_radio.return_value = "compact"
    items = [
        _toggle_item("test:enabled"),
        _radio_item(
            "test:mode",
            options=[{"value": "off", "label": "Off"}, {"value": "compact", "label": "Compact"}],
            default="off",
            requires_enabled="test:enabled",
        ),
    ]

    result = run_tui(items)

    assert result["test:enabled"] is True
    assert result["test:mode"] == "compact"
    mock_radio.assert_called_once()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_skips_radio_when_gate_false(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"test:enabled": False}
    items = [
        _toggle_item("test:enabled", default=False),
        _radio_item(
            "test:mode",
            options=[{"value": "off", "label": "Off"}, {"value": "tdd", "label": "TDD"}],
            default="tdd",
            requires_enabled="test:enabled",
        ),
    ]

    result = run_tui(items)

    assert result["test:enabled"] is False
    assert result["test:mode"] == "tdd"  # falls back to default, not prompted
    mock_radio.assert_not_called()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_runs_radio_when_no_gate(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {}
    mock_radio.return_value = "selected"
    items = [
        _radio_item(
            "test:mode",
            options=[{"value": "selected", "label": "Selected"}],
            default="selected",
        ),
    ]

    result = run_tui(items)

    assert result["test:mode"] == "selected"
    mock_radio.assert_called_once()


@patch("launcher.launcher._run_radio_stage")
@patch("launcher.launcher._run_checkbox_stage")
def test_run_tui_passes_only_non_radio_to_checkbox_stage(mock_checkbox, mock_radio):
    mock_checkbox.return_value = {"a:enabled": True}
    mock_radio.return_value = "x"
    items = [
        _toggle_item("a:enabled"),
        _radio_item(
            "a:mode",
            options=[{"value": "x", "label": "X"}],
            default="x",
            requires_enabled="a:enabled",
        ),
    ]

    run_tui(items)

    forwarded = mock_checkbox.call_args[0][0]
    assert all(i.get("type") != "radio" for i in forwarded)
    assert any(i["key"] == "a:enabled" for i in forwarded)


@patch("launcher.launcher._run_radio_stage")
@patch("InquirerPy.inquirer.checkbox")
def test_run_tui_skips_checkbox_when_only_separators(mock_checkbox, mock_radio):
    """Phase 1 should not render a checkbox if no toggle items are present."""
    mock_radio.return_value = "default"
    items = [
        {"type": "separator", "label": "Settings", "module_name": "Test"},
        _radio_item(
            "test:mode",
            options=[{"value": "default", "label": "Default"}],
            default="default",
        ),
    ]

    result = run_tui(items)

    mock_checkbox.assert_not_called()
    assert result["test:mode"] == "default"

"""Tests for launcher module."""

import pytest
from launcher.launcher import collect_mcp_entries


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

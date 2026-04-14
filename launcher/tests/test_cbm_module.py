"""Tests for codebase-memory-mcp module."""

import pytest
from unittest.mock import patch
from launcher.modules.codebase_memory_mcp import module


def test_check_dependencies_binary_found():
    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        result = module.check_dependencies({})

    assert result["available"] is True
    assert result["name"] == "Codebase-Memory MCP"
    assert result["reason"] is None


def test_check_dependencies_binary_not_found():
    with patch("shutil.which", return_value=None):
        result = module.check_dependencies({})

    assert result["available"] is False
    assert result["name"] == "Codebase-Memory MCP"
    assert "not found on PATH" in result["reason"]


def test_build_tui_section_returns_toggle():
    result = module.build_tui_section({}, {})

    assert len(result) == 1
    assert result[0]["type"] == "toggle"
    assert result[0]["label"] == "Codebase-Memory MCP"
    assert result[0]["key"] == "enabled"
    assert result[0]["group"] == "master"


def test_build_tui_section_respects_saved_state():
    result = module.build_tui_section({}, {"enabled": False})
    assert result[0]["default"] is False


def test_build_tui_section_defaults_to_enabled():
    result = module.build_tui_section({}, {})
    assert result[0]["default"] is True


def test_build_prompt_returns_content_with_references_path():
    result = module.build_prompt({}, {"enabled": True})

    assert "Code Discovery Protocol" in result
    assert "Quick Decision Matrix" in result
    assert "{{REFERENCES_PATH}}" not in result  # Should be replaced
    assert "references" in result  # Should have real path


def test_build_prompt_returns_empty_when_no_prompt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    result = module.build_prompt({}, {"enabled": True})
    assert result == ""


def test_build_mcp_entries_returns_server_config():
    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        result = module.build_mcp_entries({}, {"enabled": True})

    assert len(result) == 1
    assert result[0]["name"] == "codebase-memory-mcp"
    assert result[0]["type"] == "stdio"
    assert result[0]["command"] == "/usr/local/bin/codebase-memory-mcp"
    assert result[0]["args"] == []
    assert result[0]["env"] == {}


def test_build_mcp_entries_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_mcp_entries({}, {"enabled": True})
    assert result == []

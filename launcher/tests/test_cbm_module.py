"""Tests for codebase-memory-mcp module."""

import os
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
    assert result[0]["key"] == "codebase-memory_mcp:enabled"
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


def test_build_mcp_entries_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        result = module.build_mcp_entries({}, {"enabled": False})

    assert result == []


def test_build_hooks_returns_pretooluse_entry():
    result = module.build_hooks({}, {"enabled": True})

    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    entries = result["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Grep|Glob|Read|Search"
    inner = entries[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["type"] == "command"
    assert os.path.isabs(inner[0]["command"])


def test_build_hooks_gate_script_is_executable():
    result = module.build_hooks({}, {"enabled": True})
    gate_path = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert os.access(gate_path, os.X_OK), f"Gate script not executable: {gate_path}"


def test_build_hooks_returns_empty_when_disabled():
    result = module.build_hooks({}, {"enabled": False})
    assert result == {}


def test_build_hooks_returns_empty_when_gate_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "HOOKS_DIR", tmp_path)
    result = module.build_hooks({}, {"enabled": True})
    assert result == {}


def test_build_hooks_enabled_defaults_true_when_key_absent():
    # selections without 'enabled' key should default to enabled
    result = module.build_hooks({}, {})
    # Should behave the same as {"enabled": True}
    assert "hooks" in result


def test_build_hooks_chmod_failure_does_not_raise(tmp_path, monkeypatch):
    # Create a fake gate.sh in tmp_path
    gate = tmp_path / "gate.sh"
    gate.write_text("#!/bin/bash\nexit 0\n")
    monkeypatch.setattr(module, "HOOKS_DIR", tmp_path)

    # Mock os.chmod to raise PermissionError
    original_chmod = os.chmod

    def raising_chmod(path, mode):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(os, "chmod", raising_chmod)

    # Should not raise — just print a warning
    result = module.build_hooks({}, {"enabled": True})
    assert "hooks" in result

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

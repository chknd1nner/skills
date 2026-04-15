"""Tests for prompt_builder module."""

import json
import os
from launcher.prompt_builder import write_mcp_config


def test_write_mcp_config_creates_json_file():
    config = {"mcpServers": {"test-server": {"command": "/usr/bin/test"}}}
    path = write_mcp_config(config)

    assert path.endswith(".json")
    assert os.path.exists(path)

    with open(path) as f:
        written = json.load(f)

    assert written == config
    os.unlink(path)


def test_write_mcp_config_with_nested_config():
    config = {
        "mcpServers": {
            "server-a": {
                "command": "/bin/a",
                "args": ["--flag"],
                "env": {"KEY": "val"},
            },
            "server-b": {"type": "stdio", "command": "/bin/b"},
        }
    }
    path = write_mcp_config(config)

    with open(path) as f:
        written = json.load(f)

    assert written["mcpServers"]["server-a"]["args"] == ["--flag"]
    assert written["mcpServers"]["server-b"]["type"] == "stdio"
    os.unlink(path)


import json
import os
from launcher.prompt_builder import write_settings_config, merge_settings


def test_write_settings_config_creates_json_file():
    config = {"hooks": {"PreToolUse": [{"matcher": "Grep", "hooks": []}]}}
    path = write_settings_config(config)

    assert path.endswith(".json")
    assert "claude-settings" in path
    assert os.path.exists(path)

    with open(path) as f:
        written = json.load(f)

    assert written == config
    os.unlink(path)


def test_merge_settings_combines_dicts():
    a = {"hooks": {"PreToolUse": [{"matcher": "Grep"}]}}
    b = {"hooks": {"SessionStart": [{"matcher": "startup"}]}}
    result = merge_settings([a, b])

    assert "PreToolUse" in result["hooks"]
    assert "SessionStart" in result["hooks"]


def test_merge_settings_concatenates_lists():
    a = {"hooks": {"PreToolUse": [{"matcher": "Grep"}]}}
    b = {"hooks": {"PreToolUse": [{"matcher": "Glob"}]}}
    result = merge_settings([a, b])

    assert len(result["hooks"]["PreToolUse"]) == 2


def test_merge_settings_empty_list():
    assert merge_settings([]) == {}


def test_merge_settings_single_item():
    config = {"hooks": {"PreToolUse": [{"matcher": "Read"}]}}
    result = merge_settings([config])
    assert result == config

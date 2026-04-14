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
            "server-a": {"command": "/bin/a", "args": ["--flag"], "env": {"KEY": "val"}},
            "server-b": {"type": "stdio", "command": "/bin/b"},
        }
    }
    path = write_mcp_config(config)

    with open(path) as f:
        written = json.load(f)

    assert written["mcpServers"]["server-a"]["args"] == ["--flag"]
    assert written["mcpServers"]["server-b"]["type"] == "stdio"
    os.unlink(path)

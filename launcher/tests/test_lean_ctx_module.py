"""Tests for lean-ctx MCP launcher module."""

import os
from unittest.mock import patch

from launcher.modules.lean_ctx_mcp import module


def test_check_dependencies_binary_found():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.check_dependencies({})

    assert result["available"] is True
    assert result["name"] == "lean-ctx MCP"
    assert result["reason"] is None


def test_check_dependencies_binary_not_found():
    with patch("shutil.which", return_value=None):
        result = module.check_dependencies({})

    assert result["available"] is False
    assert result["name"] == "lean-ctx MCP"
    assert "not found on PATH" in result["reason"]
    assert "brew install lean-ctx" in result["reason"]


def test_build_tui_section_returns_toggle_separator_radio():
    items = module.build_tui_section({}, {})

    assert len(items) == 3
    assert items[0]["type"] == "toggle"
    assert items[0]["label"] == "lean-ctx MCP"
    assert items[0]["key"] == "lean-ctx_mcp:enabled"
    assert items[0]["group"] == "master"

    assert items[1]["type"] == "separator"
    assert items[1]["label"] == "CRP Mode"

    assert items[2]["type"] == "radio"
    assert items[2]["key"] == "lean-ctx_mcp:crp_mode"
    assert items[2]["requires_enabled"] == "lean-ctx_mcp:enabled"
    values = [opt["value"] for opt in items[2]["options"]]
    assert values == ["off", "compact", "tdd"]


def test_build_tui_section_toggle_default_respects_saved_state():
    items_on = module.build_tui_section({}, {"enabled": True})
    items_off = module.build_tui_section({}, {"enabled": False})

    assert items_on[0]["default"] is True
    assert items_off[0]["default"] is False


def test_build_tui_section_toggle_default_true_when_unset():
    items = module.build_tui_section({}, {})
    assert items[0]["default"] is True


def test_build_tui_section_radio_default_respects_saved_state():
    items = module.build_tui_section({}, {"crp_mode": "compact"})
    assert items[2]["default"] == "compact"


def test_build_tui_section_radio_default_falls_back_when_invalid():
    items = module.build_tui_section({}, {"crp_mode": "garbage"})
    assert items[2]["default"] == "tdd"


def test_build_tui_section_radio_default_tdd_when_unset():
    items = module.build_tui_section({}, {})
    assert items[2]["default"] == "tdd"


def test_build_prompt_returns_strong_language_when_enabled():
    result = module.build_prompt({}, {"enabled": True})

    assert "NEVER use" in result
    assert "ALWAYS use" in result
    assert "ctx_read" in result
    assert "ctx_shell" in result
    assert "CRITICAL" in result


def test_build_prompt_includes_modes_and_editing_sections():
    result = module.build_prompt({}, {"enabled": True})

    assert "ctx_read Modes" in result
    assert "signatures" in result
    assert "File Editing" in result
    assert "ctx_edit" in result


def test_build_prompt_returns_empty_when_disabled():
    result = module.build_prompt({}, {"enabled": False})
    assert result == ""


def test_build_prompt_defaults_to_enabled_when_key_absent():
    result = module.build_prompt({}, {})
    assert "ctx_read" in result


def test_build_prompt_returns_file_content_verbatim():
    expected = (module.PROMPTS_DIR / "tool-preference.md").read_text(encoding="utf-8")
    result = module.build_prompt({}, {"enabled": True})
    assert result == expected


def test_build_prompt_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    result = module.build_prompt({}, {"enabled": True})
    assert result == ""


def test_build_prompt_returns_empty_when_path_is_directory(tmp_path, monkeypatch):
    (tmp_path / "tool-preference.md").mkdir()
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    result = module.build_prompt({}, {"enabled": True})
    assert result == ""


def test_build_prompt_returns_empty_when_file_unreadable(tmp_path, monkeypatch):
    (tmp_path / "tool-preference.md").write_text("content", encoding="utf-8")
    monkeypatch.setattr(module, "PROMPTS_DIR", tmp_path)
    with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
        result = module.build_prompt({}, {"enabled": True})
    assert result == ""


def test_ensure_sandbox_home_creates_dir_and_symlink(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    real_lean_ctx = tmp_path / "fake-home" / ".lean-ctx"
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    result = module._ensure_sandbox_home()

    assert result == sandbox
    assert sandbox.is_dir()
    link = sandbox / ".lean-ctx"
    assert link.is_symlink()
    assert os.readlink(link) == str(real_lean_ctx)


def test_ensure_sandbox_home_idempotent(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    module._ensure_sandbox_home()
    result = module._ensure_sandbox_home()  # second call, no-op

    assert result == sandbox
    assert (sandbox / ".lean-ctx").is_symlink()


def test_ensure_sandbox_home_falls_back_when_non_symlink_blocks_path(
    tmp_path, monkeypatch
):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    # Pre-place a directory (not a symlink) at .lean-ctx
    (sandbox / ".lean-ctx").mkdir()

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME


def test_ensure_sandbox_home_falls_back_when_symlink_creation_fails(
    tmp_path, monkeypatch
):
    sandbox = tmp_path / "sandbox"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    def raising_symlink(self, target):
        raise OSError("permission denied")

    monkeypatch.setattr(module.Path, "symlink_to", raising_symlink)

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME


def test_ensure_sandbox_home_falls_back_when_mkdir_fails(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    def raising_mkdir(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(module.Path, "mkdir", raising_mkdir)

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback to real HOME


def test_build_mcp_entries_returns_server_with_env(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "compact"})

    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "lean-ctx"
    assert entry["type"] == "stdio"
    assert entry["command"] == "/usr/local/bin/lean-ctx"
    assert entry["args"] == []
    assert entry["env"]["LEAN_CTX_CRP_MODE"] == "compact"
    assert entry["env"]["HOME"] == str(tmp_path / "sandbox")


def test_build_mcp_entries_uses_default_crp_mode_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True})

    assert result[0]["env"]["LEAN_CTX_CRP_MODE"] == "tdd"


def test_build_mcp_entries_falls_back_when_invalid_crp_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "garbage"})

    assert result[0]["env"]["LEAN_CTX_CRP_MODE"] == "tdd"


def test_build_mcp_entries_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {"enabled": False})

    assert result == []


def test_build_mcp_entries_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_mcp_entries({}, {"enabled": True, "crp_mode": "tdd"})

    assert result == []


def test_build_mcp_entries_defaults_to_enabled_when_key_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "SANDBOX_HOME", tmp_path / "sandbox")
    monkeypatch.setattr(
        module.Path, "home", classmethod(lambda cls: tmp_path / "fake-home")
    )

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_mcp_entries({}, {})

    assert len(result) == 1


def test_build_hooks_returns_bash_rewrite_entry():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": True})

    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    entries = result["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"
    inner = entries[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["type"] == "command"
    assert inner[0]["command"] == "/usr/local/bin/lean-ctx hook rewrite"


def test_build_hooks_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": False})

    assert result == {}


def test_build_hooks_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}


def test_build_hooks_defaults_to_enabled_when_key_absent():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {})

    assert "hooks" in result
    assert "PreToolUse" in result["hooks"]
    entries = result["hooks"]["PreToolUse"]
    assert len(entries) == 1
    assert entries[0]["matcher"] == "Bash"
    inner = entries[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["type"] == "command"
    assert inner[0]["command"] == "/usr/local/bin/lean-ctx hook rewrite"


def test_ensure_sandbox_home_falls_back_when_symlink_points_elsewhere(
    tmp_path, monkeypatch
):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    wrong_target = tmp_path / "wrong-target"
    # Create a symlink pointing to the wrong place
    (sandbox / ".lean-ctx").symlink_to(wrong_target)

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback because symlink target mismatches


def test_ensure_sandbox_home_falls_back_when_readlink_fails(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").symlink_to(tmp_path / "whatever")

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))
    # Simulate TOCTOU: symlink disappears between is_symlink() and os.readlink()
    monkeypatch.setattr(
        module.os, "readlink", lambda p: (_ for _ in ()).throw(FileNotFoundError(p))
    )

    result = module._ensure_sandbox_home()

    assert result == fake_home  # fallback when readlink raises


def test_build_hooks_quotes_binary_path_with_spaces():
    with patch("shutil.which", return_value="/Applications/My Apps/lean-ctx"):
        result = module.build_hooks({}, {"enabled": True})

    command = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    # The quoted binary path must appear as a single shell-safe token
    assert command == "'/Applications/My Apps/lean-ctx' hook rewrite"

"""Tests for lean-ctx MCP launcher module."""

import json
import os
import subprocess
from unittest.mock import patch

import pytest

from launcher.modules.lean_ctx_mcp import module


# ---------------------------------------------------------------------------
# Fixture: reset _setup_done between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_setup_done():
    """Reset the module-level _setup_done flag before every test."""
    module._setup_done = False
    yield
    module._setup_done = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_rules(sandbox, content="# lean-ctx rules v9\n"):
    """Write a fake rules file into the sandbox."""
    rules = sandbox / module._RULES_REL
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(content, encoding="utf-8")
    return rules


def _write_settings(sandbox, data):
    """Write a fake settings.json into the sandbox."""
    settings = sandbox / module._SETTINGS_REL
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data), encoding="utf-8")
    return settings


def _patch_sandbox(monkeypatch, tmp_path):
    """Point SANDBOX_HOME at tmp_path/sandbox with a fake home."""
    sandbox = tmp_path / "sandbox"
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))
    return sandbox


# ---------------------------------------------------------------------------
# check_dependencies
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# build_tui_section
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _run_lean_ctx_setup
# ---------------------------------------------------------------------------


def test_run_lean_ctx_setup_calls_subprocess(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    with patch("subprocess.run") as mock_run:
        result = module._run_lean_ctx_setup(sandbox, "/usr/local/bin/lean-ctx")

    assert result is True
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0] == ["/usr/local/bin/lean-ctx", "setup"]
    assert call_args[1]["stdin"] == subprocess.DEVNULL
    assert call_args[1]["env"]["HOME"] == str(sandbox)
    assert call_args[1]["timeout"] == 30


def test_run_lean_ctx_setup_returns_false_on_timeout(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
        result = module._run_lean_ctx_setup(sandbox, "/usr/local/bin/lean-ctx")

    assert result is False


def test_run_lean_ctx_setup_returns_false_on_os_error(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    with patch("subprocess.run", side_effect=OSError("not found")):
        result = module._run_lean_ctx_setup(sandbox, "/usr/local/bin/lean-ctx")

    assert result is False


# ---------------------------------------------------------------------------
# _ensure_lean_ctx_setup
# ---------------------------------------------------------------------------


def test_ensure_lean_ctx_setup_runs_once(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    with patch.object(module, "_run_lean_ctx_setup", return_value=True) as mock:
        module._ensure_lean_ctx_setup(sandbox, "/bin/lean-ctx")
        module._ensure_lean_ctx_setup(sandbox, "/bin/lean-ctx")

    mock.assert_called_once()
    assert module._setup_done is True


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_returns_rules_content(tmp_path, monkeypatch):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    rules_text = "# lean-ctx v9 rules\nctx_read ctx_shell"
    _write_rules(sandbox, rules_text)

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_prompt({}, {"enabled": True})

    assert result == rules_text


def test_build_prompt_returns_empty_when_disabled(tmp_path, monkeypatch):
    _patch_sandbox(monkeypatch, tmp_path)
    result = module.build_prompt({}, {"enabled": False})
    assert result == ""


def test_build_prompt_defaults_to_enabled(tmp_path, monkeypatch):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    _write_rules(sandbox, "rules content")

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_prompt({}, {})

    assert result == "rules content"


def test_build_prompt_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_prompt({}, {"enabled": True})
    assert result == ""


def test_build_prompt_returns_empty_when_rules_file_missing(tmp_path, monkeypatch):
    _patch_sandbox(monkeypatch, tmp_path)

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_prompt({}, {"enabled": True})

    assert result == ""


def test_build_prompt_warns_when_rules_file_missing(tmp_path, monkeypatch, capsys):
    _patch_sandbox(monkeypatch, tmp_path)

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        module.build_prompt({}, {"enabled": True})

    assert "did not produce a rules file" in capsys.readouterr().err


def test_build_prompt_warns_when_sandbox_unavailable(tmp_path, monkeypatch, capsys):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").mkdir()  # block symlink creation
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_prompt({}, {"enabled": True})

    assert result == ""
    assert "sandbox unavailable" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _ensure_sandbox_home
# ---------------------------------------------------------------------------


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
    result = module._ensure_sandbox_home()

    assert result == sandbox
    assert (sandbox / ".lean-ctx").is_symlink()


def test_ensure_sandbox_home_falls_back_when_non_symlink_blocks_path(
    tmp_path, monkeypatch
):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").mkdir()

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    result = module._ensure_sandbox_home()
    assert result == fake_home


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
    assert result == fake_home


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
    assert result == fake_home


def test_ensure_sandbox_home_falls_back_when_symlink_points_elsewhere(
    tmp_path, monkeypatch
):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").symlink_to(tmp_path / "wrong-target")

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    result = module._ensure_sandbox_home()
    assert result == fake_home


def test_ensure_sandbox_home_falls_back_when_readlink_fails(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").symlink_to(tmp_path / "whatever")

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(
        module.os, "readlink", lambda p: (_ for _ in ()).throw(FileNotFoundError(p))
    )

    result = module._ensure_sandbox_home()
    assert result == fake_home


# ---------------------------------------------------------------------------
# build_mcp_entries
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# build_hooks
# ---------------------------------------------------------------------------


def test_build_hooks_returns_extracted_hooks(tmp_path, monkeypatch):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    hooks_data = {
        "PreToolUse": [
            {"matcher": "Bash|bash", "hooks": [{"type": "command", "command": "lean-ctx hook rewrite"}]},
            {"matcher": "Read|Grep|ListFiles", "hooks": [{"type": "command", "command": "lean-ctx hook redirect"}]},
        ]
    }
    _write_settings(sandbox, {"hooks": hooks_data})

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {"hooks": hooks_data}


def test_build_hooks_returns_empty_when_disabled():
    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": False})
    assert result == {}


def test_build_hooks_returns_empty_when_binary_missing():
    with patch("shutil.which", return_value=None):
        result = module.build_hooks({}, {"enabled": True})
    assert result == {}


def test_build_hooks_defaults_to_enabled(tmp_path, monkeypatch):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    hooks_data = {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}
    _write_settings(sandbox, {"hooks": hooks_data})

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_hooks({}, {})

    assert result == {"hooks": hooks_data}


def test_build_hooks_returns_empty_when_settings_missing(tmp_path, monkeypatch):
    _patch_sandbox(monkeypatch, tmp_path)

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}


def test_build_hooks_warns_when_settings_missing(tmp_path, monkeypatch, capsys):
    _patch_sandbox(monkeypatch, tmp_path)

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        module.build_hooks({}, {"enabled": True})

    assert "did not produce a settings file" in capsys.readouterr().err


def test_build_hooks_returns_empty_when_settings_has_no_hooks(tmp_path, monkeypatch):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    _write_settings(sandbox, {"other_key": "value"})

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}


def test_build_hooks_returns_empty_on_invalid_json(tmp_path, monkeypatch, capsys):
    sandbox = _patch_sandbox(monkeypatch, tmp_path)
    settings = sandbox / module._SETTINGS_REL
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("{invalid json", encoding="utf-8")

    with (
        patch("shutil.which", return_value="/usr/local/bin/lean-ctx"),
        patch.object(module, "_run_lean_ctx_setup", return_value=True),
    ):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}
    assert "could not read lean-ctx settings" in capsys.readouterr().err


def test_build_hooks_warns_when_sandbox_unavailable(tmp_path, monkeypatch, capsys):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / ".lean-ctx").mkdir()  # block symlink
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(module, "SANDBOX_HOME", sandbox)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: fake_home))

    with patch("shutil.which", return_value="/usr/local/bin/lean-ctx"):
        result = module.build_hooks({}, {"enabled": True})

    assert result == {}
    assert "sandbox unavailable" in capsys.readouterr().err

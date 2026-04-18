# OpenCode Hook Thinking Level Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `thinking` field to profiles in `.claude/hooks/opencode-router.toml` that the interceptor hook forwards as `variant` in the `POST /session/{id}/message` body. OpenCode's server translates `variant` into provider-native thinking/reasoning options.

**Architecture:** Pure additive change to `intercept-review-agents.py`. Validation happens in `_normalize_config` (warn-and-strip for unknown values, preserves current fall-through-on-error behavior for other config issues). Request body enrichment happens in `run_background_process` where the existing `body` dict is built. Tests extend the existing `test_intercept_review_agents.py` patterns.

**Tech Stack:** Python 3.11+ stdlib (tomllib, urllib), pytest.

**Spec:** `docs/superpowers/specs/2026-04-18-opencode-hook-thinking-levels-design.md`

---

## Files

- Modify: `.claude/hooks/intercept-review-agents.py`
  - Add `ALLOWED_THINKING_LEVELS` module constant.
  - Update `_normalize_config` to read, validate, warn, and store `thinking`.
  - Update `run_background_process` to inject `variant` into the POST body when set.
- Modify: `.claude/hooks/test_intercept_review_agents.py`
  - Add tests for normalization (valid, invalid, absent).
  - Add tests for request body (variant present, variant absent).

No new files. No changes to `opencode-router.toml` itself in this plan — adopting the feature is a manual TOML edit the user makes after merge.

---

## Task 1: Add `thinking` normalization with warn-and-strip

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (add constant near other validation helpers ~line 148; modify `_normalize_config` at lines 180-207)
- Test: `.claude/hooks/test_intercept_review_agents.py` (append three new tests near existing config tests ~line 1535)

- [ ] **Step 1: Write failing test — valid thinking levels are preserved**

Append to `.claude/hooks/test_intercept_review_agents.py` (after the existing config tests; test name alphabetizes after `test_config_unsupported_version`):

```python
@pytest.mark.parametrize('level', ['low', 'medium', 'high', 'max', 'xhigh'])
def test_config_thinking_valid_level_preserved(tmp_path, level):
    """Profile with a valid thinking level keeps the field after normalization."""
    toml_content = f"""\
version = 1

[profiles.p1]
agent = "code-reviewer"
thinking = "{level}"

[[routes]]
name = "r"
match_subagent = "superpowers:code-reviewer"
profile = "p1"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['profiles']['p1']['thinking'] == level
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/martinkuek/Documents/Projects/skills
pytest .claude/hooks/test_intercept_review_agents.py::test_config_thinking_valid_level_preserved -v
```

Expected: FAIL with `KeyError: 'thinking'` (key not added by `_normalize_config`).

- [ ] **Step 3: Add `ALLOWED_THINKING_LEVELS` constant and wire into `_normalize_config`**

In `.claude/hooks/intercept-review-agents.py`, add the constant just above `_validate_profiles` (after the existing `_config_error` helper at line 147):

```python
ALLOWED_THINKING_LEVELS = frozenset({'low', 'medium', 'high', 'max', 'xhigh'})
```

Then update `_normalize_config` (currently lines 180-207). The profile dict construction at lines 184-191 becomes:

```python
    profiles: dict = {}
    for name, prof in raw.get('profiles', {}).items():
        thinking = prof.get('thinking')
        if thinking is not None and thinking not in ALLOWED_THINKING_LEVELS:
            valid = ' | '.join(sorted(ALLOWED_THINKING_LEVELS))
            print(
                f"WARN: unknown thinking level {thinking!r} in profile {name!r} — ignoring.\n"
                f"      Valid: {valid}\n"
                f"      (absent = no thinking variant sent)",
                file=sys.stderr,
            )
            thinking = None
        profiles[name] = {
            'agent': prof['agent'],
            'provider': prof.get('provider'),
            'model': prof.get('model'),
            'thinking': thinking,
            'timeout_seconds': prof.get('timeout_seconds'),
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_config_thinking_valid_level_preserved -v
```

Expected: PASS for all five parametrized levels.

- [ ] **Step 5: Write failing test — invalid level warn-and-strip**

Append to the test file directly after the previous test:

```python
def test_config_thinking_invalid_level_warns_and_strips(tmp_path, capsys):
    """Profile with an unrecognized thinking level: stderr warning, field stripped, config still valid."""
    toml_content = """\
version = 1

[profiles.p1]
agent = "code-reviewer"
thinking = "extreme"

[[routes]]
name = "r"
match_subagent = "superpowers:code-reviewer"
profile = "p1"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None, 'invalid thinking level must not fail the whole config'
    assert cfg['profiles']['p1']['thinking'] is None
    captured = capsys.readouterr()
    assert 'extreme' in captured.err
    assert "'p1'" in captured.err
    assert 'low' in captured.err and 'xhigh' in captured.err
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_config_thinking_invalid_level_warns_and_strips -v
```

Expected: PASS (the implementation from Step 3 already handles this case).

- [ ] **Step 7: Write test — absent thinking yields `None`**

Append directly after the previous test:

```python
def test_config_thinking_absent_is_none(tmp_path, capsys):
    """Profile without a thinking field: normalized value is None, no stderr warning."""
    toml_content = """\
version = 1

[profiles.p1]
agent = "code-reviewer"

[[routes]]
name = "r"
match_subagent = "superpowers:code-reviewer"
profile = "p1"
"""
    path = _write_toml(tmp_path, toml_content)
    cfg = _hook.load_config(path)
    assert cfg is not None
    assert cfg['profiles']['p1']['thinking'] is None
    captured = capsys.readouterr()
    assert 'thinking' not in captured.err
```

- [ ] **Step 8: Run test to verify it passes**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_config_thinking_absent_is_none -v
```

Expected: PASS.

- [ ] **Step 9: Run the full config-test group to confirm no regressions**

```bash
pytest .claude/hooks/test_intercept_review_agents.py -v -k test_config
```

Expected: All pre-existing `test_config_*` tests PASS alongside the three new tests.

- [ ] **Step 10: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(hook): normalize thinking level with warn-and-strip"
```

---

## Task 2: Forward `thinking` as `variant` in message body

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py` (in `run_background_process`, after the existing `body['model']` block around lines 572-580)
- Test: `.claude/hooks/test_intercept_review_agents.py` (append two new tests near the existing `test_payload_model_*` tests ~line 1910)

- [ ] **Step 1: Write failing test — variant sent when thinking is set**

Append to `.claude/hooks/test_intercept_review_agents.py` after `test_payload_model_omitted_when_agent_only`. This test defines a new TOML fixture inline because existing fixtures don't set `thinking`:

```python
_THINKING_TOML = """\
version = 1

[profiles.review_gpt54]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"
thinking = "high"

[[routes]]
name = "test-route"
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"
"""


def test_payload_variant_sent_when_thinking_set(fake_opencode, tmp_path):
    """Profile with thinking='high' → POST body includes variant='high'."""
    server = fake_opencode(session_id='sess-var', result_text='Ok.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _THINKING_TOML)
    _hook.write_status(cwd, 'var-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'var-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-var',
        task_id='var-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='review_gpt54',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert body['variant'] == 'high'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_payload_variant_sent_when_thinking_set -v
```

Expected: FAIL with `KeyError: 'variant'` (the hook doesn't yet add `variant` to the body).

- [ ] **Step 3: Inject `variant` into the POST body**

In `.claude/hooks/intercept-review-agents.py`, locate the block in `run_background_process` at lines 570-581 that builds `body`. After the existing `if profile.get('provider') and profile.get('model'):` block (which closes at line 580), add:

```python
    if profile.get('thinking'):
        body['variant'] = profile['thinking']
```

So the surrounding code reads:

```python
    body: dict = {
        'agent': profile.get('agent', ''),
        'parts': [{'type': 'text', 'text': prompt}],
    }
    if profile.get('provider') and profile.get('model'):
        body['model'] = {
            'providerID': profile['provider'],
            'modelID': profile['model'],
        }
    if profile.get('thinking'):
        body['variant'] = profile['thinking']
    data = json.dumps(body).encode()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_payload_variant_sent_when_thinking_set -v
```

Expected: PASS.

- [ ] **Step 5: Write test — variant omitted when thinking is absent**

Append directly after the previous test:

```python
def test_payload_variant_omitted_when_thinking_absent(fake_opencode, tmp_path):
    """Profile without thinking → POST body has no variant field."""
    server = fake_opencode(session_id='sess-novar', result_text='Ok.')
    cwd = str(tmp_path / 'project')
    config_path = _write_toml(tmp_path, _FULL_PROFILE_TOML)  # no thinking field
    _hook.write_status(cwd, 'novar-test', 'PENDING')
    (tmp_path / 'project' / '.opencode' / 'tasks' / 'novar-test.prompt').write_text('Review this.')

    run_poller(
        session_id='sess-novar',
        task_id='novar-test',
        port=server.port,
        cwd=cwd,
        env={'OPENCODE_TIMEOUT': '10'},
        config_path=config_path,
        profile_name='review_gpt54',
    )
    msg_reqs = [r for r in server.requests if '/message' in r['path'] and r['method'] == 'POST']
    assert len(msg_reqs) == 1
    body = msg_reqs[0]['body']
    assert 'variant' not in body
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest .claude/hooks/test_intercept_review_agents.py::test_payload_variant_omitted_when_thinking_absent -v
```

Expected: PASS (the `if profile.get('thinking'):` guard ensures absence).

- [ ] **Step 7: Run the full test file to confirm no regressions**

```bash
pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected: All tests PASS (full prior suite plus five new tests from Tasks 1–2).

- [ ] **Step 8: Commit**

```bash
git add .claude/hooks/intercept-review-agents.py .claude/hooks/test_intercept_review_agents.py
git commit -m "feat(hook): forward profile thinking level as variant in message body"
```

---

## Post-implementation (manual, outside this plan)

Adopting the feature requires editing `.claude/hooks/opencode-router.toml` by hand to add a `thinking = "..."` line to any profile that should request a specific effort level. Example:

```toml
[profiles.review_gpt54]
agent = "plan"
provider = "github-copilot"
model = "gpt-5.4"
thinking = "high"
timeout_seconds = 3600
```

This edit is intentionally not part of the plan — the user sets the values based on quota/quality tradeoffs.

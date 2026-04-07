# OpenCode Router TOML and Agent Routing Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the OpenCode async bridge from a review-only, env-var-driven hook into a TOML-configured router that classifies hook inputs, selects an OpenCode agent, and can optionally force a provider/model override per profile. The implementation must preserve the existing async file-handshake architecture while replacing hard-coded review detection with ordered route matching.

**Architecture:** The hook remains a single Python entry point at `.claude/hooks/intercept-review-agents.py`. A new TOML config file at `.claude/hooks/opencode-router.toml` defines `defaults`, named `profiles`, and ordered `routes`. The hook loads and validates that config, resolves the first matching route, and sends `POST /session/{id}/message` with `agent` and, when configured, `model: { providerID, modelID }`. OpenCode agent config remains the preferred home for reasoning effort and provider-specific passthrough options; the hook TOML owns routing plus optional provider/model experiment overrides. The original design spec must be updated in the same workstream so the spec remains sufficient to reconstruct the implementation from scratch.

**Tech Stack:** Python 3 stdlib only (`tomllib`, `json`, `urllib.request`, `subprocess`, `threading`, `os`, `sys`, `uuid`, `logging`, `time`, `socket`, `hashlib`), pytest

**Primary Spec To Update:** `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`

---

## Target Config Shape

Create and adopt this hook-local config file:

```toml
version = 1

[defaults]
startup_timeout_seconds = 10
fallback = "claude"

[profiles.review_gpt54]
agent = "code-reviewer"
provider = "poe"
model = "openai/gpt-5.4"
timeout_seconds = 1200

[profiles.implementor_sonnet]
agent = "implementor"
provider = "poe"
model = "anthropic/claude-sonnet-4.6"
timeout_seconds = 3600

[[routes]]
name = "superpowers-review"
enabled = true
match_subagent = "superpowers:code-reviewer"
profile = "review_gpt54"

[[routes]]
name = "general-review-prefix"
enabled = true
match_subagent = "general-purpose"
match_description_prefix = "review"
profile = "review_gpt54"
```

Rules:
- First matching enabled route wins.
- A profile must specify `agent`.
- `provider` and `model` are optional as a pair; if either is set, both are required.
- If a profile omits `provider` and `model`, OpenCode agent defaults apply.
- Reasoning effort is not modeled in the hook TOML at this stage; configure it in OpenCode agent definitions.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `.claude/hooks/intercept-review-agents.py` | Modify | Load TOML config, resolve routes, send `agent` and optional `model` payload |
| `.claude/hooks/test_intercept_review_agents.py` | Modify | Add config, route-matching, payload-shape, and failure-mode tests |
| `.claude/hooks/opencode-router.toml` | Create | Project-scoped routing and profile config for the hook |
| `.claude/settings.json` | Modify | Remove obsolete `OPENCODE_MODEL`; keep hook wiring and minimal env only |
| `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md` | Modify | Rewrite sections so the living spec matches the new router architecture |
| `docs/superpowers/opencode-review-hook-setup.md` | Modify | Update setup and configuration docs for TOML-first routing |

---

### Task 1: Rewrite the living spec before changing code

**Files:**
- Modify: `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`

- [ ] **Step 1: Replace the old detection narrative with router-based classification**

Update the spec sections currently titled `Approach`, `Architecture`, and `Detection` so they describe:
- ordered route evaluation from `.claude/hooks/opencode-router.toml`
- first-match-wins semantics
- route matching on `subagent_type` and description prefix
- the continued presence of the `[BYPASS_HOOK]` escape hatch

- [ ] **Step 2: Replace env-var model selection with profile-based routing**

Remove or rewrite all statements that imply `OPENCODE_MODEL` drives review selection. The spec must instead state:
- the hook chooses a named profile from TOML
- a profile always selects an OpenCode `agent`
- a profile may optionally override `provider` and `model`
- reasoning effort belongs in OpenCode agent config, not the hook TOML

- [ ] **Step 3: Update the dispatch contract in the spec**

Rewrite the `Dispatch Flow` and `Background Process` sections to document the new message payload shape:

```json
{
  "agent": "code-reviewer",
  "model": {
    "providerID": "poe",
    "modelID": "openai/gpt-5.4"
  },
  "parts": [{ "type": "text", "text": "<prompt>" }]
}
```

Document that:
- `agent` is always sent when a route matches
- `model` is sent only when the selected profile specifies both `provider` and `model`
- empty response bodies, invalid JSON, and unexpected response shapes are treated as failure

- [ ] **Step 4: Add a new `Configuration` section to the spec**

Document the TOML schema in enough detail that the hook could be rebuilt from the spec alone:
- config path
- required top-level keys
- route ordering
- validation rules
- fallback semantics
- env vars that remain supported (`OPENCODE_PORT`, `OPENCODE_SERVER_PASSWORD`, `OPENCODE_DEBUG`, `OPENCODE_LOG_FILE`, `OPENCODE_SKIP_POLLER`)

- [ ] **Step 5: Update the spec timestamp and verify reconstructability**

Set `Last updated` to the implementation date and read the full spec once for internal consistency. It should describe the new router architecture end-to-end without relying on the code.

---

### Task 2: Introduce hook-local TOML config and loader

**Files:**
- Create: `.claude/hooks/opencode-router.toml`
- Modify: `.claude/hooks/intercept-review-agents.py`
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Create the tracked project config file**

Add `.claude/hooks/opencode-router.toml` with a working initial configuration for the current project. The initial config should preserve the current review-routing behavior while switching from env-driven model selection to profile-driven selection.

- [ ] **Step 2: Add config loading helpers to the hook**

In `.claude/hooks/intercept-review-agents.py`:
- import `tomllib`
- add a default config path constant for `.claude/hooks/opencode-router.toml`
- add a loader that reads and parses TOML
- add validation functions for `defaults`, `profiles`, and `routes`
- normalize the parsed TOML into an internal structure that is easy to consume during dispatch

Recommended internal shape:

```python
{
    "defaults": {"startup_timeout_seconds": 10, "fallback": "claude"},
    "profiles": {
        "review_gpt54": {
            "agent": "code-reviewer",
            "provider": "poe",
            "model": "openai/gpt-5.4",
            "timeout_seconds": 1200,
        },
    },
    "routes": [
        {
            "name": "superpowers-review",
            "enabled": True,
            "match_subagent": "superpowers:code-reviewer",
            "match_description_prefix": None,
            "profile": "review_gpt54",
        },
    ],
}
```

- [ ] **Step 3: Validate profile override rules**

Reject invalid configurations with a clear logged error:
- profile missing `agent`
- route references a missing profile
- profile sets `provider` without `model`
- profile sets `model` without `provider`
- unknown `fallback` value
- unsupported `version`

Invalid config should not crash Claude Code. The hook should log the configuration error and fall through to Claude.

- [ ] **Step 4: Add config-loader tests**

Add pytest coverage for:
- valid config parse
- missing profile reference
- missing `agent`
- provider/model pair validation
- disabled routes being ignored
- description-prefix normalization to lowercase matching

---

### Task 3: Replace `is_review_call` with ordered route matching

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py`
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Add a route matcher**

Add helper functions that:
- preserve the existing `is_bypass(description)` check
- inspect `subagent_type` and `description`
- iterate through routes in declared order
- return the first matching route plus its resolved profile

Supported match fields for this iteration:
- `match_subagent`
- `match_description_prefix`

Matching rules:
- string equality for `match_subagent`
- case-insensitive `startswith()` for `match_description_prefix`
- omitted match fields are treated as unconstrained
- disabled routes are skipped

- [ ] **Step 2: Remove the hard-coded review-only branch**

Replace the current `is_review_call()` gate in `main()` with:
- load config
- find first matching route
- pass through when no route matches
- dispatch using the resolved profile when a route matches

- [ ] **Step 3: Add route-matching tests**

Add tests for:
- exact `superpowers:code-reviewer` match
- `general-purpose` plus `review` description prefix
- first-match-wins when two routes overlap
- no route match falls through silently
- bypass flag short-circuits route matching

---

### Task 4: Change message dispatch to use `agent` plus optional `model`

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py`
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Refactor the background dispatch function signature**

Change `run_background_process(...)` to accept the resolved route/profile settings instead of a single flat `model` string. The poller invocation should carry enough information to rebuild the selected dispatch settings in the child process. Choose one of these approaches and use it consistently:
- pass the config path and route/profile name to `--poll`, then reload config in the child
- or serialize the resolved dispatch settings into a small JSON blob passed on argv

Prefer reloading by config path plus route/profile name for readability and lower argv complexity.

- [ ] **Step 2: Build the request body from the profile**

Construct the body like this:

```python
body = {
    "agent": profile["agent"],
    "parts": [{"type": "text", "text": prompt}],
}
if profile has provider+model:
    body["model"] = {
        "providerID": profile["provider"],
        "modelID": profile["model"],
    }
```

Do not send the old `modelID` string field.

- [ ] **Step 3: Treat malformed success responses as failure**

Strengthen `run_background_process()` to fail cleanly when the message endpoint returns:
- empty body
- invalid JSON
- JSON with no `info`
- JSON with no `parts`
- `finish` other than `"stop"`

On failure:
- write `FAILED`
- preserve any partial progress transcript
- log the failure reason

- [ ] **Step 4: Add payload-shape and malformed-response tests**

Add tests that assert:
- `agent` is always sent for a matched route
- `model` object is sent when provider/model override exists
- `model` is omitted when the profile only specifies `agent`
- empty `200 OK` body produces `FAILED`
- invalid JSON body produces `FAILED`
- finish not equal to `stop` produces `FAILED`

---

### Task 5: Move timeout resolution into profiles and defaults

**Files:**
- Modify: `.claude/hooks/intercept-review-agents.py`
- Modify: `.claude/hooks/test_intercept_review_agents.py`

- [ ] **Step 1: Resolve timeouts from config instead of a single review env var**

The hook should resolve:
- startup timeout from TOML `defaults.startup_timeout_seconds`, with env `OPENCODE_STARTUP_TIMEOUT` remaining as an explicit override
- request timeout from `profile.timeout_seconds`, with env `OPENCODE_TIMEOUT` remaining as an explicit override

This preserves operability while moving the main configuration surface into TOML.

- [ ] **Step 2: Add timeout-resolution tests**

Add tests for:
- profile-specific timeout
- fallback to defaults when profile timeout is absent
- env override still wins when explicitly set

---

### Task 6: Update project settings and setup documentation

**Files:**
- Modify: `.claude/settings.json`
- Modify: `docs/superpowers/opencode-review-hook-setup.md`

- [ ] **Step 1: Remove obsolete env model selection from project settings**

Edit `.claude/settings.json` to remove `OPENCODE_MODEL`. Keep only env vars that still make sense at the Claude settings layer, such as `OPENCODE_PORT` or `OPENCODE_DEBUG`, if they are still wanted for this project.

- [ ] **Step 2: Rewrite the setup guide for TOML-first configuration**

Update `docs/superpowers/opencode-review-hook-setup.md` so it explains:
- the new config file path
- routes versus profiles
- `agent` plus optional provider/model overrides
- why reasoning effort belongs in OpenCode agent config
- which env vars remain supported

- [ ] **Step 3: Add a concrete example for reviewer/coder split**

Include one example showing:
- review routes to GPT-5.4
- implementor routes to Sonnet 4.6

This should reflect the primary user motivation for the router.

---

### Task 7: Run the full verification set

**Files:**
- No file changes

- [ ] **Step 1: Run the hook test suite**

Run:

```bash
python3 -m pytest .claude/hooks/test_intercept_review_agents.py -v
```

Expected:
- all existing async-bridge tests still pass after adaptation
- new config and payload tests pass

- [ ] **Step 2: Smoke test route resolution locally**

Use the hook directly with representative stdin payloads to verify:
- matched review route returns deny with async instructions
- unmatched route passes through
- invalid TOML falls through safely with a logged error

- [ ] **Step 3: Live probe against the local OpenCode server**

Verify with the running server that a matched route produces:
- `POST /session`
- `POST /session/{id}/message` with `agent`
- optional `model` object when configured

Also verify that an invalid `target_agent` or malformed empty response results in `FAILED` status and preserves fallback behavior.

---

### Task 8: Final documentation alignment check

**Files:**
- Modify as needed: `docs/superpowers/specs/2026-04-03-opencode-async-bridge-design.md`
- Modify as needed: `docs/superpowers/opencode-review-hook-setup.md`

- [ ] **Step 1: Re-read the code and the spec side by side**

After implementation and tests, compare the final code with the updated April 3 spec. Fix any drift immediately. The spec is the source of truth for reconstruction and must not lag behind the implementation.

- [ ] **Step 2: Re-read the setup guide from a new-user perspective**

Confirm that a user could:
- understand where to edit routing
- know when to use OpenCode agent config versus hook TOML
- configure distinct reviewer and implementor models without reading the code

- [ ] **Step 3: Commit as a coherent feature**

Stage the code, config, tests, and documentation together so the router lands as one coherent change.


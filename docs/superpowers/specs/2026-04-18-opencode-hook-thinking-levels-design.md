# OpenCode Hook — Thinking Level Support

**Date:** 2026-04-18
**Target:** `.claude/hooks/intercept-review-agents.py` + `.claude/hooks/opencode-router.toml`

## Problem

The OpenCode interceptor hook dispatches subagent tasks to an OpenCode server via `POST /session/{id}/message`, selecting a profile from `opencode-router.toml`. Profiles specify `agent`, `provider`, and `model`, but have no way to set a thinking/reasoning effort level. All dispatches run at the server's default thinking configuration (which varies by model). For code review and implementation tasks, the ability to request `high` or `max` thinking would improve output quality for hard tasks and reduce latency/cost for easy ones.

## Discovery

Investigation of OpenCode v1.4.6 source (`packages/opencode/src/session/prompt.ts:1704`) showed that `PromptInput` already accepts a normalized `variant: string` field. At request time, the server calls `ProviderTransform.variants(model)` (`packages/opencode/src/provider/transform.ts`) which returns a dict of supported variants keyed by level name (`low`, `medium`, `high`, `max`, and for some GPT-5 models `minimal`/`xhigh`). The server uses the caller's `variant` string as a lookup into that dict and applies the resulting provider-native payload fragment.

This means:
- Translation happens **server-side**. The hook sends a normalized level and OpenCode builds the provider-native shape (`thinking: {type: "adaptive", effort: ...}` for Anthropic 4.6, `reasoning_effort` for GPT-5, budget tokens for Anthropic 4.5).
- No mapping table is needed in the hook. If OpenCode adds a new level in a future version (e.g. ships `xhigh` for Opus 4.7), it works as soon as the server understands it.
- Unknown variants for a given model family are silently skipped by the server — no error, no feedback.

## Design

### Config surface

Add an optional `thinking` field to profiles:

```toml
[profiles.review_gpt54]
agent = "plan"
provider = "github-copilot"
model = "gpt-5.4"
thinking = "high"
timeout_seconds = 3600
```

Valid values: `low`, `medium`, `high`, `max`, `xhigh`. Absent = the field is omitted from the request body (current behavior preserved). Case is normalized to lowercase before validation — `"High"`, `"HIGH"`, and `"high"` all accepted.

### Validation behavior

**Warn-and-strip on unknown values.** If a profile specifies `thinking = "extreme"`, `_validate_profiles` emits a stderr warning and removes the field from the normalized profile. The hook continues to dispatch — the request goes out without a `variant` field, identical to no thinking config at all.

Warning format (stderr):
```
WARN: unknown thinking level 'extreme' in profile 'review_gpt54' — ignoring.
      Valid: low | medium | high | max | xhigh
      (absent = no thinking variant sent)
```

One warning per dispatch. No de-spamming in v1. User sees the warning, amends the TOML, next dispatch is clean. If repeat noise becomes annoying, v2 can add an mtime-keyed warning cache next to the TOML.

### Code changes

`.claude/hooks/intercept-review-agents.py` — three touch points, ~15 lines total:

1. **`_validate_profiles`** (~line 150): after existing provider/model checks, inspect `prof.get('thinking')`. If present and not in the allowed set, emit stderr warning and delete the key from `prof` in-place before returning. Mutation during validation is a minor break from the current pattern (which only collects errors), but it keeps the stripping colocated with the warning. Acceptable tradeoff for one call site.

2. **`_normalize_config`** (~line 180): carry `thinking` through alongside `agent`, `provider`, `model`, `timeout_seconds`:
   ```python
   profiles[name] = {
       'agent': prof['agent'],
       'provider': prof.get('provider'),
       'model': prof.get('model'),
       'thinking': prof.get('thinking'),
       'timeout_seconds': prof.get('timeout_seconds'),
   }
   ```

3. **`run_background_process`** (~line 570): after building `body` with `model` object, append `variant` if set:
   ```python
   if profile.get('thinking'):
       body['variant'] = profile['thinking']
   ```

No changes to `opencode-router.toml` itself (users add `thinking = "..."` opt-in per profile).

### Allowed set

```python
ALLOWED_THINKING_LEVELS = frozenset({'low', 'medium', 'high', 'max', 'xhigh'})
```

Defined as a module constant near the other validation helpers. If OpenCode adds a new level, update this constant in a follow-up.

## Testing

Extend `.claude/hooks/test_intercept_review_agents.py`:

1. **Validation — valid levels accepted.** Parametrized over the five allowed values: profile loads, `thinking` preserved.
2. **Validation — invalid level warn-and-strip.** Profile with `thinking = "extreme"` loads successfully, stderr contains the warning, normalized profile has no `thinking` key.
3. **Validation — absent thinking.** Profile without `thinking` loads, no warning, normalized profile has `thinking: None`.
4. **Request shape — variant sent.** Fake server records the POST body; assert `body['variant'] == 'high'` when the profile sets `thinking = "high"`.
5. **Request shape — variant absent.** Profile without `thinking`: assert `'variant'` not in body.

## Out of scope

- **Per-route thinking override.** Routes currently just name a profile; we don't add route-level `thinking =` that overrides the profile's value. If that need emerges, add it as a separate spec.
- **Model-family-aware validation** (e.g. reject `xhigh` for `claude-sonnet-4.6`). The allowed set is the hook's single source of truth; model-family compatibility is OpenCode's responsibility.
- **Warning de-spamming.** One stderr line per dispatch is acceptable.
- **xhigh for Opus 4.7.** Included in the allowed set anticipatorily, but OpenCode may not route it correctly until a future version integrates it. User is aware.

## Adopted live (in-scope expansion)

The initial plan scoped the `opencode-router.toml` edit as a manual post-merge step. During implementation the user directed adoption of `thinking = "high"` on the `review_gpt54` profile as part of the integration test (a live code-review dispatch through the modified hook), so the TOML change ships in this branch. This is a deliberate behavior change: every route resolving to `review_gpt54` (both `superpowers-code-review` and `superpowers-code-review-prefixed`) now requests high-effort thinking from the server. The `implementer_sonnet` profile remains unchanged.

## References

- Research report: `docs/research/Opencode-thinking-levels.md`
- OpenCode source probed at v1.4.6 (`dev` branch): `packages/opencode/src/session/prompt.ts:1704`, `packages/opencode/src/provider/transform.ts:368-747`
- Hook source: `.claude/hooks/intercept-review-agents.py`
- Existing router config: `.claude/hooks/opencode-router.toml`

# OpenCode Thinking-Level Mapping Report

## Question
How does OpenCode translate the simple TUI thinking controls (`low`, `medium`, `high`) into provider-specific payloads for diverse model APIs?

## Summary
OpenCode uses a centralized transformation layer in `packages/opencode/src/provider/transform.ts` to map a normalized thinking level into provider-specific request options. The mapping is done per provider and per model family, because different providers expect different parameter names and value shapes.

The key entry point is `ProviderTransform.variants(model)`, which returns a dictionary of supported thinking variants for that model. The TUI then selects one of these variants and sends the resulting provider-specific options in the request payload.

## Core implementation

### Variant mapping
- `packages/opencode/src/provider/transform.ts:368-747`
  - Defines `variants(model)` and returns provider-specific variant payloads.
  - Uses `model.api.npm`, `model.providerID`, `model.api.id`, and `model.release_date` to determine the correct shape.

### Provider option routing
- `packages/opencode/src/provider/transform.ts:922-960`
  - `providerOptions(model, options)` wraps the selected options under the correct provider key, including gateway special handling and Azure dual-key behavior.

### Default request options
- `packages/opencode/src/provider/transform.ts:749-878`
  - `options(input)` injects defaults like:
    - OpenAI / Copilot `store: false`
    - Google `thinkingConfig`
    - GPT-5 `reasoningEffort`, `reasoningSummary`, and `include`
    - Anthropic / Gemini / Bedrock thinking defaults where applicable

### Small/thinking-off variants
- `packages/opencode/src/provider/transform.ts:881-914`
  - `smallOptions(model)` provides the low/no-thinking variant for several provider families.

## Provider-specific thinking payloads

### Anthropic Sonnet 4.5 / Opus 4.5
- `packages/opencode/src/provider/transform.ts:554-586`
- `packages/opencode/src/provider/transform.ts:573-585`
- For Anthropic SDK:
  - `high` → `thinking: { type: "enabled", budgetTokens: 16000 }`
  - `max` → `thinking: { type: "enabled", budgetTokens: 31999 }`

### Anthropic Sonnet 4.6 / Opus 4.6
- `packages/opencode/src/provider/transform.ts:554-572`
- `packages/opencode/src/provider/transform.ts:559-569`
- For adaptive Anthropic models:
  - `low` / `medium` / `high` / `max` → `thinking: { type: "adaptive" }` plus `effort: "<level>"`

### GPT-5 family
- `packages/opencode/src/provider/transform.ts:523-552`
- `packages/opencode/src/provider/transform.ts:832-863`
- GPT-5 requests use:
  - `reasoningEffort`
  - `reasoningSummary: "auto"`
  - `include: ["reasoning.encrypted_content"]`
- OpenCode also sets:
  - `textVerbosity: "low"` for non-chat GPT-5.x models where supported

## Evidence from tests

### Anthropic 4.6 adaptive variants
- `packages/opencode/test/provider/transform.test.ts:2534-2580`
  - Confirms `claude-sonnet-4-6` returns `low`, `medium`, `high`, `max`
  - Confirms `result.high` equals:
    - `thinking: { type: "adaptive" }`
    - `effort: "high"`

### Anthropic 4.5 budget variants
- `packages/opencode/test/provider/transform.test.ts:2555-2579`
  - Confirms `claude-4` returns `high` and `max`
  - Confirms `high` uses:
    - `thinking: { type: "enabled", budgetTokens: 16000 }`
  - Confirms `max` uses:
    - `thinking: { type: "enabled", budgetTokens: 31999 }`

### Google Gemini thinking config
- `packages/opencode/test/provider/transform.test.ts:2624-2675`
  - Confirms Gemini 2.5 uses `thinkingConfig` with `thinkingBudget`
  - Confirms other Gemini models use `thinkingConfig` with `thinkingLevel`

### GPT-5 effort variants
- `packages/opencode/test/provider/transform.test.ts:2468-2531`
  - Confirms GPT-5 variants include `minimal`, `low`, `medium`, `high`, and sometimes `xhigh`
  - Confirms payloads include `reasoningEffort`, `reasoningSummary`, and `include`

## Request body shape examples

### Anthropic direct request shape
- `packages/console/app/src/routes/zen/util/provider/anthropic.ts:324-465`
  - `toAnthropicRequest()` maps generic messages into Anthropic’s `system` + `messages` format.
  - Final output includes:
    - `model`
    - `max_tokens`
    - `temperature`
    - `top_p`
    - `system`
    - `messages`
    - `stream`
    - `tools`
    - `tool_choice`
    - `stop_sequences`

### OpenAI-compatible request shape
- `packages/opencode/src/provider/sdk/copilot/chat/openai-compatible-chat-language-model.ts:193-218`
  - Sends JSON body to `/chat/completions`
  - Provider options are parsed and included in the final request args

## Important conclusion
OpenCode does **not** use one universal thinking field. Instead, it stores a normalized thinking choice in the UI and converts it at request time into the exact provider-native JSON fields needed by the selected model family.

That is why:
- Anthropic 4.5 uses token budgets
- Anthropic 4.6 uses adaptive thinking + effort
- GPT-5 uses reasoning-effort style parameters

## Recommended next step
If you want to replicate this manually against the OpenCode server endpoint, you should:
1. Pick the model family
2. Use the corresponding provider-native payload shape
3. Include the message body in the provider’s expected format
4. Send the selected thinking variant through the correct provider options namespace

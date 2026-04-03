# Plan: Add OpenAI Provider Support

Add support for OpenAI as an alternative to Claude/Anthropic, selectable via environment variable.

## Overview

The app is tightly coupled to the Anthropic SDK. Supporting OpenAI requires changes in three files, plus config and env updates.

---

## Changes Required

### 1. `app/config.py`

- Read `AI_PROVIDER` env var (`anthropic` or `openai`, default `anthropic`)
- Read `OPENAI_API_KEY` env var

### 2. `app/.azure-agent.example`

Add new optional fields:

```
# AI provider: "anthropic" (default) or "openai"
# AI_PROVIDER=anthropic

# Anthropic API key (used when AI_PROVIDER=anthropic)
ANTHROPIC_API_KEY=

# OpenAI API key (used when AI_PROVIDER=openai)
# OPENAI_API_KEY=
```

### 3. `app/tools/base.py`

Add an `openai_definition` property alongside the existing `definition` property.

- Anthropic format uses `"input_schema"` as the parameter key
- OpenAI format wraps the tool as `{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}`

```python
@property
def openai_definition(self) -> dict:
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        },
    }
```

### 4. `app/tools/__init__.py`

Update `definitions_for_groups()` to accept a `provider` argument and return the appropriate format.

- When `provider == "anthropic"`: current behavior (include `cache_control` on last definition, use `t.definition`)
- When `provider == "openai"`: use `t.openai_definition`, no `cache_control`

### 5. `app/agent.py`

This is the main refactor. Branch on provider for:

**Client initialization:**
- `anthropic`: `anthropic.Anthropic()`
- `openai`: `openai.OpenAI()`

**API calls (`_create_with_retry`):**
- `anthropic`: `client.messages.create(model=..., system=..., tools=..., messages=...)`
- `openai`: `client.chat.completions.create(model=..., tools=..., messages=...)` with system prompt prepended as `{"role": "system", "content": ...}` in the messages list

**Response parsing:**
- Anthropic: `response.content` → list of typed blocks (`type == "text"`, `type == "tool_use"`)
- OpenAI: `response.choices[0].message` → `.content` for text, `.tool_calls` for tool calls

**Stop reasons:**
- Anthropic: `"end_turn"` (text response), `"tool_use"` (tool call)
- OpenAI: `"stop"` (text response), `"tool_calls"` (tool call)

**Tool results:**
- Anthropic: `{"type": "tool_result", "tool_use_id": ..., "content": ...}` appended as a `user` message
- OpenAI: `{"role": "tool", "tool_call_id": ..., "content": ...}` appended as individual messages

**Error handling:**
- Anthropic: `anthropic.RateLimitError`
- OpenAI: `openai.RateLimitError`

**Classifier (`_classify_groups`):**
- `anthropic`: current behavior using Haiku (`claude-haiku-4-5`)
- `openai`: use `gpt-4o-mini` with equivalent prompt; or fall back to returning all groups

**Model constants:**
```python
ANTHROPIC_MODEL = "claude-opus-4-6"
ANTHROPIC_CLASSIFIER_MODEL = "claude-haiku-4-5"
OPENAI_MODEL = "gpt-4o"
OPENAI_CLASSIFIER_MODEL = "gpt-4o-mini"
```

---

## Notes

- The Anthropic `cache_control` feature (prompt caching) has no OpenAI equivalent — omit it for OpenAI
- The OpenAI system prompt goes in the messages array as `{"role": "system", ...}` rather than a separate parameter
- OpenAI tool results are individual messages with `role: "tool"`, not batched inside a single `role: "user"` message
- The `destructive` field on `Tool` and all Azure SDK tool logic is provider-agnostic — no changes needed there

"""Azure agent — multi-turn conversation loop with tool use."""
import json
import time
import anthropic
import openai
from prompts import SYSTEM_PROMPT
from tools import TOOL_REGISTRY, GROUP_DESCRIPTIONS, definitions_for_groups
from config import (
    DEFAULT_SUBSCRIPTION_ID,
    AI_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_API_VERSION,
    OPENAI_DEPLOYMENT_NAME,
)

ANTHROPIC_MODEL = "claude-opus-4-6"
ANTHROPIC_CLASSIFIER_MODEL = "claude-haiku-4-5"
OPENAI_MODEL = "gpt-4o"
OPENAI_CLASSIFIER_MODEL = "gpt-4o-mini"
MAX_TOKENS = 4096

_CACHED_SYSTEM = [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]

_CLASSIFIER_SYSTEM = (
    "You select which Azure service groups are needed to answer a user request. "
    "Respond with a JSON array of group names — only from the list provided. "
    "Return an empty array [] if the request needs no specialised tools (e.g. greetings). "
    "Return only the JSON array, no other text."
)


class AzureAgent:
    def __init__(self) -> None:
        self._provider = AI_PROVIDER
        if self._provider == "openai":
            if OPENAI_BASE_URL:
                self.client = openai.AzureOpenAI(
                    azure_endpoint=OPENAI_BASE_URL,
                    api_key=OPENAI_API_KEY or None,
                    api_version=OPENAI_API_VERSION or "2024-10-21",
                )
            else:
                self.client = openai.OpenAI(api_key=OPENAI_API_KEY or None)
            self._model = OPENAI_DEPLOYMENT_NAME or OPENAI_MODEL
            self._classifier_model = OPENAI_CLASSIFIER_MODEL
        else:
            self.client = anthropic.Anthropic()
            self._model = ANTHROPIC_MODEL
            self._classifier_model = ANTHROPIC_CLASSIFIER_MODEL

        self.messages: list[dict] = []
        self._active_groups: set[str] = set()

    def _classify_groups(self, user_input: str) -> set[str]:
        """Use a fast/cheap model to pick which tool groups the request needs."""
        group_list = "\n".join(
            f"- {name}: {desc}" for name, desc in GROUP_DESCRIPTIONS.items()
        )
        prompt = (
            f"User request: {user_input}\n\n"
            f"Available groups:\n{group_list}\n\n"
            "Which groups are needed? Return a JSON array of group names."
        )
        try:
            if self._provider == "openai":
                resp = self.client.chat.completions.create(
                    model=self._classifier_model,
                    max_tokens=64,
                    messages=[
                        {"role": "system", "content": _CLASSIFIER_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                )
                text = resp.choices[0].message.content or "[]"
            else:
                resp = self.client.messages.create(
                    model=self._classifier_model,
                    max_tokens=64,
                    system=_CLASSIFIER_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = next((b.text for b in resp.content if b.type == "text"), "[]")
            groups = json.loads(text)
            return {g for g in groups if g in GROUP_DESCRIPTIONS}
        except Exception:
            return set(GROUP_DESCRIPTIONS.keys())

    def chat(self, user_input: str) -> str:
        """Send a user message and return the final assistant response."""
        new_groups = self._classify_groups(user_input)
        self._active_groups |= new_groups

        tool_defs = definitions_for_groups(
            list(self._active_groups), provider=self._provider
        )

        if not self.messages and DEFAULT_SUBSCRIPTION_ID:
            user_input = (
                f"[Default subscription: {DEFAULT_SUBSCRIPTION_ID}] {user_input}"
            )

        self.messages.append({"role": "user", "content": user_input})

        while True:
            response = self._create_with_retry(tool_defs)

            if self._provider == "openai":
                choice = response.choices[0]
                message = choice.message
                stop_reason = choice.finish_reason

                assistant_msg: dict = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ]
                self.messages.append(assistant_msg)

                if stop_reason == "stop":
                    return message.content or "(no text response)"

                if stop_reason != "tool_calls":
                    return f"[Unexpected stop reason: {stop_reason}]"

                for tc in message.tool_calls:
                    tool_input = json.loads(tc.function.arguments)
                    result = self._execute_tool(tc.function.name, tool_input)
                    self.messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result}
                    )

            else:  # anthropic
                self.messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    return next(
                        (b.text for b in response.content if b.type == "text"),
                        "(no text response)",
                    )

                if response.stop_reason != "tool_use":
                    return f"[Unexpected stop reason: {response.stop_reason}]"

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                self.messages.append({"role": "user", "content": tool_results})

    def _create_with_retry(self, tool_defs: list[dict], max_retries: int = 5):
        """Call the model API with exponential backoff on rate limit errors."""
        rate_limit_exc = (
            openai.RateLimitError if self._provider == "openai"
            else anthropic.RateLimitError
        )
        delay = 10.0
        for attempt in range(max_retries):
            try:
                if self._provider == "openai":
                    messages_with_system = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *self.messages,
                    ]
                    return self.client.chat.completions.create(
                        model=self._model,
                        max_tokens=MAX_TOKENS,
                        tools=tool_defs,
                        messages=messages_with_system,
                    )
                else:
                    return self.client.messages.create(
                        model=self._model,
                        max_tokens=MAX_TOKENS,
                        system=_CACHED_SYSTEM,
                        tools=tool_defs,
                        messages=self.messages,
                    )
            except rate_limit_exc as exc:
                if attempt == max_retries - 1:
                    raise
                retry_after = None
                if hasattr(exc, "response") and exc.response is not None:
                    retry_after = exc.response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else delay
                print(
                    f"\n[rate limited — waiting {wait:.0f}s before retry "
                    f"{attempt + 1}/{max_retries}]"
                )
                time.sleep(wait)
                delay = min(delay * 2, 120.0)

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        tool = TOOL_REGISTRY.get(tool_name)
        if tool is None:
            return f"[Error] Unknown tool: {tool_name}"
        try:
            return tool.execute(**tool_input)
        except TypeError as exc:
            return f"[Error] Invalid arguments for {tool_name}: {exc}"

    def reset(self) -> None:
        """Clear conversation history and active group state."""
        self.messages = []
        self._active_groups = set()

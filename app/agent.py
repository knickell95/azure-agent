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

# ---------------------------------------------------------------------------
# Model constants — classifier uses a smaller/cheaper model than the main one
# to keep latency and cost down for the group-selection step.
# ---------------------------------------------------------------------------
ANTHROPIC_MODEL = "claude-opus-4-6"
ANTHROPIC_CLASSIFIER_MODEL = "claude-haiku-4-5"
OPENAI_MODEL = "gpt-4o"
OPENAI_CLASSIFIER_MODEL = "gpt-4o-mini"
MAX_TOKENS = 4096

# Wrap the system prompt with cache_control so Anthropic caches it across turns,
# reducing token cost on long conversations. OpenAI has no equivalent, so this
# structure is only used on the Anthropic path.
_CACHED_SYSTEM = [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]

# Instructions for the classifier model — kept terse so the small model stays
# on task and returns only the JSON array we need.
_CLASSIFIER_SYSTEM = (
    "You select which Azure service groups are needed to answer a user request. "
    "Respond with a JSON array of group names — only from the list provided. "
    "Return an empty array [] if the request needs no specialised tools (e.g. greetings). "
    "Return only the JSON array, no other text."
)


class AzureAgent:
    def __init__(self) -> None:
        # Select the AI provider and build the appropriate client.
        # For OpenAI, prefer AzureOpenAI when a base URL is configured (Azure AI
        # Foundry / Azure OpenAI Service), otherwise fall back to the public
        # OpenAI API. api_key is passed as None when empty so the SDK reads
        # OPENAI_API_KEY from the environment automatically.
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
            # Azure OpenAI uses the deployment name as the model identifier.
            self._model = OPENAI_DEPLOYMENT_NAME or OPENAI_MODEL
            self._classifier_model = OPENAI_CLASSIFIER_MODEL
        else:
            self.client = anthropic.Anthropic()
            self._model = ANTHROPIC_MODEL
            self._classifier_model = ANTHROPIC_CLASSIFIER_MODEL

        # Full conversation history sent to the model on every turn.
        self.messages: list[dict] = []
        # Tool groups loaded so far — unions across turns so follow-up questions
        # (e.g. "now show me the disks") keep the previously loaded tools active.
        self._active_groups: set[str] = set()

    def _classify_groups(self, user_input: str) -> set[str]:
        """Use a fast/cheap model to pick which tool groups the request needs."""
        # Build the group menu from the registry so it stays in sync as tools are added.
        group_list = "\n".join(
            f"- {name}: {desc}" for name, desc in GROUP_DESCRIPTIONS.items()
        )
        prompt = (
            f"User request: {user_input}\n\n"
            f"Available groups:\n{group_list}\n\n"
            "Which groups are needed? Return a JSON array of group names."
        )
        try:
            # OpenAI requires the system prompt inside the messages array;
            # Anthropic accepts it as a separate top-level parameter.
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
            # Filter out any group names the model hallucinated.
            return {g for g in groups if g in GROUP_DESCRIPTIONS}
        except Exception:
            # On any failure (network, bad JSON, etc.) load all groups so the
            # main model always has the tools it might need.
            return set(GROUP_DESCRIPTIONS.keys())

    def chat(self, user_input: str) -> str:
        """Send a user message and return the final assistant response."""
        # Classify which tool groups this turn requires, then union with the
        # groups already active so context from prior turns is preserved.
        new_groups = self._classify_groups(user_input)
        self._active_groups |= new_groups

        tool_defs = definitions_for_groups(
            list(self._active_groups), provider=self._provider
        )

        # On the very first turn, prepend the default subscription ID so the
        # model doesn't need to ask the user for it.
        if not self.messages and DEFAULT_SUBSCRIPTION_ID:
            user_input = (
                f"[Default subscription: {DEFAULT_SUBSCRIPTION_ID}] {user_input}"
            )

        self.messages.append({"role": "user", "content": user_input})

        # Agentic loop — continues until the model returns a plain text response
        # (no more tool calls pending).
        while True:
            response = self._create_with_retry(tool_defs)

            if self._provider == "openai":
                choice = response.choices[0]
                message = choice.message
                stop_reason = choice.finish_reason

                # Store the assistant turn. Tool calls must be included in the
                # history as plain dicts (not SDK objects) so they round-trip
                # correctly when sent back to the API on the next iteration.
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

                # "stop" means the model finished with a text response.
                if stop_reason == "stop":
                    return message.content or "(no text response)"

                if stop_reason != "tool_calls":
                    return f"[Unexpected stop reason: {stop_reason}]"

                # Execute each requested tool and append results as individual
                # "tool" role messages — OpenAI requires one message per call,
                # unlike Anthropic which batches them inside a single user turn.
                for tc in message.tool_calls:
                    tool_input = json.loads(tc.function.arguments)
                    result = self._execute_tool(tc.function.name, tool_input)
                    self.messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result}
                    )

            else:  # anthropic
                # Anthropic SDK returns typed content block objects; store them
                # directly — the SDK serialises them when building the next request.
                self.messages.append({"role": "assistant", "content": response.content})

                # "end_turn" means the model finished with a text response.
                if response.stop_reason == "end_turn":
                    return next(
                        (b.text for b in response.content if b.type == "text"),
                        "(no text response)",
                    )

                if response.stop_reason != "tool_use":
                    return f"[Unexpected stop reason: {response.stop_reason}]"

                # Execute all tool calls in this turn and batch the results into
                # a single user message — Anthropic's API requires this format.
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
        # Resolve the correct exception type up front so the except clause can
        # use a plain variable reference rather than branching inside the handler.
        rate_limit_exc = (
            openai.RateLimitError if self._provider == "openai"
            else anthropic.RateLimitError
        )
        delay = 10.0
        for attempt in range(max_retries):
            try:
                if self._provider == "openai":
                    # OpenAI has no separate system parameter — prepend it as the
                    # first message every call. self.messages stores only user/
                    # assistant/tool turns, so there's no risk of duplication.
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
                    # Anthropic accepts the system prompt separately and caches it
                    # via the cache_control block defined at module level.
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
                # Honour the Retry-After header when present; otherwise use
                # the local exponential backoff value.
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
        # Look up the tool in the registry rather than importing each module
        # directly, so the agent doesn't need to know which module owns each tool.
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

"""Azure agent — multi-turn conversation loop with tool use."""
import json
import time
import anthropic
from prompts import SYSTEM_PROMPT
from tools import TOOL_REGISTRY, GROUP_DESCRIPTIONS, definitions_for_groups
from config import DEFAULT_SUBSCRIPTION_ID

MODEL = "claude-opus-4-6"
CLASSIFIER_MODEL = "claude-haiku-4-5"
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
        self.client = anthropic.Anthropic()
        self.messages: list[dict] = []
        # Track active groups across turns so follow-up questions keep context.
        # E.g. "now show me the disks" after a VM question keeps "compute" active.
        self._active_groups: set[str] = set()
        self._build_initial_context()

    def _build_initial_context(self) -> None:
        """If a default subscription is configured, inject it via the system prompt
        rather than history messages, so it doesn't consume history token budget."""
        pass  # handled by SYSTEM_PROMPT + config.DEFAULT_SUBSCRIPTION_ID injection below

    def _classify_groups(self, user_input: str) -> set[str]:
        """Use Haiku to pick which tool groups the request needs."""
        group_list = "\n".join(
            f"- {name}: {desc}" for name, desc in GROUP_DESCRIPTIONS.items()
        )
        prompt = (
            f"User request: {user_input}\n\n"
            f"Available groups:\n{group_list}\n\n"
            "Which groups are needed? Return a JSON array of group names."
        )
        try:
            resp = self.client.messages.create(
                model=CLASSIFIER_MODEL,
                max_tokens=64,
                system=_CLASSIFIER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "[]")
            groups = json.loads(text)
            return {g for g in groups if g in GROUP_DESCRIPTIONS}
        except Exception:
            # On any failure, fall back to all groups
            return set(GROUP_DESCRIPTIONS.keys())

    def chat(self, user_input: str) -> str:
        """Send a user message and return the final assistant response."""
        # Classify which groups this turn needs, then union with active groups
        # so follow-up questions retain context from the previous turn.
        new_groups = self._classify_groups(user_input)
        self._active_groups |= new_groups

        tool_defs = definitions_for_groups(list(self._active_groups))

        # Inject default subscription context into the first user message if set
        if not self.messages and DEFAULT_SUBSCRIPTION_ID:
            user_input = (
                f"[Default subscription: {DEFAULT_SUBSCRIPTION_ID}] {user_input}"
            )

        self.messages.append({"role": "user", "content": user_input})

        while True:
            response = self._create_with_retry(tool_defs)
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

    def _create_with_retry(
        self, tool_defs: list[dict], max_retries: int = 5
    ) -> anthropic.types.Message:
        """Call messages.create with exponential backoff on rate limit errors."""
        delay = 10.0
        for attempt in range(max_retries):
            try:
                return self.client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=_CACHED_SYSTEM,
                    tools=tool_defs,
                    messages=self.messages,
                )
            except anthropic.RateLimitError as exc:
                if attempt == max_retries - 1:
                    raise
                retry_after = exc.response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else delay
                print(f"\n[rate limited — waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}]")
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

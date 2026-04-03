"""Unit tests for AzureAgent (agent.py)."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers to build fake Anthropic response objects
# ---------------------------------------------------------------------------

def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, input_data, block_id="tu_001"):
    return SimpleNamespace(type="tool_use", name=name, input=input_data, id=block_id)


def _message(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _rate_limit_error():
    import anthropic
    resp = MagicMock()
    resp.headers = {}
    return anthropic.RateLimitError("rate limited", response=resp, body={})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_anthropic(monkeypatch):
    """Replace anthropic.Anthropic with a MagicMock for every test."""
    mock_client = MagicMock()
    monkeypatch.setattr("anthropic.Anthropic", lambda: mock_client)
    return mock_client


@pytest.fixture(autouse=True)
def mock_default_subscription(monkeypatch):
    monkeypatch.setattr("config.DEFAULT_SUBSCRIPTION_ID", "")


@pytest.fixture()
def agent(mock_anthropic):
    from agent import AzureAgent
    return AzureAgent()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_starts_with_empty_history(self, agent):
        assert agent.messages == []

    def test_starts_with_no_active_groups(self, agent):
        assert agent._active_groups == set()


# ---------------------------------------------------------------------------
# _classify_groups
# ---------------------------------------------------------------------------

class TestClassifyGroups:
    def _setup_classifier_response(self, mock_client, groups_json):
        mock_resp = MagicMock()
        mock_resp.content = [SimpleNamespace(type="text", text=groups_json)]
        mock_client.messages.create.return_value = mock_resp

    def test_returns_valid_groups(self, agent, mock_anthropic):
        self._setup_classifier_response(mock_anthropic, '["compute", "network"]')
        result = agent._classify_groups("list my VMs")
        assert result == {"compute", "network"}

    def test_ignores_unknown_groups(self, agent, mock_anthropic):
        self._setup_classifier_response(mock_anthropic, '["compute", "dragons"]')
        result = agent._classify_groups("list VMs and dragons")
        assert result == {"compute"}

    def test_returns_empty_set_for_greeting(self, agent, mock_anthropic):
        self._setup_classifier_response(mock_anthropic, "[]")
        result = agent._classify_groups("hello")
        assert result == set()

    def test_falls_back_to_all_groups_on_api_error(self, agent, mock_anthropic):
        mock_anthropic.messages.create.side_effect = Exception("API down")
        from tools import GROUP_DESCRIPTIONS
        result = agent._classify_groups("something")
        assert result == set(GROUP_DESCRIPTIONS.keys())

    def test_falls_back_to_all_groups_on_invalid_json(self, agent, mock_anthropic):
        self._setup_classifier_response(mock_anthropic, "not json")
        from tools import GROUP_DESCRIPTIONS
        result = agent._classify_groups("something")
        assert result == set(GROUP_DESCRIPTIONS.keys())


# ---------------------------------------------------------------------------
# chat — end_turn (simple text response)
# ---------------------------------------------------------------------------

class TestChatEndTurn:
    def test_returns_assistant_text(self, agent, mock_anthropic):
        mock_anthropic.messages.create.return_value = _message(
            [_text_block("Here are your VMs.")], "end_turn"
        )
        # Patch classifier to return empty set so we don't call create twice unexpectedly
        agent._classify_groups = MagicMock(return_value=set())
        result = agent.chat("list VMs")
        assert result == "Here are your VMs."

    def test_appends_user_and_assistant_messages(self, agent, mock_anthropic):
        mock_anthropic.messages.create.return_value = _message(
            [_text_block("Done.")], "end_turn"
        )
        agent._classify_groups = MagicMock(return_value=set())
        agent.chat("hello")
        assert agent.messages[0] == {"role": "user", "content": "hello"}
        assert agent.messages[1] == {"role": "assistant", "content": [_text_block("Done.")]}

    def test_no_text_block_returns_fallback(self, agent, mock_anthropic):
        mock_anthropic.messages.create.return_value = _message([], "end_turn")
        agent._classify_groups = MagicMock(return_value=set())
        result = agent.chat("hello")
        assert result == "(no text response)"

    def test_unexpected_stop_reason_returns_message(self, agent, mock_anthropic):
        mock_anthropic.messages.create.return_value = _message([], "max_tokens")
        agent._classify_groups = MagicMock(return_value=set())
        result = agent.chat("hello")
        assert "max_tokens" in result


# ---------------------------------------------------------------------------
# chat — tool_use loop
# ---------------------------------------------------------------------------

class TestChatToolUse:
    def test_executes_tool_and_returns_final_response(self, agent, mock_anthropic):
        tool_call_response = _message(
            [_tool_use_block("list_subscriptions", {})], "tool_use"
        )
        final_response = _message([_text_block("You have 2 subscriptions.")], "end_turn")
        mock_anthropic.messages.create.side_effect = [tool_call_response, final_response]

        agent._classify_groups = MagicMock(return_value=set())
        agent._execute_tool = MagicMock(return_value="- sub1\n- sub2")

        result = agent.chat("list subscriptions")
        assert result == "You have 2 subscriptions."
        agent._execute_tool.assert_called_once_with("list_subscriptions", {})

    def test_tool_result_appended_as_user_message(self, agent, mock_anthropic):
        tool_call_response = _message(
            [_tool_use_block("list_subscriptions", {}, block_id="tu_42")], "tool_use"
        )
        final_response = _message([_text_block("Done.")], "end_turn")
        mock_anthropic.messages.create.side_effect = [tool_call_response, final_response]

        agent._classify_groups = MagicMock(return_value=set())
        agent._execute_tool = MagicMock(return_value="results")

        agent.chat("go")
        tool_result_msg = agent.messages[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "tu_42"
        assert tool_result_msg["content"][0]["content"] == "results"


# ---------------------------------------------------------------------------
# _execute_tool
# ---------------------------------------------------------------------------

class TestExecuteTool:
    def test_calls_registered_tool(self, agent):
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "ok"
        with patch.dict("agent.TOOL_REGISTRY", {"my_tool": mock_tool}):
            result = agent._execute_tool("my_tool", {"a": 1})
        mock_tool.execute.assert_called_once_with(a=1)
        assert result == "ok"

    def test_unknown_tool_returns_error(self, agent):
        result = agent._execute_tool("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_type_error_returns_error(self, agent):
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = TypeError("missing arg")
        with patch.dict("agent.TOOL_REGISTRY", {"bad_tool": mock_tool}):
            result = agent._execute_tool("bad_tool", {})
        assert "Invalid arguments" in result


# ---------------------------------------------------------------------------
# _create_with_retry
# ---------------------------------------------------------------------------

class TestRetry:
    def test_returns_immediately_on_success(self, agent, mock_anthropic):
        mock_response = _message([_text_block("ok")], "end_turn")
        mock_anthropic.messages.create.return_value = mock_response
        result = agent._create_with_retry([])
        assert result is mock_response
        assert mock_anthropic.messages.create.call_count == 1

    def test_retries_on_rate_limit_error(self, agent, mock_anthropic):
        good_response = _message([_text_block("ok")], "end_turn")
        mock_anthropic.messages.create.side_effect = [
            _rate_limit_error(),
            good_response,
        ]
        with patch("time.sleep"):
            result = agent._create_with_retry([])
        assert result is good_response
        assert mock_anthropic.messages.create.call_count == 2

    def test_raises_after_max_retries(self, agent, mock_anthropic):
        import anthropic
        mock_anthropic.messages.create.side_effect = _rate_limit_error()
        with patch("time.sleep"):
            with pytest.raises(anthropic.RateLimitError):
                agent._create_with_retry([], max_retries=3)
        assert mock_anthropic.messages.create.call_count == 3


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_clears_messages_and_groups(self, agent, mock_anthropic):
        mock_anthropic.messages.create.return_value = _message(
            [_text_block("hi")], "end_turn"
        )
        agent._classify_groups = MagicMock(return_value={"compute"})
        agent.chat("list VMs")

        assert agent.messages != []
        assert agent._active_groups != set()

        agent.reset()
        assert agent.messages == []
        assert agent._active_groups == set()


# ---------------------------------------------------------------------------
# Default subscription injection
# ---------------------------------------------------------------------------

class TestDefaultSubscription:
    def test_injects_subscription_into_first_message(self, mock_anthropic, monkeypatch):
        monkeypatch.setattr("config.DEFAULT_SUBSCRIPTION_ID", "sub-abc-123")
        # Re-import after patching
        import importlib
        import agent as agent_module
        importlib.reload(agent_module)

        from agent import AzureAgent
        a = AzureAgent()
        a._classify_groups = MagicMock(return_value=set())
        mock_anthropic.messages.create.return_value = _message(
            [_text_block("ok")], "end_turn"
        )
        a.chat("hello")
        first_user_content = a.messages[0]["content"]
        assert "sub-abc-123" in first_user_content

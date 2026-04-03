"""Unit tests for the Tool base class and tool registry (tools/base.py, tools/__init__.py)."""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------

class TestToolDefinition:
    def _make_tool(self, **kwargs):
        from tools.base import Tool
        defaults = dict(
            name="my_tool",
            description="Does a thing.",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            func=MagicMock(return_value="result"),
        )
        defaults.update(kwargs)
        return Tool(**defaults)

    def test_definition_contains_name(self):
        t = self._make_tool(name="do_thing")
        assert t.definition["name"] == "do_thing"

    def test_definition_contains_description(self):
        t = self._make_tool(description="My description.")
        assert t.definition["description"] == "My description."

    def test_definition_contains_input_schema(self):
        schema = {"type": "object", "properties": {}, "required": []}
        t = self._make_tool(input_schema=schema)
        assert t.definition["input_schema"] == schema

    def test_definition_has_no_extra_keys(self):
        t = self._make_tool()
        assert set(t.definition.keys()) == {"name", "description", "input_schema"}

    def test_destructive_defaults_to_false(self):
        t = self._make_tool()
        assert t.destructive is False

    def test_destructive_can_be_set_true(self):
        t = self._make_tool(destructive=True)
        assert t.destructive is True


class TestToolExecute:
    def _make_tool(self, func):
        from tools.base import Tool
        return Tool(
            name="t", description="d",
            input_schema={"type": "object", "properties": {}, "required": []},
            func=func,
        )

    def test_passes_kwargs_to_func(self):
        func = MagicMock(return_value="ok")
        t = self._make_tool(func)
        result = t.execute(x="hello", y=42)
        func.assert_called_once_with(x="hello", y=42)
        assert result == "ok"

    def test_returns_func_result(self):
        t = self._make_tool(lambda: "my output")
        assert t.execute() == "my output"

    def test_catches_exception_and_returns_error_string(self):
        def boom():
            raise ValueError("something went wrong")
        t = self._make_tool(boom)
        result = t.execute()
        assert "[Azure error]" in result
        assert "ValueError" in result
        assert "something went wrong" in result

    def test_exception_message_includes_exception_type(self):
        def boom():
            raise RuntimeError("bad state")
        t = self._make_tool(boom)
        result = t.execute()
        assert "RuntimeError" in result


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_all_tools_have_unique_names(self):
        from tools import TOOL_REGISTRY, ALL_TOOLS
        assert len(TOOL_REGISTRY) == len(ALL_TOOLS), "Duplicate tool names detected"

    def test_registry_keys_match_tool_names(self):
        from tools import TOOL_REGISTRY
        for name, tool in TOOL_REGISTRY.items():
            assert tool.name == name

    def test_core_tools_always_present(self):
        from tools import TOOL_REGISTRY
        # Core resource tools that should always be available
        assert "list_subscriptions" in TOOL_REGISTRY
        assert "list_resource_groups" in TOOL_REGISTRY

    def test_all_group_names_exist_in_tool_groups(self):
        from tools import GROUP_DESCRIPTIONS, TOOL_GROUPS
        for name in GROUP_DESCRIPTIONS:
            assert name in TOOL_GROUPS, f"Group '{name}' in GROUP_DESCRIPTIONS but not in TOOL_GROUPS"


# ---------------------------------------------------------------------------
# definitions_for_groups
# ---------------------------------------------------------------------------

class TestDefinitionsForGroups:
    def test_always_includes_core_tools(self):
        from tools import definitions_for_groups, TOOL_GROUPS
        core_names = {t.name for t in TOOL_GROUPS["core"]}
        defs = definitions_for_groups([])
        def_names = {d["name"] for d in defs}
        assert core_names.issubset(def_names)

    def test_includes_requested_group(self):
        from tools import definitions_for_groups, TOOL_GROUPS
        compute_names = {t.name for t in TOOL_GROUPS["compute"]}
        defs = definitions_for_groups(["compute"])
        def_names = {d["name"] for d in defs}
        assert compute_names.issubset(def_names)

    def test_ignores_unknown_group_names(self):
        from tools import definitions_for_groups
        # Should not raise; unknown groups are silently skipped
        defs = definitions_for_groups(["dragons"])
        assert isinstance(defs, list)

    def test_cache_control_on_last_definition(self):
        from tools import definitions_for_groups
        defs = definitions_for_groups([])
        assert "cache_control" in defs[-1]
        assert defs[-1]["cache_control"] == {"type": "ephemeral"}

    def test_cache_control_only_on_last_definition(self):
        from tools import definitions_for_groups
        defs = definitions_for_groups(["compute"])
        for d in defs[:-1]:
            assert "cache_control" not in d

    def test_does_not_add_core_twice_when_core_in_group_list(self):
        from tools import definitions_for_groups, TOOL_GROUPS
        # "core" is always included; passing it explicitly should not duplicate
        defs_without = definitions_for_groups([])
        defs_with = definitions_for_groups(["core"])
        names_without = [d["name"] for d in defs_without]
        names_with = [d["name"] for d in defs_with]
        assert names_without == names_with

    def test_multiple_groups_combined(self):
        from tools import definitions_for_groups, TOOL_GROUPS
        compute_names = {t.name for t in TOOL_GROUPS["compute"]}
        storage_names = {t.name for t in TOOL_GROUPS["storage"]}
        defs = definitions_for_groups(["compute", "storage"])
        def_names = {d["name"] for d in defs}
        assert compute_names.issubset(def_names)
        assert storage_names.issubset(def_names)

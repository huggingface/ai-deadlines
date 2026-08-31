"""Last-turn search-tool budget nudge / deny helpers."""

from agents.pipeline_utils import (
    BUDGET_EXHAUSTED_MESSAGE,
    ToolBudgetState,
    is_search_tool,
)


def test_search_tool_detection():
    assert is_search_tool("WebSearch")
    assert is_search_tool("WebFetch")
    assert is_search_tool("mcp__exa__web_search_exa")
    assert is_search_tool("exa_search")
    assert not is_search_tool("Read")
    assert not is_search_tool("Bash")
    assert not is_search_tool("")


def test_nudge_on_max_turns_minus_one():
    state = ToolBudgetState(max_turns=12)
    for _ in range(10):
        assert state.on_post_tool_use("WebSearch") is None
    extra = state.on_post_tool_use("WebFetch")
    assert extra == BUDGET_EXHAUSTED_MESSAGE
    assert state.nudge_sent is True
    assert state.search_uses == 11
    assert state.on_post_tool_use("WebSearch") is None


def test_deny_after_nudge():
    state = ToolBudgetState(max_turns=12)
    for _ in range(11):
        state.on_post_tool_use("WebSearch")
    assert state.should_deny_pre_tool_use("WebFetch") is True
    assert state.should_deny_pre_tool_use("Read") is False


def test_non_search_tools_do_not_count():
    state = ToolBudgetState(max_turns=3)
    assert state.on_post_tool_use("Read") is None
    assert state.on_post_tool_use("Read") is None
    assert state.on_post_tool_use("WebSearch") is None
    extra = state.on_post_tool_use("WebFetch")
    assert extra == BUDGET_EXHAUSTED_MESSAGE
    assert state.search_uses == 2


def test_aggregation_budget_of_eight():
    state = ToolBudgetState(max_turns=8)
    for _ in range(6):
        assert state.on_post_tool_use("WebSearch") is None
    assert state.on_post_tool_use("WebSearch") == BUDGET_EXHAUSTED_MESSAGE
    assert state.should_deny_pre_tool_use("WebSearch") is True

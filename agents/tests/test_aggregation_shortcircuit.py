"""P6: skip aggregation unless a retrieval agent proposed an update."""

from agents.pipeline_utils import (
    retrieval_short_circuit,
    should_skip_aggregation,
)


def test_skip_when_all_false():
    results = [
        {"requires_update": False, "reasoning": "CFP not published"},
        {"requires_update": False, "reasoning": "page unreadable"},
        {"requires_update": False, "reasoning": "no 2027 dates"},
    ]
    assert should_skip_aggregation(results) is True
    out = retrieval_short_circuit(results, total_cost=0.12)
    assert out["status"] == "no_changes"
    assert out["skipped_aggregation"] is True
    assert "page unreadable" in out["reasoning"] or "CFP" in out["reasoning"] or "2027" in out["reasoning"]


def test_skip_when_false_plus_empty():
    results = [
        {"requires_update": False, "reasoning": "already up to date"},
        {},
        {"error": "silent exit"},
    ]
    assert should_skip_aggregation(results) is True
    out = retrieval_short_circuit(results, total_cost=0.05)
    assert out["status"] == "no_changes"
    assert out["reasoning"] == "already up to date"


def test_zero_structured_results_is_no_changes():
    results = [{}, {"error": "error_max_turns"}, {"status": "unknown"}]
    assert should_skip_aggregation(results) is True
    out = retrieval_short_circuit(results, total_cost=0.2)
    assert out["status"] == "no_changes"
    assert out["reasoning"] == "retrieval produced no structured output"


def test_all_timeouts_surface_as_timeout_not_no_changes():
    results = [
        {"status": "timeout", "error": "agent wall-clock timeout after 300s"},
        {"status": "timeout", "error": "agent wall-clock timeout after 300s"},
        {"status": "timeout", "error": "agent wall-clock timeout after 300s"},
    ]
    assert should_skip_aggregation(results) is True
    out = retrieval_short_circuit(results, total_cost=0.01)
    assert out["status"] == "timeout"
    assert out["error"]


def test_do_not_skip_when_someone_proposed_update():
    results = [
        {"requires_update": False, "reasoning": "no"},
        {"requires_update": True, "reasoning": "new 2027 CFP", "updated_yaml": "x: 1"},
        {},
    ]
    assert should_skip_aggregation(results) is False

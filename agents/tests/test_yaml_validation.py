"""P8: YAML validation before push."""

from datetime import date

import pytest

from agents.pipeline_utils import YamlValidationError, validate_updated_yaml

CURRENT = """\
- title: Demo
  year: 2025
  id: demo25
  date: January 1 - 2, 2025
  start: '2025-01-01'
  end: '2025-01-02'
  timezone: AoE
- title: Demo
  year: 2027
  id: demo27
  date: January 1 - 2, 2027
  start: '2027-01-01'
  end: '2027-01-02'
  timezone: AoE
"""


def test_valid_yaml_with_untouched_past_year_passes():
    updated = CURRENT.replace("id: demo27", "id: demo27\n  city: Paris")
    validate_updated_yaml(CURRENT, updated, today=date(2026, 8, 28))


def test_invalid_yaml_raises():
    with pytest.raises(YamlValidationError, match="does not parse"):
        validate_updated_yaml(CURRENT, "this: [unterminated", today=date(2026, 8, 28))


def test_bad_timezone_utc_minus_12_rejected():
    with pytest.raises(YamlValidationError, match="AoE"):
        lines = CURRENT.splitlines(keepends=True)
        lines[-1] = "  timezone: UTC-12\n"
        validate_updated_yaml(CURRENT, "".join(lines), today=date(2026, 8, 28))


def test_bad_timezone_utc_plus_12_rejected():
    updated = CURRENT.replace(
        "  timezone: AoE\n",
        "  timezone: UTC+12\n",
        1,
    )
    # first timezone is 2025 (past) — either timezone is forbidden
    with pytest.raises(YamlValidationError, match="AoE"):
        validate_updated_yaml(CURRENT, updated, today=date(2026, 8, 28))


def test_mutated_past_year_rejected():
    updated = CURRENT.replace("id: demo25", "id: demo25-mutated")
    with pytest.raises(YamlValidationError, match="past year 2025"):
        validate_updated_yaml(CURRENT, updated, today=date(2026, 8, 28))


def test_missing_required_field_rejected():
    updated = """\
- title: Demo
  year: 2027
  date: January 1 - 2, 2027
"""
    with pytest.raises(YamlValidationError, match="required field"):
        validate_updated_yaml(CURRENT, updated, today=date(2026, 8, 28))


def test_empty_yaml_rejected():
    with pytest.raises(YamlValidationError, match="empty"):
        validate_updated_yaml(CURRENT, "   ", today=date(2026, 8, 28))


def test_appending_next_year_does_not_flag_past_block_newline():
    current = """\
- title: Demo
  year: 2025
  id: demo25
  date: January 1 - 2, 2025
  start: '2025-01-01'
  end: '2025-01-02'
  timezone: AoE
"""
    updated = current.rstrip("\n") + """
- title: Demo
  year: 2027
  id: demo27
  date: January 1 - 2, 2027
  start: '2027-01-01'
  end: '2027-01-02'
  timezone: AoE
"""
    validate_updated_yaml(current, updated, today=date(2026, 8, 28))

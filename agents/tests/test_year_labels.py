"""Year classification: PAST / UPCOMING / MISSING_NEXT_YEAR / UNKNOWN."""

from datetime import date

from agents.pipeline_utils import (
    classify_conference_years,
    classify_year_entry,
    format_year_labels_block,
    parse_date_field_end,
)

KDD_STYLE_YAML = """\
- title: KDD
  year: 2025
  id: kdd25
  date: August 3 - 7, 2025
  start: '2025-08-03'
  end: '2025-08-07'
- title: KDD
  year: 2026
  id: kdd26
  date: August 9 - 13, 2026
  start: '2026-08-09'
  end: '2026-08-13'
"""

UNKNOWN_YAML = """\
- title: FutureConf
  year: 2027
  id: future27
  deadlines: []
"""


def test_kdd_ended_last_week_is_past_and_next_year_missing():
    today = date(2026, 8, 26)
    labels = {item.year: item.status for item in classify_conference_years(KDD_STYLE_YAML, today)}
    assert labels[2025] == "PAST"
    assert labels[2026] == "PAST"
    assert labels[2027] == "MISSING_NEXT_YEAR"


def test_kdd_still_upcoming_before_end_date():
    today = date(2026, 8, 10)
    labels = {item.year: item.status for item in classify_conference_years(KDD_STYLE_YAML, today)}
    assert labels[2025] == "PAST"
    assert labels[2026] == "UPCOMING"
    assert 2027 not in labels


def test_end_date_on_today_is_past():
    entry = {"year": 2026, "end": "2026-08-13"}
    assert classify_year_entry(entry, date(2026, 8, 13)) == "PAST"


def test_falls_back_to_start_when_end_missing():
    entry = {"year": 2027, "start": "2027-06-01"}
    assert classify_year_entry(entry, date(2026, 8, 28)) == "UPCOMING"
    assert classify_year_entry(entry, date(2027, 6, 2)) == "PAST"


def test_falls_back_to_date_field_when_start_and_end_missing():
    entry = {"year": 2026, "date": "August 9 - 13, 2026"}
    assert classify_year_entry(entry, date(2026, 8, 26)) == "PAST"
    assert classify_year_entry(entry, date(2026, 8, 1)) == "UPCOMING"


def test_missing_all_dates_is_unknown_not_fake_upcoming_row():
    today = date(2026, 8, 28)
    labels = classify_conference_years(UNKNOWN_YAML, today)
    assert [(item.year, item.status) for item in labels] == [(2027, "UNKNOWN")]


def test_parse_cross_month_date_field():
    assert parse_date_field_end("April 29-May 4, 2025") == date(2025, 5, 4)
    assert parse_date_field_end("February 25 - March 4, 2025") == date(2025, 3, 4)
    assert parse_date_field_end("November 30 - December 7, 2025") == date(2025, 12, 7)
    assert parse_date_field_end("December 6-12, 2026") == date(2026, 12, 12)


def test_year_labels_block_includes_today():
    today = date(2026, 8, 26)
    labels = classify_conference_years(KDD_STYLE_YAML, today)
    block = format_year_labels_block(today, labels)
    assert "today: 2026-08-26" in block
    assert "2025: PAST" in block
    assert "2026: PAST" in block
    assert "2027: MISSING_NEXT_YEAR" in block


def test_upcoming_latest_year_does_not_invent_missing_next():
    yaml_text = """\
- title: AAAI
  year: 2026
  id: aaai26
  start: 2026-01-20
  end: 2026-01-27
- title: AAAI
  year: 2027
  id: aaai27
  start: 2027-02-16
  end: 2027-02-23
"""
    labels = {item.year: item.status for item in classify_conference_years(yaml_text, date(2026, 8, 28))}
    assert labels[2026] == "PAST"
    assert labels[2027] == "UPCOMING"
    assert 2028 not in labels

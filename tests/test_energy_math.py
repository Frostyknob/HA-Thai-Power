"""Tests for reset-safe energy totals built from long-term statistics rows."""

import os
import sys
import unittest
import zoneinfo
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("custom_components/thai_energy_monitor"))

from energy_math import partial_since_last_stat, summarize_hourly_changes  # noqa: E402

BKK = zoneinfo.ZoneInfo("Asia/Bangkok")


def _parse(value):
    return value


def _daily_reset_rows(cycle_start, days, kwh_per_hour):
    """Build hourly LTS rows for a meter that resets to 0 every midnight.

    The recorder reports a reset-safe ``change`` per hour and a ``state``
    that is the raw (resetting) meter reading at the end of the hour.
    """
    rows = []
    running_sum = 1000.0
    # Three hours before the cycle, as the coordinator queries them
    for h in range(-3, days * 24):
        start = cycle_start + timedelta(hours=h)
        hour_of_day = start.hour
        state = kwh_per_hour * (hour_of_day + 1)  # resets at 00:00
        running_sum += kwh_per_hour
        rows.append({"start": start, "change": kwh_per_hour, "state": state, "sum": running_sum})
    return rows


class TestPartialSinceLastStat(unittest.TestCase):
    def test_normal_increase(self):
        self.assertAlmostEqual(partial_since_last_stat(12.5, 10.0), 2.5)

    def test_meter_reset_counts_everything_on_meter(self):
        # Last compiled hour ended at 23:00 with 24 kWh; meter reset at midnight
        self.assertAlmostEqual(partial_since_last_stat(0.4, 24.0), 0.4)

    def test_no_previous_state(self):
        self.assertEqual(partial_since_last_stat(5.0, None), 0.0)

    def test_unavailable_reads_as_zero(self):
        self.assertEqual(partial_since_last_stat(0.0, 7.0), 0.0)


class TestSummarizeHourlyChanges(unittest.TestCase):
    def test_daily_reset_meter_counts_whole_cycle(self):
        cycle_start = datetime(2026, 11, 17, 0, 0, tzinfo=BKK)
        rows = _daily_reset_rows(cycle_start, days=3, kwh_per_hour=0.5)
        today_start = cycle_start + timedelta(days=2)

        summary = summarize_hourly_changes(rows, cycle_start, today_start, _parse)

        # 3 full days x 24 h x 0.5 kWh; the 3 pre-cycle hours are excluded
        self.assertAlmostEqual(summary["monthly"], 36.0)
        self.assertAlmostEqual(summary["today"], 12.0)
        # Raw meter at end of the last hour (23:00-24:00) reads 12 kWh
        self.assertAlmostEqual(summary["last_state"], 12.0)
        self.assertEqual(summary["last_end"], cycle_start + timedelta(days=3))

    def test_baseline_subtraction_would_undercount(self):
        """Documents the bug: raw meter minus cycle-start reading is ~one day."""
        cycle_start = datetime(2026, 11, 17, 0, 0, tzinfo=BKK)
        rows = _daily_reset_rows(cycle_start, days=4, kwh_per_hour=0.25)
        summary = summarize_hourly_changes(rows, cycle_start, cycle_start + timedelta(days=3), _parse)
        naive = rows[-1]["state"] - rows[2]["state"]  # what baseline subtraction saw
        self.assertLess(naive, summary["monthly"] / 3)
        self.assertAlmostEqual(summary["monthly"], 24.0)

    def test_negative_and_missing_changes_ignored(self):
        cycle_start = datetime(2026, 11, 1, 0, 0, tzinfo=BKK)
        rows = [
            {"start": cycle_start, "change": 1.0, "state": 1.0, "sum": 1.0},
            {"start": cycle_start + timedelta(hours=1), "change": -3.0, "state": 0.0, "sum": 1.0},
            {"start": cycle_start + timedelta(hours=2), "change": None, "state": 0.0, "sum": 1.0},
            {"start": cycle_start + timedelta(hours=3), "change": 2.0, "state": 2.0, "sum": 3.0},
        ]
        summary = summarize_hourly_changes(rows, cycle_start, cycle_start, _parse)
        self.assertAlmostEqual(summary["monthly"], 3.0)
        self.assertAlmostEqual(summary["last_sum"], 3.0)

    def test_no_rows_returns_none(self):
        start = datetime(2026, 11, 1, tzinfo=BKK)
        self.assertIsNone(summarize_hourly_changes([], start, start, _parse))

    def test_only_pre_cycle_rows_give_zero_with_known_state(self):
        cycle_start = datetime(2026, 11, 17, 0, 0, tzinfo=BKK)
        rows = [{"start": cycle_start - timedelta(hours=1), "change": 0.5, "state": 9.0, "sum": 50.0}]
        summary = summarize_hourly_changes(rows, cycle_start, cycle_start, _parse)
        self.assertEqual(summary["monthly"], 0.0)
        self.assertEqual(summary["last_state"], 9.0)


if __name__ == "__main__":
    unittest.main()

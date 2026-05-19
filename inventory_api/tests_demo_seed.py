from datetime import datetime

from django.test import SimpleTestCase
from django.utils import timezone

from inventory_api.forecasting.demo_seed import (
    _activity_context,
    _normalize_demo_profile,
    _normalize_demo_scenario,
    _target_vector,
)


class DemoSeedProfileTests(SimpleTestCase):
    def test_default_office_profile_matches_expected_hours(self):
        profile = _normalize_demo_profile("office_weekday", None)
        self.assertEqual(profile["workday_start"], "08:30")
        self.assertEqual(profile["workday_end"], "17:30")
        self.assertEqual(profile["lunch_start"], "13:00")
        self.assertEqual(profile["lunch_end"], "14:00")
        self.assertEqual(profile["backup_start"], "21:00")
        self.assertEqual(profile["backup_end"], "23:00")
        self.assertEqual(profile["workdays"], [0, 1, 2, 3, 4])

    def test_workday_pressure_higher_than_weekend(self):
        profile = _normalize_demo_profile("office_weekday", None)
        tz = timezone.get_current_timezone()
        monday = timezone.make_aware(datetime(2026, 3, 16, 10, 0), tz)
        sunday = timezone.make_aware(datetime(2026, 3, 15, 10, 0), tz)

        monday_ctx = _activity_context(monday, profile)
        sunday_ctx = _activity_context(sunday, profile)

        self.assertGreater(monday_ctx["work_pressure"], sunday_ctx["work_pressure"])
        self.assertTrue(monday_ctx["is_workday"])
        self.assertFalse(sunday_ctx["is_workday"])

    def test_backup_window_active_only_in_configured_period(self):
        profile = _normalize_demo_profile("office_weekday", None)
        tz = timezone.get_current_timezone()
        backup_ts = timezone.make_aware(datetime(2026, 3, 16, 21, 30), tz)
        midday_ts = timezone.make_aware(datetime(2026, 3, 16, 12, 0), tz)

        backup_ctx = _activity_context(backup_ts, profile)
        midday_ctx = _activity_context(midday_ts, profile)

        self.assertGreater(backup_ctx["backup_pressure"], 0.5)
        self.assertLess(midday_ctx["backup_pressure"], 0.1)

    def test_demo_scenario_normalizes_selected_metrics_and_coefficients(self):
        scenario = _normalize_demo_scenario({
            "degraded_metric_codes": ["mem_usage_percent", "storcli_predictive_failure_count", "unknown"],
            "degradation_strength": 1.7,
            "bad_mode_persistence": -1,
        })

        self.assertEqual(
            scenario["degraded_metric_codes"],
            ["mem_usage_percent", "storcli_predictive_failure_count"],
        )
        self.assertEqual(scenario["degradation_strength"], 1.7)
        self.assertEqual(scenario["bad_mode_persistence"], 0.0)

    def test_degradation_strength_is_clamped_to_new_upper_bound(self):
        scenario = _normalize_demo_scenario({
            "degraded_metric_codes": ["cpu_load_total"],
            "degradation_strength": 7.5,
        })
        self.assertEqual(scenario["degradation_strength"], 3.0)

    def test_selected_metric_gets_smooth_upward_drift(self):
        profile = _normalize_demo_profile("office_weekday", None)
        scenario = _normalize_demo_scenario({
            "degraded_metric_codes": ["mem_usage_percent"],
            "degradation_strength": 0.9,
            "bad_mode_persistence": 0.6,
        })
        tz = timezone.get_current_timezone()
        start_at = timezone.make_aware(datetime(2026, 1, 1, 0, 0), tz)
        end_at = timezone.make_aware(datetime(2026, 3, 1, 0, 0), tz)

        early_vector = _target_vector(
            timezone.make_aware(datetime(2026, 1, 5, 10, 0), tz),
            profile,
            start_at,
            end_at,
            scenario,
        )
        late_vector = _target_vector(
            timezone.make_aware(datetime(2026, 2, 27, 10, 0), tz),
            profile,
            start_at,
            end_at,
            scenario,
        )

        self.assertGreater(late_vector["mem_usage_percent"], early_vector["mem_usage_percent"])

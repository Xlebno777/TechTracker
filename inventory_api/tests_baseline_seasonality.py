from types import SimpleNamespace

from django.test import SimpleTestCase

from inventory_api.forecasting.baseline_service import (
    DEFAULT_SEASONALITY_MODE,
    SEASONALITY_MODE_SARIMA_SEASONAL,
    SEASONALITY_MODE_STL_RESEASONALIZED,
    normalize_seasonality_mode,
    project_recent_trend_adjustment,
    project_repeating_seasonality,
    seasonality_mode_label,
)


class BaselineSeasonalityHelpersTests(SimpleTestCase):
    def test_normalize_seasonality_mode_falls_back_to_default(self):
        self.assertEqual(normalize_seasonality_mode(None), DEFAULT_SEASONALITY_MODE)
        self.assertEqual(normalize_seasonality_mode("unknown"), DEFAULT_SEASONALITY_MODE)
        self.assertEqual(
            normalize_seasonality_mode(SEASONALITY_MODE_SARIMA_SEASONAL),
            SEASONALITY_MODE_SARIMA_SEASONAL,
        )

    def test_project_repeating_seasonality_repeats_last_cycle(self):
        pandas = __import__("pandas")
        preprocess_result = SimpleNamespace(
            seasonal=pandas.Series([9.0, 8.0, 1.0, 2.0, 3.0, 4.0]),
            seasonal_period=4,
        )
        projected = project_repeating_seasonality(preprocess_result, steps=6)
        self.assertEqual(projected, [1.0, 2.0, 3.0, 4.0, 1.0, 2.0])

    def test_seasonality_mode_label_is_human_readable(self):
        self.assertEqual(seasonality_mode_label(SEASONALITY_MODE_SARIMA_SEASONAL), "SARIMA с сезонностью")
        self.assertEqual(
            seasonality_mode_label(SEASONALITY_MODE_STL_RESEASONALIZED),
            "STL + возврат сезонности",
        )

    def test_project_recent_trend_adjustment_detects_smooth_growth(self):
        pandas = __import__("pandas")
        preprocess_result = SimpleNamespace(
            trend=pandas.Series([10.0 + idx * 0.2 for idx in range(96)]),
            seasonal_period=24,
        )
        projected, meta = project_recent_trend_adjustment(preprocess_result, steps=5)
        self.assertEqual(len(projected), 5)
        self.assertTrue(meta["applied"])
        self.assertGreater(projected[-1], projected[0])
        self.assertGreater(projected[-1], 0.0)

    def test_project_recent_trend_adjustment_ignores_flat_trend(self):
        pandas = __import__("pandas")
        preprocess_result = SimpleNamespace(
            trend=pandas.Series([25.0 for _ in range(96)]),
            seasonal_period=24,
        )
        projected, meta = project_recent_trend_adjustment(preprocess_result, steps=5)
        self.assertEqual(projected, [0.0] * 5)
        self.assertFalse(meta["applied"])

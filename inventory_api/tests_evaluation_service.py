from django.test import SimpleTestCase

from inventory_api.forecasting.evaluation_service import _forecast_variant_from_meta


class EvaluationServiceVariantTests(SimpleTestCase):
    def test_sarima_seasonal_variant(self):
        key, label = _forecast_variant_from_meta(
            "sarima",
            {"seasonality_mode": "sarima_seasonal"},
            {},
        )
        self.assertEqual(key, "sarima:sarima_seasonal")
        self.assertEqual(label, "SARIMA • сезонность в модели")

    def test_sarima_stl_variant_from_run_parameters(self):
        key, label = _forecast_variant_from_meta(
            "sarima",
            {},
            {"seasonality_mode": "stl_reseasonalized"},
        )
        self.assertEqual(key, "sarima:stl_reseasonalized")
        self.assertEqual(label, "SARIMA • STL + возврат сезонности")

    def test_non_sarima_variant_passthrough(self):
        key, label = _forecast_variant_from_meta("ensemble", {}, {})
        self.assertEqual(key, "ensemble")
        self.assertEqual(label, "Оркестр")

from django.test import SimpleTestCase, override_settings

from inventory_api.release_management import compare_versions, get_current_release_info


class ApplicationUpdateServiceTests(SimpleTestCase):
    def test_compare_versions(self):
        self.assertEqual(compare_versions("0.1.0", "0.1.0"), 0)
        self.assertLess(compare_versions("0.1.0", "0.1.1"), 0)
        self.assertGreater(compare_versions("v0.2.0", "0.1.9"), 0)

    @override_settings(
        APP_VERSION="1.2.3",
        APP_RELEASE_CHANNEL="single",
        APP_RELEASE_MANIFEST_URL="",
        APP_UPDATE_ENABLED=False,
        APP_UPDATE_SCRIPT="/tmp/not-existing-techtracker-update.ps1",
    )
    def test_current_release_info_is_safe_without_manifest(self):
        info = get_current_release_info()
        self.assertEqual(info["current_version"], "1.2.3")
        self.assertEqual(info["release_channel"], "single")
        self.assertFalse(info["manifest_configured"])
        self.assertFalse(info["update_enabled"])
        self.assertFalse(info["update_script_exists"])

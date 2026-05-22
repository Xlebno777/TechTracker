from django.test import SimpleTestCase, override_settings

from inventory_api.release_management import compare_versions, get_current_release_info, normalize_manifest


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
        self.assertTrue(info["manifest_configured"])
        self.assertFalse(info["update_enabled"])
        self.assertFalse(info["update_script_exists"])

    def test_normalize_github_latest_release_payload(self):
        manifest = normalize_manifest({
            "tag_name": "v0.1.14",
            "name": "TechTracker v0.1.14",
            "published_at": "2026-05-22T00:00:00Z",
            "body": "- fix updates\n- improve installer",
            "assets": [
                {
                    "name": "TechTracker-v0.1.14-windows-server.zip",
                    "browser_download_url": "https://example.test/archive.zip",
                    "digest": "sha256:abc123",
                }
            ],
        })
        self.assertEqual(manifest["version"], "v0.1.14")
        self.assertEqual(manifest["git_ref"], "v0.1.14")
        self.assertEqual(manifest["download_url"], "https://example.test/archive.zip")
        self.assertEqual(manifest["sha256"], "abc123")
        self.assertEqual(manifest["notes"], ["fix updates", "improve installer"])

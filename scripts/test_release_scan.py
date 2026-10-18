import unittest
from datetime import UTC, datetime

from release_scan import fresh_database, verdict


class ScanEvidenceTests(unittest.TestCase):
    def test_invalid_or_stale_cache_is_not_accepted(self):
        now = datetime(2026, 10, 16, tzinfo=UTC)
        self.assertFalse(fresh_database("Status: invalid\nBuilt: 2026-10-16T00:00:00Z", now))
        self.assertFalse(fresh_database("Status: valid\nBuilt: 2026-10-13T00:00:00Z", now))
        self.assertTrue(fresh_database("Status: valid\nBuilt: 2026-10-15T00:00:00Z", now))

    def test_download_failure_and_empty_output_are_blocked(self):
        self.assertEqual(verdict(1, None), "blocked")
        self.assertEqual(verdict(0, {}), "blocked")
        self.assertEqual(verdict(0, {"matches": None}), "blocked")

    def test_success_requires_official_valid_database(self):
        report = {
            "matches": [],
            "descriptor": {
                "db": {"status": {"valid": True, "from": "https://untrusted.invalid/db"}}
            },
        }
        self.assertEqual(verdict(0, report), "blocked")
        report["descriptor"]["db"]["status"]["from"] = "https://grype.anchore.io/databases/v6/db"
        self.assertEqual(verdict(0, report), "passed")
        self.assertEqual(verdict(2, report), "failed")

    def test_high_findings_fail_even_if_process_reports_success(self):
        report = {
            "matches": [{"vulnerability": {"severity": "High"}}],
            "descriptor": {
                "db": {
                    "status": {"valid": True, "from": "https://grype.anchore.io/databases/v6/db"}
                }
            },
        }
        self.assertEqual(verdict(0, report), "failed")

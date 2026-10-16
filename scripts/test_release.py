import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release import ReleaseError, compose, exclusive, run
from release_preflight import validate


class ReleaseGuardTests(unittest.TestCase):
    def test_paid_launch_and_missing_image_scan_evidence_are_blocked(self):
        with patch("release_preflight.run", return_value="fixture"):
            blocked = validate(
                {"commercial_mode": "paid_public_launch"},
                {"source": {"dirty": True, "revision": "fixture"}, "images": {}},
            )
        self.assertIn("billing_entitlements_metering_not_implemented", blocked)
        self.assertIn("committed_clean_candidate_required", blocked)
        self.assertIn("immutable_artifacts_required", blocked)
        self.assertIn("passing_security_evidence_for_all_artifacts_required", blocked)

    def test_unknown_or_mismatched_target_refused(self):
        for state in (
            {"project": "production"},
            {"project": "ppi-rehearsal-0123456789", "database": "working"},
        ):
            with self.assertRaises(ReleaseError):
                compose(Path("unused"), state)

    def test_exclusive_lock_prevents_concurrent_release_and_preserves_other_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with exclusive(folder):
                with self.assertRaises(ReleaseError):
                    with exclusive(folder):
                        self.fail("Concurrent release admitted")
                self.assertTrue((folder / "release.lock").exists())
            self.assertFalse((folder / "release.lock").exists())

    def test_subprocess_failure_does_not_expose_stderr(self):
        import subprocess

        with patch(
            "release.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1, ["fixture"], stderr="private-password-body"
            ),
        ):
            with self.assertRaises(ReleaseError) as result:
                run(["fixture"])
        self.assertNotIn("private", str(result.exception))

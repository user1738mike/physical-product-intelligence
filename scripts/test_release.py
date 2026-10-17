import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release import ReleaseError, compose, exclusive, operate, run
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

    def test_supervised_processors_quiesce_before_backup_and_old_manifests_stay_compatible(self):
        import json

        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                manifest = {
                    "project": "ppi-rehearsal-0123456789",
                    "database": "ppi_rehearsal_0123456789",
                    "events": [],
                    "processors_enabled": enabled,
                }
                (folder / "release.json").write_text(json.dumps(manifest))
                commands = []

                def execute(command, _commands=commands, **kwargs):
                    _commands.append((command, kwargs))
                    return "{}"

                with patch("release.run", side_effect=execute):
                    operate(folder, "backup")
                stop = next(
                    (command, options) for command, options in commands if "stop" in command
                )
                self.assertEqual("processors" in stop[0], enabled)
                self.assertEqual("compose.processors.yaml" in stop[0], enabled)
                self.assertEqual(stop[1]["timeout"], 300 if enabled else 120)
                backup_index = next(
                    i for i, (command, _) in enumerate(commands) if "backup_bundle" in command
                )
                stop_index = next(i for i, (command, _) in enumerate(commands) if "stop" in command)
                self.assertLess(stop_index, backup_index)

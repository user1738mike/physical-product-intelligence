import copy
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from attest_grype_import import stop_owned_import
from grype_provenance import METADATA_URL, cache_digest, validate_metadata, verify_receipt
from release_scan import archive_identity, database_status, stop_owned_scan, verdict

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class OfficialImportTests(unittest.TestCase):
    def test_database_validation_timeout_cleans_only_its_owned_process(self):
        with (
            patch("release_scan.secrets.token_hex", return_value="a" * 32),
            patch(
                "release_scan.execute", side_effect=TimeoutError("Synthetic blocked storage")
            ) as execute,
            patch("release_scan.stop_owned_scan") as cleanup,
        ):
            with self.assertRaises(TimeoutError):
                database_status(["docker", "run", "--rm"], "immutable-scanner")
        cleanup.assert_called_once_with("ppi-grype-status-" + "a" * 16, "a" * 32)
        self.assertEqual(execute.call_args.kwargs["timeout"], 300)
        self.assertIn("ppi.grype-scan=" + "a" * 32, execute.call_args.args[0])

    def test_timeout_cleanup_stops_only_our_scanner_container(self):
        with patch("release_scan.execute", return_value=(0, "different-owner", "")) as execute:
            stop_owned_scan("fixture", "our-owner")
            self.assertEqual(execute.call_count, 1)
        with patch(
            "release_scan.execute", side_effect=[(0, "our-owner\n", ""), (0, "", "")]
        ) as execute:
            stop_owned_scan("fixture", "our-owner")
            self.assertEqual(
                execute.call_args.args[0], ["docker", "stop", "--time", "5", "fixture"]
            )

    def test_exported_image_config_is_hashed_and_multiple_images_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tar"
            config = json.dumps({"rootfs": {"diff_ids": ["sha256:" + "a" * 64]}}).encode()
            for count in (1, 2):
                with tarfile.open(path, "w") as bundle:
                    for name, data in [
                        ("manifest.json", json.dumps([{"Config": "config.json"}] * count).encode()),
                        ("config.json", config),
                    ]:
                        member = tarfile.TarInfo(name)
                        member.size = len(data)
                        bundle.addfile(member, io.BytesIO(data))
                if count == 1:
                    self.assertEqual(
                        archive_identity(path),
                        ("sha256:" + hashlib.sha256(config).hexdigest(), ["sha256:" + "a" * 64]),
                    )
                else:
                    with self.assertRaises(ValueError):
                        archive_identity(path)

    def test_cleanup_never_stops_a_container_without_our_fresh_ownership_label(self):
        with patch("attest_grype_import.execute", return_value=(0, "other-owner", "")) as execute:
            stop_owned_import("fixture-container", "fresh-nonce")
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(execute.call_args.args[0][1], "inspect")
        with patch("attest_grype_import.execute", return_value=(0, "fresh-nonce", "")) as execute:
            stop_owned_import("fixture-container", "fresh-nonce")
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(
                execute.call_args.args[0], ["docker", "stop", "--time", "5", "fixture-container"]
            )

    def metadata(self, content=b"synthetic-public-db-archive"):
        return {
            "status": "active",
            "schemaVersion": "v6.1.10",
            "built": "2026-10-17T06:27:09Z",
            "path": "vulnerability-db_v6.1.10_fixture.tar.zst",
            "checksum": "sha256:" + hashlib.sha256(content).hexdigest(),
        }

    def test_metadata_rejects_unsafe_identity_schema_checksum_and_age(self):
        valid = self.metadata()
        self.assertTrue(
            validate_metadata(valid, NOW).startswith("https://grype.anchore.io/databases/v6/")
        )
        for key, value in (
            ("status", "inactive"),
            ("schemaVersion", "v5.1.0"),
            ("path", "../outside.tar.zst"),
            ("path", "https://evil.invalid/db"),
            ("checksum", "sha1:abc"),
            ("built", "2026-10-14T00:00:00Z"),
            ("built", "2026-10-18T00:00:00Z"),
            ("built", None),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_metadata({**valid, key: value}, NOW)

    def test_manual_import_is_never_accepted_without_verified_chain(self):
        report = {
            "matches": [],
            "descriptor": {"db": {"status": {"valid": True, "from": "manual import"}}},
        }
        self.assertEqual(verdict(0, report), "blocked")
        self.assertEqual(verdict(0, report, verified_import=True), "passed")
        report["matches"] = [{"vulnerability": {"severity": "High"}}]
        self.assertEqual(verdict(0, report, verified_import=True), "failed")

    def test_receipt_binds_fresh_import_archive_scanner_cache_and_database_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            archive = root / "artifacts/db.tar.zst"
            archive.write_bytes(b"synthetic-public-db-archive")
            database = {"sha256": "a" * 64, "client_version": "v6.1.10", "source": "manual import"}
            receipt = {
                "format": "ppi-official-grype-import-v1",
                "verified_at": NOW.isoformat(),
                "metadata_url": METADATA_URL,
                "metadata": self.metadata(),
                "scanner": "immutable-scanner-fixture",
                "cache": "ppi_grype_0123456789",
                "archive": "artifacts/db.tar.zst",
                "database": database,
                "fresh_cache_import": True,
                "import_exit_code": 0,
            }
            status = (
                "Schema: v6.1.10\nBuilt: 2026-10-17T06:27:09Z\nFrom: manual import\nStatus: valid\n"
            )

            def verify(value, db=database):
                return verify_receipt(
                    value,
                    cache=receipt["cache"],
                    scanner=receipt["scanner"],
                    status=status,
                    database=db,
                    root=root,
                    now=NOW,
                )

            self.assertTrue(verify(receipt))
            for key, value in (
                ("fresh_cache_import", False),
                ("import_exit_code", 1),
                ("scanner", "other"),
                ("cache", "other"),
                ("metadata_url", "https://evil.invalid/latest.json"),
                ("verified_at", (NOW - timedelta(days=3)).isoformat()),
            ):
                with self.subTest(key=key):
                    self.assertFalse(verify({**receipt, key: value}))
            different = copy.deepcopy(database)
            different["sha256"] = "b" * 64
            self.assertFalse(verify(receipt, different))
            archive.write_bytes(b"corrupted")
            self.assertFalse(verify(receipt))

    def test_cache_path_cannot_mount_arbitrary_host_paths(self):
        def forbidden(*args, **kwargs):
            self.fail("Docker must not run for an invalid cache identity")

        for cache in ("C:/private", "../../secret", "host:/cache", "ppi_cache:rw"):
            with self.subTest(cache=cache), self.assertRaises(ValueError):
                cache_digest(cache, "fixture", forbidden)

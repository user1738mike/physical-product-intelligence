import io
import json
import socket
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from ingestion.ai_provider import ProviderFailure
from ingestion.evaluation import evaluate
from ingestion.scanning import clamd_scan


class ScannerTests(SimpleTestCase):
    def scan(self, reply):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.side_effect = reply
        with (
            patch.dict("os.environ", {"CLAMD_HOST": "scanner", "CLAMD_PORT": "3310"}),
            patch("ingestion.scanning.socket.create_connection", return_value=connection),
        ):
            return clamd_scan(b"synthetic bytes")

    def test_only_complete_clean_reply_is_accepted(self):
        self.assertTrue(self.scan([b"stream: OK\0"]))
        self.assertFalse(self.scan([b"stream: infected FOUND\0"]))
        self.assertFalse(self.scan([b"stream: scanner ERROR\0"]))

    def test_timeout_unavailable_and_truncated_responses_fail_closed(self):
        with self.assertRaises(socket.timeout):
            self.scan([TimeoutError()])
        with self.assertRaises(ValueError):
            self.scan([b"partial", b""])
        with (
            patch.dict("os.environ", {"CLAMD_HOST": "scanner"}),
            patch(
                "ingestion.scanning.socket.create_connection", side_effect=OSError("private-host")
            ),
            self.assertRaises(OSError),
        ):
            clamd_scan(b"data")

    def test_scanner_configuration_and_size_are_bounded(self):
        with patch.dict("os.environ", {"CLAMD_HOST": ""}), self.assertRaises(ValueError):
            clamd_scan(b"data")


class EvaluationAndLiveGateTests(SimpleTestCase):
    def test_versioned_synthetic_checks_match_without_provider_or_database(self):
        with patch(
            "ingestion.ai_provider.configured_provider", side_effect=AssertionError("No provider")
        ):
            result = evaluate()
        self.assertEqual(result["dataset_version"], "synthetic-spec-v1")
        self.assertEqual(result["cases"], 18)
        self.assertEqual(result["case_expectations_matched"], 18)
        self.assertEqual(result["provider_calls"], 0)

    def test_live_command_is_inert_without_explicit_flag(self):
        output = io.StringIO()
        with patch(
            "ingestion.ai_provider.configured_provider", side_effect=AssertionError("No provider")
        ):
            call_command("check_ai_provider", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["status"], "not_executed")

    @override_settings(AI_EXTRACTION_MODEL="mock-model")
    def test_opt_in_command_uses_existing_adapter_with_bounded_synthetic_request(self):
        output = io.StringIO()
        provider = Mock()
        provider.extract.return_value = (
            json.dumps(
                {
                    "candidates": [
                        {
                            "attribute": "mass",
                            "value": "1200",
                            "unit": "g",
                            "original": "1200 g",
                            "segment": 1,
                            "quote": "Weight: 1200 g",
                        }
                    ]
                }
            ),
            {},
        )
        with patch("ingestion.ai_provider.configured_provider", return_value=provider) as factory:
            call_command("check_ai_provider", allow_live_provider=True, stdout=output)
        factory.assert_called_once_with(max_output_tokens=400)
        self.assertEqual(provider.extract.call_count, 1)
        self.assertNotIn("product_id", json.dumps(provider.extract.call_args.args))
        self.assertEqual(json.loads(output.getvalue())["status"], "passed")

    def test_opt_in_provider_failures_are_sanitized(self):
        output = io.StringIO()
        with patch(
            "ingestion.ai_provider.configured_provider", side_effect=ProviderFailure("timeout")
        ):
            call_command("check_ai_provider", allow_live_provider=True, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["category"], "timeout")

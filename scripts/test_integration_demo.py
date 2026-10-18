import unittest
from unittest.mock import patch

from integration_demo import demonstrate


class DemonstrationLifecycleTests(unittest.TestCase):
    def test_running_dispatcher_resumes_after_demonstration_failure(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if "ps" in command:
                return "backend\nprocessors\n"
            if "demonstrate_integrations" in command:
                raise RuntimeError("Synthetic demonstration failure")
            return ""

        with patch("integration_demo.run", side_effect=run), self.assertRaises(RuntimeError):
            demonstrate(["compose-fixture"], True)
        self.assertIn("stop", calls[1])
        self.assertIn("up", calls[-1])
        self.assertEqual(calls[-1][-1], "processors")

    def test_stopped_dispatcher_is_not_started_by_demonstration(self):
        with patch("integration_demo.run", side_effect=["backend\n", '{"status":"passed"}']) as run:
            self.assertEqual(demonstrate(["compose-fixture"], True)["status"], "passed")
        self.assertEqual(run.call_count, 2)

"""Run with python -m unittest discover -s scripts -p test_setup_env.py."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from setup_env import ROOT, setup_env


class SetupEnvTests(unittest.TestCase):
    def test_creation_generates_distinct_credentials_and_preserves_template(self):
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        credentials = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".env.example").write_text(template, encoding="utf-8")
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertTrue(setup_env(root))
                values = dict(
                    line.split("=", 1)
                    for line in (root / ".env").read_text().splitlines()
                    if line and not line.startswith("#")
                )
                for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD"):
                    self.assertRegex(values[key], r"^[a-f0-9]{64}$")
                    self.assertNotIn(values[key], output.getvalue())
                self.assertNotEqual(
                    values["DJANGO_SECRET_KEY"], values["POSTGRES_PASSWORD"]
                )
                self.assertEqual(values["POSTGRES_DB"], "ppi")
                self.assertEqual(values["POSTGRES_USER"], "ppi")
                self.assertEqual((root / ".env.example").read_text(), template)
                credentials.append(values["DJANGO_SECRET_KEY"])
        self.assertNotEqual(*credentials)

    def test_rerun_preserves_existing_file_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b"# developer configuration\r\nCUSTOM=value\r\n"
            (root / ".env").write_bytes(original)
            with (
                redirect_stdout(io.StringIO()),
                patch("setup_env.secrets.token_hex") as generate,
            ):
                self.assertFalse(setup_env(root))
            generate.assert_not_called()
            self.assertEqual((root / ".env").read_bytes(), original)

    def test_invalid_template_creates_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text("POSTGRES_DB=ppi\n")
            with self.assertRaises(ValueError):
                setup_env(root)
            self.assertFalse((root / ".env").exists())

    def test_concurrent_creation_preserves_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_bytes((ROOT / ".env.example").read_bytes())
            original_open = Path.open

            def racing_open(path, mode="r", *args, **kwargs):
                if mode == "x":
                    path.write_bytes(b"CUSTOM=preserved\n")
                return original_open(path, mode, *args, **kwargs)

            with (
                patch.object(Path, "open", racing_open),
                redirect_stdout(io.StringIO()),
            ):
                self.assertFalse(setup_env(root))
            self.assertEqual((root / ".env").read_bytes(), b"CUSTOM=preserved\n")

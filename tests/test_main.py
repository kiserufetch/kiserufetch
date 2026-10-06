import tempfile
import unittest
from datetime import date
from pathlib import Path

from dossier.__main__ import ConfigError, parse_emails, run

ENV = {"DOSSIER_TOKEN": "t", "DOSSIER_EMAILS": "Me@Example.com, ", "DOSSIER_SALT": "salt"}


class FakeClient:
    def list(self, path, params=None, key=None):
        if path == "/user/repos":
            return [{"full_name": "me/top-secret-project", "private": True, "fork": False, "default_branch": "main"}]
        return [{"sha": "a", "author": None,
                 "commit": {"author": {"email": "me@example.com", "date": "2026-10-05T10:00:00Z"}}}]

    def get(self, path, params=None):
        return {}


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.svg = Path(tmp.name) / "dossier.svg"
        self.readme = Path(tmp.name) / "README.md"
        self.readme.write_text('<img src="assets/dossier.svg?v=2026-01-01">\n', encoding="utf-8")
        self.logs = []

    def go(self, env=ENV):
        run(env, client=FakeClient(), today=date(2026, 10, 6),
            svg_path=self.svg, readme_path=self.readme, log=self.logs.append)

    def test_writes_svg_and_bumps_readme(self):
        self.go()
        svg = self.svg.read_text(encoding="utf-8")
        self.assertIn("1 · visible to you: 0", svg)
        self.assertIn("1 event · contents classified", svg)
        self.assertIn("?v=2026-10-06", self.readme.read_text(encoding="utf-8"))

    def test_outputs_never_leak_repo_names_or_addresses(self):
        self.go()
        public = (self.svg.read_text(encoding="utf-8") + self.readme.read_text(encoding="utf-8")
                  + "\n".join(self.logs)).lower()
        self.assertNotIn("top-secret-project", public)
        self.assertNotIn("example.com", public)

    def test_missing_secret_fails_before_writing(self):
        for key in ENV:
            with self.subTest(key=key):
                env = {k: v for k, v in ENV.items() if k != key}
                with self.assertRaises(ConfigError):
                    self.go(env)
                self.assertFalse(self.svg.exists())

    def test_readme_without_image_fails_before_writing(self):
        self.readme.write_text("# hi\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            self.go()
        self.assertFalse(self.svg.exists())


class ParseEmailsTest(unittest.TestCase):
    def test_trims_lowercases_and_drops_empty(self):
        self.assertEqual(parse_emails(" A@x.io,b@Y.io ,, "), frozenset({"a@x.io", "b@y.io"}))

import unittest
from datetime import date

from dossier.__main__ import ConfigError, bump_readme

README = ('<div align="center">\n'
          '  <img src="assets/dossier.svg?v=2026-10-05" width="100%" alt="Personnel file. Classified.">\n'
          "</div>\n")


class BumpReadmeTest(unittest.TestCase):
    def test_replaces_the_version(self):
        out = bump_readme(README, date(2026, 10, 6))
        self.assertIn("assets/dossier.svg?v=2026-10-06", out)
        self.assertNotIn("2026-10-05", out)

    def test_second_run_changes_nothing(self):
        once = bump_readme(README, date(2026, 10, 6))
        self.assertEqual(bump_readme(once, date(2026, 10, 6)), once)

    def test_missing_image_is_an_error(self):
        with self.assertRaises(ConfigError):
            bump_readme("# hello\n", date(2026, 10, 6))

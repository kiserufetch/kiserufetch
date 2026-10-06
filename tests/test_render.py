import re
import unittest
import xml.etree.ElementTree as ET
from datetime import date

from dossier.collect import Stats
from dossier.life import exhibit
from dossier.render import MAX_BYTES, render

DAY = date(2026, 10, 6)
STATS = Stats(public_repos=15, private_repos=11, total=2033, visible=115, claude=300, last24=3)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def svg_for(stats=STATS, seed=1234):
    return render(stats, exhibit(seed, stats.last24), day=DAY, seed=seed)


class RenderTest(unittest.TestCase):
    def test_is_well_formed_svg(self):
        root = ET.fromstring(svg_for())
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.get("width"), "880")

    def test_shows_live_fields(self):
        svg = svg_for()
        for text in ("15 public · 11 private", "COMMITS, 2026", "2 033 · visible to you: 115",
                     "claude · 300 of the above", "3 events · contents classified"):
            self.assertIn(text, svg)

    def test_single_event_is_singular(self):
        self.assertIn("1 event · contents classified", svg_for(Stats(15, 11, 2033, 115, 300, 1)))

    def test_caption_names_exhibit_date_and_seed(self):
        svg = svg_for(seed=0xABCD1234)
        self.assertIn("EXHIBIT Nº 279", svg)
        self.assertIn("recovered 06.10.2026 · seed 0x1234", svg)
        self.assertIn("specimen in motion", svg)

    def test_busy_day_animates_60_frames(self):
        svg = svg_for()
        self.assertEqual(svg.count('class="f'), 60)
        self.assertIn("@keyframes", svg)
        self.assertIn("prefers-reduced-motion", svg)

    def test_quiet_day_is_a_static_still_life(self):
        svg = svg_for(Stats(15, 11, 2033, 115, 300, 0))
        self.assertNotIn("@keyframes", svg)
        self.assertNotIn('class="f', svg)
        self.assertIn("no activity · still life", svg)
        self.assertIn("· still life</text>", svg)

    def test_stays_under_size_budget_on_heavy_days(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                svg = svg_for(Stats(15, 11, 9999, 115, 300, 500), seed=seed)
                self.assertLessEqual(len(svg.encode("utf-8")), MAX_BYTES)

    def test_has_no_external_references_or_addresses(self):
        svg = svg_for().replace('xmlns="http://www.w3.org/2000/svg"', "")
        self.assertNotIn("http", svg)
        self.assertNotIn("href", svg)
        self.assertNotIn("<script", svg)
        self.assertIsNone(EMAIL.search(svg))

    def test_embeds_both_font_weights(self):
        self.assertEqual(svg_for().count("data:font/woff2;base64,"), 2)

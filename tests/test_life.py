import unittest
from datetime import date
from unittest import mock

from dossier import life
from dossier.life import FRAMES, H, W, exhibit, mulberry32, seed_from, soup, step, still_life


class PrngTest(unittest.TestCase):
    def test_same_seed_same_sequence_in_unit_interval(self):
        a, b = mulberry32(42), mulberry32(42)
        xs = [a() for _ in range(200)]
        self.assertEqual(xs, [b() for _ in range(200)])
        self.assertTrue(all(0 <= x < 1 for x in xs))

    def test_different_seeds_differ(self):
        self.assertNotEqual(mulberry32(1)(), mulberry32(2)())

    def test_seed_from_depends_on_day_and_salt(self):
        d = date(2026, 10, 6)
        self.assertEqual(seed_from(d, "s"), seed_from(d, "s"))
        self.assertNotEqual(seed_from(d, "s"), seed_from(d, "t"))
        self.assertNotEqual(seed_from(d, "s"), seed_from(date(2026, 10, 7), "s"))
        self.assertTrue(0 <= seed_from(d, "s") < 2**32)


class StepTest(unittest.TestCase):
    def test_blinker_oscillates(self):
        horizontal = frozenset({(4, 5), (5, 5), (6, 5)})
        vertical = frozenset({(5, 4), (5, 5), (5, 6)})
        self.assertEqual(step(horizontal), vertical)
        self.assertEqual(step(vertical), horizontal)

    def test_edges_wrap_around(self):
        across = frozenset({(W - 1, 0), (0, 0), (1, 0)})
        self.assertEqual(step(across), frozenset({(0, H - 1), (0, 0), (0, 1)}))


class StillLifeTest(unittest.TestCase):
    def test_never_changes_for_100_seeds(self):
        for seed in range(100):
            with self.subTest(seed=seed):
                cells = still_life(mulberry32(seed))
                self.assertTrue(cells)
                self.assertEqual(step(cells), cells)

    def test_keeps_one_cell_margin_from_edges(self):
        for seed in range(100):
            for x, y in still_life(mulberry32(seed)):
                self.assertTrue(1 <= x <= W - 2 and 1 <= y <= H - 2, (seed, x, y))


class ExhibitTest(unittest.TestCase):
    def test_same_seed_same_frames(self):
        self.assertEqual(exhibit(7, 5), exhibit(7, 5))

    def test_quiet_day_is_one_still_frame(self):
        ex = exhibit(7, 0)
        self.assertFalse(ex.moving)
        self.assertEqual(len(ex.frames), 1)
        self.assertEqual(step(ex.frames[0]), ex.frames[0])

    def test_busy_day_has_60_frames_with_ghosts(self):
        ex = exhibit(7, 5)
        self.assertTrue(ex.moving)
        self.assertEqual(len(ex.frames), FRAMES)
        self.assertEqual(len(ex.ghosts), FRAMES)
        for k in range(1, FRAMES):
            self.assertEqual(ex.frames[k], step(ex.frames[k - 1]))
            self.assertEqual(ex.ghosts[k], ex.frames[k - 1] - ex.frames[k])

    def test_dead_soup_is_reseeded(self):
        alive = soup(mulberry32(99), 0.35)
        with mock.patch.object(life, "soup", side_effect=[frozenset(), alive]) as fake:
            ex = exhibit(7, 5)
        self.assertEqual(fake.call_count, 2)
        self.assertGreaterEqual(len(ex.frames[-1]), life.MIN_ALIVE)

    def test_gives_up_after_five_attempts(self):
        with mock.patch.object(life, "soup", return_value=frozenset()) as fake:
            ex = exhibit(7, 5)
        self.assertEqual(fake.call_count, life.ATTEMPTS)
        self.assertTrue(ex.moving)
        self.assertEqual(len(ex.frames), FRAMES)

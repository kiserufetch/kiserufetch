"""Conway's Life exhibit: a seeded soup on busy days, a still life on quiet ones."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Callable

W, H = 30, 24
FRAMES = 60
WARMUP = 16
MIN_ALIVE = 10
ATTEMPTS = 5

_M32 = 0xFFFFFFFF

PATTERNS = {
    "block": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "beehive": [(1, 0), (2, 0), (0, 1), (3, 1), (1, 2), (2, 2)],
    "loaf": [(1, 0), (2, 0), (0, 1), (3, 1), (1, 2), (3, 2), (2, 3)],
    "boat": [(0, 0), (1, 0), (0, 1), (2, 1), (1, 2)],
    "tub": [(1, 0), (0, 1), (2, 1), (1, 2)],
    "pond": [(1, 0), (2, 0), (0, 1), (3, 1), (0, 2), (3, 2), (1, 3), (2, 3)],
    "ship": [(0, 0), (1, 0), (0, 1), (2, 1), (1, 2), (2, 2)],
}


def mulberry32(seed: int) -> Callable[[], float]:
    """Small portable PRNG: the same seed gives the same sequence on any Python version."""
    state = seed & _M32

    def rand() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _M32
        t = ((state ^ (state >> 15)) * (state | 1)) & _M32
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & _M32)) & _M32) ^ t
        return ((t ^ (t >> 14)) & _M32) / 4294967296

    return rand


def seed_from(day: date, salt: str) -> int:
    digest = hashlib.sha256((day.isoformat() + salt).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def step(cells: frozenset) -> frozenset:
    counts: dict[tuple[int, int], int] = {}
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    key = ((x + dx) % W, (y + dy) % H)
                    counts[key] = counts.get(key, 0) + 1
    return frozenset(k for k, n in counts.items() if n == 3 or (n == 2 and k in cells))


def soup(rand: Callable[[], float], density: float) -> frozenset:
    return frozenset((x, y) for y in range(H) for x in range(W) if rand() < density)


def still_life(rand: Callable[[], float]) -> frozenset:
    """Up to 10 still-life patterns, at least two empty cells apart and one cell from the edge."""
    names = sorted(PATTERNS)
    taken: set[tuple[int, int]] = set()
    cells: set[tuple[int, int]] = set()
    placed = 0
    for _ in range(500):
        if placed == 10:
            break
        pts = PATTERNS[names[int(rand() * len(names))]]
        if rand() < 0.5:
            pts = [(b, a) for a, b in pts]
        w = max(p[0] for p in pts) + 1
        h = max(p[1] for p in pts) + 1
        if rand() < 0.5:
            pts = [(w - 1 - a, b) for a, b in pts]
        ox = 1 + int(rand() * (W - w - 1))
        oy = 1 + int(rand() * (H - h - 1))
        ring = {(x, y) for x in range(ox - 1, ox + w + 1) for y in range(oy - 1, oy + h + 1)}
        if ring & taken:
            continue
        taken |= ring
        cells |= {(ox + a, oy + b) for a, b in pts}
        placed += 1
    return frozenset(cells)


@dataclass(frozen=True)
class Exhibit:
    frames: tuple[frozenset, ...]
    ghosts: tuple[frozenset, ...]
    moving: bool


def exhibit(seed: int, events: int) -> Exhibit:
    rand = mulberry32(seed)
    if events <= 0:
        return Exhibit((still_life(rand),), (frozenset(),), False)
    density = 0.16 + min(events / 4, 8) * 0.03
    frames: list[frozenset] = []
    ghosts: list[frozenset] = []
    for _ in range(ATTEMPTS):
        cells = soup(rand, density)
        for _ in range(WARMUP - 1):
            cells = step(cells)
        frames, ghosts = [], []
        for _ in range(FRAMES):
            nxt = step(cells)
            frames.append(nxt)
            ghosts.append(cells - nxt)
            cells = nxt
        if len(frames[-1]) >= MIN_ALIVE:
            break
    return Exhibit(tuple(frames), tuple(ghosts), True)

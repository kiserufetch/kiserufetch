# Dossier Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the profile README with a self-updating SVG personnel file whose numbers come from the owner's real commits and whose "exhibit" (Conway's Life print) changes every day.

**Architecture:** A stdlib-only Python package `dossier/` with four focused modules: `github.py` (HTTP client), `collect.py` (counting rules → `Stats`), `life.py` (seeded Life frames or a still life), `render.py` (`Stats` + frames → SVG). `__main__.py` wires them together, writes `assets/dossier.svg` and bumps the `?v=` in `README.md`. A daily GitHub Action runs it and commits the result.

**Tech Stack:** Python 3.12 standard library (`urllib`, `json`, `hashlib`, `unittest`), GitHub REST API, GitHub Actions. `fonttools` only once, locally, to subset the font.

**Spec:** `docs/superpowers/specs/2026-10-06-dossier-profile-design.md`

## Global Constraints

- Runtime: Python 3.12, standard library only. `fonttools` is a one-off dev tool and never imported by `dossier/`.
- Day boundaries are UTC. Cron `5 0 * * *`.
- Account login `kiserufetch`. Claude commits are identified by `commit.author.email == "noreply@anthropic.com"`.
- SVG: width 880, ≤ 300 KB (`300 * 1024` bytes), no scripts, no external references.
- Public outputs (SVG, README, code, Action logs) never contain email addresses, private repository names or secrets. Errors name a repository only as `repo #<index>`.
- Secrets: `DOSSIER_TOKEN`, `DOSSIER_EMAILS` (comma-separated), `DOSSIER_SALT`.
- Field texts are verbatim from the spec: `PERSONNEL FILE`, `NO. KF-0001`, `SUBJECT kiserufetch`, `ALIAS Kiseru`, `OCCUPATION ██████ developer`, `LOCATION ███████████`, `ACTIVE SINCE 2018`, `REPOSITORIES {public} public · {private} private`, `COMMITS, {Y} {total} · visible to you: {visible}`, `ASSOCIATES claude · {claude} of the above`, `LAST 24H {n} event(s) · contents classified` / `no activity · still life`, `NOTES "Hello stranger."`, caption `EXHIBIT Nº {yday} · specimen in motion|still life` and `recovered {DD.MM.YYYY} · seed 0x{XXXX}`, footer `exhibit replaced daily at 00:00 UTC · previous exhibits destroyed`. `Nº` is `N` + U+00BA.
- Numbers use a regular space as thousands separator (`2 033`). English plural (`1 event`, `2 events`).
- Bot commit message: `chore(dossier): exhibit YYYY-MM-DD`.
- Our own commits on this branch end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run tests from the repo root: `python -m unittest discover -s tests -v`.

## Review Focus

1. A rate-limited `403` that survives all retries must fail the run; it must not be mistaken for a blocked repository and silently skipped (that would publish too-small numbers). Test in Task 3.
2. Commits with `author: null` or no email (unlinked addresses, imported history) are ignored without crashing. Test in Task 3.
3. A fork whose parent comparison returns `404` (parent deleted or made private) is skipped and the run continues. Test in Task 3.
4. A README edited so that the `assets/dossier.svg?v=` image is gone makes the run fail before any file is written, with a clear message. Test in Task 5.
5. A very busy day (hundreds of commits yesterday) keeps the soup density capped and the SVG within 300 KB. Test in Task 4.

---

### Task 1: Life exhibit (`life.py`)

**Files:**
- Create: `dossier/__init__.py`
- Create: `dossier/life.py`
- Create: `.gitignore`
- Test: `tests/test_life.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `W = 30`, `H = 24`, `FRAMES = 60`, `WARMUP = 16`, `MIN_ALIVE = 10`, `ATTEMPTS = 5`
  - `mulberry32(seed: int) -> Callable[[], float]` (values in `[0, 1)`)
  - `seed_from(day: date, salt: str) -> int` (32-bit)
  - `step(cells: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]` (torus)
  - `soup(rand, density: float) -> frozenset`
  - `still_life(rand) -> frozenset`
  - `@dataclass(frozen=True) Exhibit(frames: tuple[frozenset, ...], ghosts: tuple[frozenset, ...], moving: bool)`
  - `exhibit(seed: int, events: int) -> Exhibit`

- [ ] **Step 1: Write the failing tests**

`tests/test_life.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_life -v`
Expected: ERROR `ModuleNotFoundError: No module named 'dossier'`.

- [ ] **Step 3: Write the implementation**

`dossier/__init__.py`:

```python
"""Self-updating personnel file for the kiserufetch profile README."""
```

`.gitignore`:

```
__pycache__/
*.pyc
*.tmp
```

`dossier/life.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_life -v`
Expected: all tests PASS. If `test_dead_soup_is_reseeded` fails because seed 99 itself dies out, change `99` to the first seed in `range(100, 200)` whose soup survives and re-run.

- [ ] **Step 5: Commit**

```bash
git add .gitignore dossier/__init__.py dossier/life.py tests/test_life.py
git commit -m "feat(dossier): Life exhibit with still life for quiet days"
```

---

### Task 2: GitHub client (`github.py`)

**Files:**
- Create: `dossier/github.py`
- Test: `tests/test_github.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ApiError(status: int, where: str = "", *, limited: bool = False)` with attributes `status`, `where`, `limited`; `str()` never contains a URL.
  - `GitHubClient(token, *, opener=urllib.request.urlopen, sleep=time.sleep, retries=3, pause=5.0, log=print)`
    - `.get(path: str, params: dict | None = None) -> dict`
    - `.list(path: str, params: dict | None = None, key: str | None = None) -> list` (follows `Link: rel="next"`; `key` picks a nested list, e.g. `"commits"` for compare)
  - `next_link(header: str | None) -> str | None`

- [ ] **Step 1: Write the failing tests**

`tests/test_github.py`:

```python
import json
import unittest
import urllib.error
from email.message import Message

from dossier.github import ApiError, GitHubClient, next_link


def headers(**values):
    msg = Message()
    for key, value in values.items():
        msg[key.replace("_", "-")] = value
    return msg


class FakeResponse:
    def __init__(self, body, hdrs=None):
        self._body = json.dumps(body).encode()
        self.headers = hdrs if hdrs is not None else headers()

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status, hdrs=None):
    return urllib.error.HTTPError(
        "https://api.github.com/repos/me/secret", status, "error", hdrs if hdrs is not None else headers(), None
    )


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def client(opener, sleeps=None):
    sleep = sleeps.append if sleeps is not None else (lambda seconds: None)
    return GitHubClient("tok", opener=opener, sleep=sleep, log=lambda *a: None)


class ClientTest(unittest.TestCase):
    def test_get_sends_auth_and_api_version(self):
        opener = FakeOpener(FakeResponse({"ok": 1}))
        self.assertEqual(client(opener).get("/user"), {"ok": 1})
        request = opener.requests[0]
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")

    def test_list_follows_next_links_and_encodes_params(self):
        opener = FakeOpener(
            FakeResponse([1, 2], headers(Link='<https://api.github.com/user/repos?page=2>; rel="next", '
                                              '<https://api.github.com/user/repos?page=2>; rel="last"')),
            FakeResponse([3]),
        )
        self.assertEqual(client(opener).list("/user/repos", {"per_page": 100}), [1, 2, 3])
        self.assertEqual(opener.requests[0].full_url, "https://api.github.com/user/repos?per_page=100")
        self.assertEqual(opener.requests[1].full_url, "https://api.github.com/user/repos?page=2")

    def test_list_with_key_collects_nested_items(self):
        opener = FakeOpener(
            FakeResponse({"commits": ["a"]}, headers(Link='<https://api.github.com/x?page=2>; rel="next"')),
            FakeResponse({"commits": ["b"]}),
        )
        self.assertEqual(client(opener).list("/repos/a/b/compare/x...y", key="commits"), ["a", "b"])

    def test_server_errors_are_retried(self):
        sleeps = []
        opener = FakeOpener(http_error(502), http_error(503), FakeResponse({"ok": 1}))
        self.assertEqual(client(opener, sleeps).get("/user"), {"ok": 1})
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_three_retries(self):
        opener = FakeOpener(*[http_error(500) for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(len(opener.requests), 4)

    def test_rate_limited_403_is_retried_and_flagged(self):
        opener = FakeOpener(*[http_error(403, headers(x_ratelimit_remaining="0")) for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertTrue(ctx.exception.limited)
        self.assertEqual(len(opener.requests), 4)

    def test_client_errors_fail_immediately(self):
        for status in (401, 403, 404, 409, 451):
            with self.subTest(status=status):
                opener = FakeOpener(http_error(status))
                with self.assertRaises(ApiError) as ctx:
                    client(opener).get("/repos/me/secret")
                self.assertEqual(ctx.exception.status, status)
                self.assertFalse(ctx.exception.limited)
                self.assertEqual(len(opener.requests), 1)

    def test_network_errors_are_retried_then_reported_as_status_0(self):
        opener = FakeOpener(*[urllib.error.URLError("down") for _ in range(4)])
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/user")
        self.assertEqual(ctx.exception.status, 0)

    def test_error_text_never_contains_the_url(self):
        opener = FakeOpener(http_error(404))
        with self.assertRaises(ApiError) as ctx:
            client(opener).get("/repos/me/secret")
        self.assertNotIn("secret", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)


class NextLinkTest(unittest.TestCase):
    def test_parses_next_and_ignores_others(self):
        self.assertEqual(next_link('<https://a/2>; rel="next", <https://a/9>; rel="last"'), "https://a/2")
        self.assertIsNone(next_link('<https://a/1>; rel="prev"'))
        self.assertIsNone(next_link(None))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_github -v`
Expected: ERROR `ModuleNotFoundError: No module named 'dossier.github'`.

- [ ] **Step 3: Write the implementation**

`dossier/github.py`:

```python
"""Minimal GitHub REST client. Error messages never include URLs: Action logs are public."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

API = "https://api.github.com"
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


class ApiError(Exception):
    def __init__(self, status: int, where: str = "", *, limited: bool = False) -> None:
        self.status = status
        self.where = where
        self.limited = limited
        super().__init__(f"GitHub API error: HTTP {status}" + (f" ({where})" if where else ""))


def next_link(header: str | None) -> str | None:
    if not header:
        return None
    match = _NEXT.search(header)
    return match.group(1) if match else None


class GitHubClient:
    def __init__(self, token: str, *, opener=urllib.request.urlopen, sleep=time.sleep,
                 retries: int = 3, pause: float = 5.0, log=print) -> None:
        self._token = token
        self._open = opener
        self._sleep = sleep
        self._retries = retries
        self._pause = pause
        self._log = log

    def get(self, path: str, params: dict | None = None) -> Any:
        data, _ = self._request(self._url(path, params))
        return data

    def list(self, path: str, params: dict | None = None, key: str | None = None) -> list:
        url: str | None = self._url(path, params)
        items: list = []
        while url:
            data, headers = self._request(url)
            items.extend(data[key] if key else data)
            url = next_link(headers.get("Link"))
        return items

    @staticmethod
    def _url(path: str, params: dict | None) -> str:
        return API + path + ("?" + urlencode(params) if params else "")

    def _request(self, url: str):
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kiserufetch-dossier",
        })
        for attempt in range(self._retries + 1):
            try:
                with self._open(request, timeout=30) as response:
                    return json.load(response), response.headers
            except urllib.error.HTTPError as err:
                status = err.code
                remaining = (err.headers or {}).get("x-ratelimit-remaining")
                limited = status == 429 or (status == 403 and remaining == "0")
                if not (status >= 500 or limited) or attempt == self._retries:
                    raise ApiError(status, limited=limited) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == self._retries:
                    raise ApiError(0) from None
            self._log(f"retry {attempt + 1}/{self._retries}")
            self._sleep(self._pause * (attempt + 1))
        raise AssertionError("unreachable")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_github -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dossier/github.py tests/test_github.py
git commit -m "feat(dossier): GitHub client with pagination and retries"
```

---

### Task 3: Counting rules (`collect.py`)

**Files:**
- Create: `dossier/collect.py`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `ApiError` (with `.status`, `.limited`) from Task 2; a client with `.get(path, params=None)` and `.list(path, params=None, key=None)`.
- Produces:
  - `CLAUDE_EMAIL = "noreply@anthropic.com"`, `SKIP_STATUSES = frozenset({403, 404, 409, 451})`
  - `@dataclass(frozen=True) Stats(public_repos: int, private_repos: int, total: int, visible: int, claude: int, last24: int)`
  - `classify(commit: dict, login: str, emails: frozenset[str]) -> str | None` (`"user"`, `"claude"` or `None`)
  - `collect(client, *, login: str, emails: frozenset[str], today: date, log=print) -> Stats`

- [ ] **Step 1: Write the failing tests**

`tests/test_collect.py`:

```python
import unittest
from datetime import date

from dossier.collect import Stats, classify, collect
from dossier.github import ApiError

TODAY = date(2026, 10, 6)
EMAILS = frozenset({"me@example.com"})


def repo(name, private=False, fork=False):
    return {"full_name": f"me/{name}", "private": private, "fork": fork, "default_branch": "main"}


def commit(sha, when, email="me@example.com", login=None):
    return {"sha": sha, "author": {"login": login} if login else None,
            "commit": {"author": {"email": email, "date": when}}}


class FakeClient:
    def __init__(self, repos, commits=None, parents=None, ahead=None, errors=None):
        self.repos = repos
        self.commits = commits or {}
        self.parents = parents or {}
        self.ahead = ahead or {}
        self.errors = errors or {}
        self.calls = []

    @staticmethod
    def _repo(path):
        parts = path.split("/")
        return f"{parts[2]}/{parts[3]}"

    def get(self, path, params=None):
        self.calls.append(("get", path, params))
        name = self._repo(path)
        if name in self.errors:
            raise self.errors[name]
        return {"parent": self.parents.get(name)}

    def list(self, path, params=None, key=None):
        self.calls.append(("list", path, params))
        if path == "/user/repos":
            return self.repos
        name = self._repo(path)
        if name in self.errors:
            raise self.errors[name]
        if "/compare/" in path:
            return self.ahead[name]
        return self.commits.get(name, [])


def run(client, today=TODAY, logs=None):
    log = logs.append if logs is not None else (lambda *a: None)
    return collect(client, login="me", emails=EMAILS, today=today, log=log)


class ClassifyTest(unittest.TestCase):
    def test_user_by_login(self):
        self.assertEqual(classify(commit("a", "x", email="other@x.io", login="me"), "me", EMAILS), "user")

    def test_user_by_email_ignoring_case(self):
        self.assertEqual(classify(commit("a", "x", email="ME@Example.com"), "me", EMAILS), "user")

    def test_claude_by_email(self):
        c = commit("a", "x", email="noreply@anthropic.com", login="claude")
        self.assertEqual(classify(c, "me", EMAILS), "claude")

    def test_other_authors_are_ignored(self):
        c = commit("a", "x", email="bot@x.io", login="semantic-release-bot")
        self.assertIsNone(classify(c, "me", EMAILS))

    def test_null_author_and_missing_email_are_ignored(self):
        no_email = {"sha": "a", "author": None, "commit": {"author": {"date": "2026-10-05T00:00:00Z"}}}
        no_author = {"sha": "b", "author": None, "commit": {"author": None}}
        self.assertIsNone(classify(no_email, "me", EMAILS))
        self.assertIsNone(classify(no_author, "me", EMAILS))


class CollectTest(unittest.TestCase):
    def test_counts_repositories_by_visibility(self):
        client = FakeClient([repo("a"), repo("b", fork=True), repo("c", private=True)])
        stats = run(client)
        self.assertEqual((stats.public_repos, stats.private_repos), (2, 1))

    def test_totals_visible_claude_and_last24(self):
        client = FakeClient(
            [repo("pub"), repo("priv", private=True)],
            commits={
                "me/pub": [commit("p1", "2026-03-01T10:00:00Z")],
                "me/priv": [
                    commit("s1", "2026-10-05T12:00:00Z"),
                    commit("s2", "2026-10-05T13:00:00Z", email="noreply@anthropic.com", login="claude"),
                    commit("s3", "2026-02-01T00:00:00Z", email="someone@else.io", login="someone"),
                ],
            },
        )
        self.assertEqual(run(client), Stats(public_repos=1, private_repos=1, total=3, visible=1, claude=1, last24=2))

    def test_utc_day_boundaries(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2026-10-04T23:59:59Z"),
            commit("b", "2026-10-05T00:00:00Z"),
            commit("c", "2026-10-05T23:59:59Z"),
            commit("d", "2026-10-06T00:00:00Z"),
        ]})
        stats = run(client)
        self.assertEqual((stats.total, stats.last24), (4, 2))

    def test_commits_before_the_year_are_ignored(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2025-12-31T23:59:59Z"),
            commit("b", "2026-01-01T00:00:00Z"),
        ]})
        self.assertEqual(run(client).total, 1)

    def test_since_starts_at_new_year(self):
        client = FakeClient([repo("r")])
        run(client)
        self.assertIn(("list", "/repos/me/r/commits", {"since": "2026-01-01T00:00:00Z", "per_page": 100}),
                      client.calls)

    def test_january_first_sees_yesterday_but_starts_a_new_year(self):
        client = FakeClient([repo("r")], commits={"me/r": [
            commit("a", "2026-12-31T10:00:00Z"),
            commit("b", "2026-06-01T10:00:00Z"),
        ]})
        stats = run(client, today=date(2027, 1, 1))
        self.assertEqual((stats.total, stats.last24), (0, 1))
        self.assertIn(("list", "/repos/me/r/commits", {"since": "2026-12-31T00:00:00Z", "per_page": 100}),
                      client.calls)

    def test_fork_counts_only_commits_ahead_of_parent(self):
        client = FakeClient(
            [repo("fork", fork=True)],
            parents={"me/fork": {"owner": {"login": "up"}, "default_branch": "dev"}},
            ahead={"me/fork": [commit("mine", "2026-09-01T00:00:00Z"), commit("old", "2025-05-01T00:00:00Z")]},
            commits={"me/fork": [commit("upstream", "2026-09-02T00:00:00Z", email="noreply@anthropic.com")]},
        )
        stats = run(client)
        self.assertEqual((stats.total, stats.claude), (1, 0))
        self.assertIn(("list", "/repos/me/fork/compare/up:dev...main", {"per_page": 100}), client.calls)

    def test_fork_without_parent_uses_the_commit_list(self):
        client = FakeClient([repo("fork", fork=True)],
                            commits={"me/fork": [commit("a", "2026-09-01T00:00:00Z")]})
        self.assertEqual(run(client).total, 1)

    def test_same_commit_in_two_repos_counts_once_and_is_visible(self):
        shared = commit("same", "2026-05-05T00:00:00Z")
        client = FakeClient([repo("priv", private=True), repo("pub")],
                            commits={"me/priv": [shared], "me/pub": [shared]})
        stats = run(client)
        self.assertEqual((stats.total, stats.visible), (1, 1))

    def test_unavailable_repos_are_skipped_by_index(self):
        for status in (403, 404, 409, 451):
            with self.subTest(status=status):
                logs = []
                client = FakeClient([repo("ok"), repo("secret", private=True)],
                                    commits={"me/ok": [commit("a", "2026-05-05T00:00:00Z")]},
                                    errors={"me/secret": ApiError(status)})
                self.assertEqual(run(client, logs=logs).total, 1)
                self.assertEqual(logs, [f"skip repo #2: HTTP {status}"])

    def test_fork_whose_parent_is_gone_is_skipped(self):
        class ParentGone(FakeClient):
            def list(self, path, params=None, key=None):
                if "/compare/" in path:
                    raise ApiError(404)
                return super().list(path, params, key)

        client = ParentGone([repo("fork", fork=True)],
                            parents={"me/fork": {"owner": {"login": "up"}, "default_branch": "main"}})
        self.assertEqual(run(client).total, 0)

    def test_rate_limit_is_not_mistaken_for_a_blocked_repo(self):
        client = FakeClient([repo("r")], errors={"me/r": ApiError(403, limited=True)})
        with self.assertRaises(ApiError) as ctx:
            run(client)
        self.assertTrue(ctx.exception.limited)

    def test_other_errors_name_the_repo_by_index_only(self):
        client = FakeClient([repo("ok"), repo("secret", private=True)], errors={"me/secret": ApiError(500)})
        with self.assertRaises(ApiError) as ctx:
            run(client)
        self.assertEqual(ctx.exception.status, 500)
        self.assertIn("repo #2", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_collect -v`
Expected: ERROR `ModuleNotFoundError: No module named 'dossier.collect'`.

- [ ] **Step 3: Write the implementation**

`dossier/collect.py`:

```python
"""Counting rules from the spec. Only numbers leave this module."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .github import ApiError

CLAUDE_EMAIL = "noreply@anthropic.com"
SKIP_STATUSES = frozenset({403, 404, 409, 451})


@dataclass(frozen=True)
class Stats:
    public_repos: int
    private_repos: int
    total: int
    visible: int
    claude: int
    last24: int


@dataclass
class _Seen:
    when: datetime
    kind: str
    public: bool


def classify(commit: dict, login: str, emails: frozenset[str]) -> str | None:
    author = (commit.get("commit") or {}).get("author") or {}
    email = (author.get("email") or "").lower()
    if email == CLAUDE_EMAIL:
        return "claude"
    account = commit.get("author") or {}
    if account.get("login") == login or email in emails:
        return "user"
    return None


def _authored(commit: dict) -> datetime:
    raw = commit["commit"]["author"]["date"]
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _repo_commits(client, repo: dict, window: datetime) -> list[dict]:
    full = repo["full_name"]
    if repo.get("fork"):
        parent = client.get(f"/repos/{full}").get("parent")
        if parent:
            base = f'{parent["owner"]["login"]}:{parent["default_branch"]}'
            path = f"/repos/{full}/compare/{base}...{repo['default_branch']}"
            return client.list(path, {"per_page": 100}, key="commits")
    since = window.strftime("%Y-%m-%dT%H:%M:%SZ")
    return client.list(f"/repos/{full}/commits", {"since": since, "per_page": 100})


def collect(client, *, login: str, emails: frozenset[str], today: date, log=print) -> Stats:
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    yesterday_start = today_start - timedelta(days=1)
    year_start = datetime(today.year, 1, 1, tzinfo=timezone.utc)
    window = min(year_start, yesterday_start)

    repos = client.list("/user/repos", {"affiliation": "owner", "per_page": 100})
    seen: dict[str, _Seen] = {}
    for index, repo in enumerate(repos, 1):
        try:
            commits = _repo_commits(client, repo, window)
        except ApiError as err:
            if err.status in SKIP_STATUSES and not err.limited:
                log(f"skip repo #{index}: HTTP {err.status}")
                continue
            raise ApiError(err.status, f"repo #{index}", limited=err.limited) from None
        public = not repo["private"]
        for commit in commits:
            kind = classify(commit, login, emails)
            if kind is None:
                continue
            when = _authored(commit)
            if when < window:
                continue
            entry = seen.get(commit["sha"])
            if entry is None:
                seen[commit["sha"]] = _Seen(when, kind, public)
            else:
                entry.public = entry.public or public

    year = [s for s in seen.values() if s.when >= year_start]
    return Stats(
        public_repos=sum(1 for r in repos if not r["private"]),
        private_repos=sum(1 for r in repos if r["private"]),
        total=len(year),
        visible=sum(1 for s in year if s.public),
        claude=sum(1 for s in year if s.kind == "claude"),
        last24=sum(1 for s in seen.values() if yesterday_start <= s.when < today_start),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_collect -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dossier/collect.py tests/test_collect.py
git commit -m "feat(dossier): commit counting rules"
```

---

### Task 4: Font subset and SVG renderer (`render.py`)

**Files:**
- Create: `dossier/font/CourierPrime-Regular.woff2`, `dossier/font/CourierPrime-Bold.woff2`, `dossier/font/OFL.txt`
- Create: `dossier/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Stats` (Task 3); `Exhibit`, `FRAMES`, `W`, `H`, `exhibit` (Task 1).
- Produces:
  - `MAX_BYTES = 300 * 1024`
  - `render(stats: Stats, ex: Exhibit, *, day: date, seed: int) -> str`

- [ ] **Step 1: Subset the font (one-off, dev only)**

Use a throwaway venv and download directory in the scratchpad (`$SCRATCH`), never inside the repo:

```bash
python -m venv "$SCRATCH/fontenv"
"$SCRATCH/fontenv/Scripts/python" -m pip install --quiet fonttools brotli
mkdir -p "$SCRATCH/fonts-src"
for f in CourierPrime-Regular.ttf CourierPrime-Bold.ttf OFL.txt; do
  curl -sSL -o "$SCRATCH/fonts-src/$f" "https://raw.githubusercontent.com/google/fonts/main/ofl/courierprime/$f"
done
mkdir -p dossier/font
for w in Regular Bold; do
  "$SCRATCH/fontenv/Scripts/pyftsubset" "$SCRATCH/fonts-src/CourierPrime-$w.ttf" \
    --unicodes="U+0020-007E,U+00B7,U+00BA" --flavor=woff2 --layout-features='' \
    --no-hinting --desubroutinize --output-file="dossier/font/CourierPrime-$w.woff2"
done
cp "$SCRATCH/fonts-src/OFL.txt" dossier/font/OFL.txt
ls -l dossier/font
```

Expected: two `.woff2` files, each well under 30 KB, and `OFL.txt`.

- [ ] **Step 2: Write the failing tests**

`tests/test_render.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m unittest tests.test_render -v`
Expected: ERROR `ModuleNotFoundError: No module named 'dossier.render'`.

- [ ] **Step 4: Write the implementation**

`dossier/render.py`:

```python
"""Stats + exhibit -> a self-contained SVG personnel file (layout of mockup A)."""
from __future__ import annotations

import base64
from datetime import date
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from .collect import Stats
from .life import FRAMES, H, W, Exhibit

FONT_DIR = Path(__file__).parent / "font"
MAX_BYTES = 300 * 1024

PAPER, INK, STAMP, REDACT = "#e3e4e0", "#1b1a18", "#b3261e", "#141414"
PRINT_BG, PRINT_INK, PRINT_FRAME, CLIP = "#121214", "#ebe8e1", "#f7f6f2", "#7d838c"

WIDTH, HEIGHT = 880, 452
CH = 9                # advance of one Courier Prime character at 15px
LABEL_X, VALUE_X = 40, 172
ROW0, ROW = 104, 26
CELL = 10             # 30x24 cells -> 300x240 print
FRAME_STEP = 0.15     # seconds per generation: 60 frames -> 9 s loop
GHOST = ' opacity=".35"'

STAMP_SVG = (
    f'<g transform="translate(360 356) rotate(-9)" opacity=".82" fill="{STAMP}">'
    f'<rect x="-76" y="-23" width="152" height="38" fill="none" stroke="{STAMP}" stroke-width="3.5"/>'
    '<text x="2" y="6" font-size="24" font-weight="700" letter-spacing="5" text-anchor="middle">PRIVATE</text>'
    "</g>"
)
CLIP_SVG = (
    '<path transform="translate(22 -20) scale(1.25)" d="M3 12V5a3 3 0 0 1 6 0v22a4.5 4.5 0 0 1-9 0V9" '
    f'fill="none" stroke="{CLIP}" stroke-width="1.4" stroke-linecap="round"/>'
)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _plural(n: int, word: str) -> str:
    return f"{fmt_int(n)} {word}" + ("" if n == 1 else "s")


@lru_cache(maxsize=1)
def font_css() -> str:
    faces = []
    for weight, name in ((400, "CourierPrime-Regular.woff2"), (700, "CourierPrime-Bold.woff2")):
        data = base64.b64encode((FONT_DIR / name).read_bytes()).decode("ascii")
        faces.append(f"@font-face{{font-family:CP;font-weight:{weight};"
                     f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "".join(faces)


def _rows(stats: Stats, year: int) -> list[tuple[str, list[tuple[str, object]]]]:
    last24 = (f"{_plural(stats.last24, 'event')} · contents classified"
              if stats.last24 else "no activity · still life")
    return [
        ("SUBJECT", [("t", "kiserufetch")]),
        ("ALIAS", [("t", "Kiseru")]),
        ("OCCUPATION", [("r", 6), ("t", "developer")]),
        ("LOCATION", [("r", 11)]),
        ("ACTIVE SINCE", [("t", "2018")]),
        ("REPOSITORIES", [("t", f"{fmt_int(stats.public_repos)} public · {fmt_int(stats.private_repos)} private")]),
        (f"COMMITS, {year}", [("t", f"{fmt_int(stats.total)} · visible to you: {fmt_int(stats.visible)}")]),
        ("ASSOCIATES", [("t", f"claude · {fmt_int(stats.claude)} of the above")]),
        ("LAST 24H", [("t", last24)]),
        ("NOTES", [("t", '"Hello stranger."'), ("r", 7), ("r", 4)]),
        ("", [("r", 10), ("r", 6)]),
    ]


def _text(x: float, y: float, value: str, attrs: str = "") -> str:
    return f'<text x="{x:g}" y="{y:g}"{attrs}>{escape(value)}</text>'


def _fields(stats: Stats, year: int) -> str:
    out = []
    for i, (label, pieces) in enumerate(_rows(stats, year)):
        y = ROW0 + i * ROW
        if label:
            out.append(_text(LABEL_X, y, label))
        x = VALUE_X
        for kind, value in pieces:
            if kind == "t":
                out.append(_text(x, y, value))
                x += (len(value) + 1) * CH
            else:
                out.append(f'<rect x="{x:g}" y="{y - 12}" width="{value * CH}" height="15" fill="{REDACT}"/>')
                x += (value + 1) * CH
    return "".join(out)


def _path(cells: frozenset, extra: str = "") -> str:
    if not cells:
        return ""
    s = CELL - 2
    d = "".join(f"M{x * CELL + 1} {y * CELL + 1}h{s}v{s}h-{s}z" for x, y in sorted(cells))
    return f'<path d="{d}"{extra}/>'


def _cells(ex: Exhibit) -> str:
    if not ex.moving:
        return _path(ex.frames[0])
    out = []
    for k, (alive, ghost) in enumerate(zip(ex.frames, ex.ghosts)):
        cls = "f f0" if k == 0 else "f"
        out.append(f'<g class="{cls}" style="animation-delay:{k * FRAME_STEP:.2f}s">'
                   f"{_path(ghost, GHOST)}{_path(alive)}</g>")
    return "".join(out)


def _print(ex: Exhibit, day: date, seed: int) -> str:
    genre = "specimen in motion" if ex.moving else "still life"
    caption = (
        f'<text x="12" y="270" font-size="12.5"><tspan font-weight="700">EXHIBIT Nº '
        f"{day.timetuple().tm_yday}</tspan> · {genre}</text>"
        + _text(12, 288, f"recovered {day:%d.%m.%Y} · seed 0x{seed & 0xFFFF:04X}", ' font-size="12.5"')
    )
    return (
        '<g transform="translate(520 92) rotate(2.2 160 150)">'
        f'<rect width="320" height="300" fill="{PRINT_FRAME}" filter="url(#sh)"/>'
        f'<rect x="10" y="10" width="{W * CELL}" height="{H * CELL}" fill="{PRINT_BG}"/>'
        f'<g transform="translate(10 10)" fill="{PRINT_INK}">{_cells(ex)}</g>'
        f"{caption}{CLIP_SVG}</g>"
    )


def render(stats: Stats, ex: Exhibit, *, day: date, seed: int) -> str:
    style = font_css()
    if ex.moving:
        style += (
            f".f{{visibility:hidden;animation:fr {FRAMES * FRAME_STEP:g}s linear infinite}}"
            ".f0{visibility:visible}"
            f"@keyframes fr{{0%{{visibility:visible}}{100 / FRAMES:.4f}%{{visibility:hidden}}"
            "100%{visibility:hidden}}"
            "@media (prefers-reduced-motion:reduce){.f{animation:none}}"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Personnel file. Classified." '
        f"font-family=\"CP, 'Courier New', Courier, monospace\" font-size=\"15\" fill=\"{INK}\">"
        "<title>Personnel file. Classified.</title>"
        f"<style>{style}</style>"
        '<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="150%">'
        '<feDropShadow dx="0" dy="5" stdDeviation="6" flood-color="#000" flood-opacity=".28"/></filter></defs>'
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="3" fill="{PAPER}"/>'
        + _text(LABEL_X, 56, "PERSONNEL FILE", ' font-weight="700" letter-spacing="1"')
        + _text(WIDTH - 40, 56, "NO. KF-0001", ' font-weight="700" letter-spacing="1" text-anchor="end"')
        + f'<rect x="{LABEL_X}" y="66" width="{WIDTH - 80}" height="2" fill="{INK}"/>'
        + _fields(stats, day.year)
        + _print(ex, day, seed)
        + STAMP_SVG
        + _text(LABEL_X, HEIGHT - 20, "exhibit replaced daily at 00:00 UTC · previous exhibits destroyed",
                ' font-size="12.5" opacity=".7"')
        + "</svg>"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_render -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add dossier/font dossier/render.py tests/test_render.py
git commit -m "feat(dossier): SVG personnel file renderer with embedded font"
```

---

### Task 5: Entry point, README and cleanup (`__main__.py`)

**Files:**
- Create: `dossier/__main__.py`
- Modify: `README.md` (replace entirely)
- Delete: `assets/hello.gif`
- Test: `tests/test_readme.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `collect`, `Stats` (Task 3); `GitHubClient`, `ApiError` (Task 2); `exhibit`, `seed_from` (Task 1); `render`, `MAX_BYTES` (Task 4).
- Produces:
  - `ConfigError(Exception)`
  - `parse_emails(raw: str) -> frozenset[str]`
  - `bump_readme(text: str, day: date) -> str`
  - `run(env, *, client=None, today=None, svg_path=SVG_PATH, readme_path=README_PATH, log=print) -> None`
  - `main() -> int` (`python -m dossier`)

- [ ] **Step 1: Write the failing tests**

`tests/test_readme.py`:

```python
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
```

`tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_readme tests.test_main -v`
Expected: ERROR `ModuleNotFoundError: No module named 'dossier.__main__'`.

- [ ] **Step 3: Write the implementation**

`dossier/__main__.py`:

```python
"""python -m dossier: count, draw, write assets/dossier.svg and bump README.md."""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from .collect import collect
from .github import ApiError, GitHubClient
from .life import exhibit, seed_from
from .render import MAX_BYTES, render

LOGIN = "kiserufetch"
ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "dossier.svg"
README_PATH = ROOT / "README.md"
SECRETS = ("DOSSIER_TOKEN", "DOSSIER_EMAILS", "DOSSIER_SALT")
_IMAGE = re.compile(r"assets/dossier\.svg\?v=[0-9-]+")


class ConfigError(Exception):
    pass


def parse_emails(raw: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def bump_readme(text: str, day: date) -> str:
    new, count = _IMAGE.subn(f"assets/dossier.svg?v={day.isoformat()}", text)
    if count == 0:
        raise ConfigError("README.md has no assets/dossier.svg?v=... image")
    return new


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def run(env, *, client=None, today: date | None = None, svg_path: Path = SVG_PATH,
        readme_path: Path = README_PATH, log=print) -> None:
    missing = [name for name in SECRETS if not env.get(name)]
    if missing:
        raise ConfigError("missing secrets: " + ", ".join(missing))
    today = today or datetime.now(timezone.utc).date()
    client = client or GitHubClient(env["DOSSIER_TOKEN"], log=log)

    stats = collect(client, login=LOGIN, emails=parse_emails(env["DOSSIER_EMAILS"]), today=today, log=log)
    seed = seed_from(today, env["DOSSIER_SALT"])
    svg = render(stats, exhibit(seed, stats.last24), day=today, seed=seed)
    size = len(svg.encode("utf-8"))
    if size > MAX_BYTES:
        raise ConfigError(f"dossier.svg would be {size} bytes, limit is {MAX_BYTES}")
    readme = bump_readme(readme_path.read_text(encoding="utf-8"), today)

    _write_atomic(svg_path, svg)
    _write_atomic(readme_path, readme)
    log(f"repos {stats.public_repos} public / {stats.private_repos} private; "
        f"commits {today.year}: {stats.total} (visible {stats.visible}, claude {stats.claude}); "
        f"last 24h: {stats.last24}; svg {size} bytes")


def main() -> int:
    try:
        run(os.environ)
    except (ConfigError, ApiError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Replace README and delete the old GIF**

`README.md` (whole file):

```html
<div align="center">
  <img src="assets/dossier.svg?v=2026-10-06" width="100%" alt="Personnel file. Classified.">
</div>
```

```bash
git rm assets/hello.gif
```

- [ ] **Step 5: Run the whole suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add dossier/__main__.py tests/test_readme.py tests/test_main.py README.md
git commit -m "feat(dossier): entry point, README with the dossier, drop hello.gif"
```

---

### Task 6: Daily workflow and first real render

**Files:**
- Create: `.github/workflows/dossier.yml`
- Generate: `assets/dossier.svg`
- Modify: `README.md` (`?v=` bumped by the run)

**Interfaces:**
- Consumes: `python -m dossier` (Task 5) and the three secrets.
- Produces: the scheduled job and the first committed `assets/dossier.svg`.

- [ ] **Step 1: Write the workflow**

`.github/workflows/dossier.yml`:

```yaml
name: dossier

on:
  schedule:
    - cron: "5 0 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: dossier
  cancel-in-progress: false

jobs:
  exhibit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Render dossier
        env:
          DOSSIER_TOKEN: ${{ secrets.DOSSIER_TOKEN }}
          DOSSIER_EMAILS: ${{ secrets.DOSSIER_EMAILS }}
          DOSSIER_SALT: ${{ secrets.DOSSIER_SALT }}
        run: python -m dossier
      - name: Commit exhibit
        run: |
          if git diff --quiet -- assets/dossier.svg README.md && [ -z "$(git ls-files --others --exclude-standard assets/dossier.svg)" ]; then
            echo "nothing changed"
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add assets/dossier.svg README.md
          git commit -m "chore(dossier): exhibit $(date -u +%F)"
          git push
```

- [ ] **Step 2: Render locally with real data**

Use the local `gh` token (read access to private repos) and the owner's addresses from the environment only, never from a file in the repo:

```bash
DOSSIER_TOKEN="$(gh auth token)" \
DOSSIER_EMAILS="<owner addresses, comma-separated>" \
DOSSIER_SALT="local-preview" \
python -m dossier
```

Expected: one log line like `repos 15 public / 11 private; commits 2026: ~2033 (visible ~115, claude 300); last 24h: N; svg … bytes`. Numbers may differ slightly from the spec's reference (2 033 / 115 / 300) because of SHA de-duplication and today's new commits. No repository names in the output.

- [ ] **Step 3: Look at the result**

Open `assets/dossier.svg` in a browser at 100% and check: font is Courier Prime (not a fallback), the print is rotated with the paperclip on top, frames animate (or the still life is static), the stamp does not cover any live value, nothing is clipped at the right or bottom edge.

- [ ] **Step 4: Run the suite once more and commit**

```bash
python -m unittest discover -s tests -v
git add .github/workflows/dossier.yml assets/dossier.svg README.md
git commit -m "ci(dossier): daily workflow and first exhibit"
```

- [ ] **Step 5: Hand-off checklist for the owner (not automated)**

1. Create a fine-grained token: Settings → Developer settings → Fine-grained tokens → Repository access: All repositories → Permissions: Contents (read), Metadata (read).
2. Add repository secrets in `kiserufetch/kiserufetch`: `DOSSIER_TOKEN`, `DOSSIER_EMAILS`, `DOSSIER_SALT` (any long random string).
3. Merge `dossier-profile` into `main` and push.
4. Actions → dossier → Run workflow once; check the profile page in light and dark themes.

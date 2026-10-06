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

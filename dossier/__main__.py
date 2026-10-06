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

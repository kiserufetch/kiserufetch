"""Stats + exhibit -> a self-contained SVG personnel file (layout of mockup A)."""
from __future__ import annotations

import base64
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
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


def _rows(stats: Stats, year: int) -> list[tuple[str, list[tuple[str, Any]]]]:
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

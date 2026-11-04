"""Tekken 4 Online's rank badges: our own pictures, one per rank, made from nothing but this script.

Tekken 4 ranked uses Tekken 7's rank NAMES (the T4 lobby's t4lobby/ranks.py, docs/T4_ONLINE.md "Ranked"). Namco's
rank emblems are theirs and are never shipped or downloaded: these badges are drawn here from simple shapes --
a plate in the rank group's colour (Tekken 7's colour groups), an emblem whose shape names the group, a pip per
step inside the group, and the rank's name.

    python tools/make_rank_badges.py                       openrecomp/ui/assets/ranks/t4_rank_NN.svg (the launcher's)
    python tools/make_rank_badges.py --png DIR [--height H]  PNG copies (needs PySide6; previews, posts)
    python tools/make_rank_badges.py --header FILE         the same design as a C++ table for the T4 game's own
                                                           name plates (runtime/tekken4_rank_badges.h in the T4 port)
    python tools/make_rank_badges.py --sheet FILE.svg      every badge on one page (review)
    python tools/make_rank_badges.py --check               the committed SVGs are what this script makes

The SVGs are committed (text, our own art); PNGs are not (.gitignore). The game draws the same elements itself
(raylib shapes and text) from the header, so the launcher and the game show the same badge.
"""
import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "openrecomp", "ui", "assets", "ranks")
W, H = 200, 100                     # 2:1 like the T5DR plates the online table already makes room for

# Tekken 7's ranks, in order (= the T4 lobby's tiers). Index = tier.
NAMES = ["Beginner", "9th Kyu", "8th Kyu", "7th Kyu", "6th Kyu", "5th Kyu", "4th Kyu", "3rd Kyu", "2nd Kyu", "1st Kyu",
         "1st Dan", "2nd Dan", "3rd Dan", "Initiate", "Mentor", "Expert", "Grand Master", "Brawler", "Marauder",
         "Fighter", "Vanguard", "Warrior", "Vindicator", "Juggernaut", "Usurper", "Vanquisher", "Destroyer", "Savior",
         "Overlord", "Genbu", "Byakko", "Seiryu", "Suzaku", "Mighty Ruler", "Revered Ruler", "Divine Ruler",
         "Eternal Ruler", "Fujin", "Raijin", "Yaksa", "Ryujin", "Emperor", "Tekken King", "Tekken God",
         "True Tekken God", "Tekken God Prime", "Tekken God Omega"]

# (first tier, last tier, key, plate, light, dark, emblem): emblem = ("poly", sides) or ("star", points); 0 sides = circle
GROUPS = [
    (0, 0, "beginner", "#7d838c", "#c9ccd1", "#3c4047", ("poly", 0)),
    (1, 9, "kyu", "#8b5a2b", "#d29a5e", "#40260f", ("poly", 3)),
    (10, 12, "dan", "#8f99a4", "#e6ebf0", "#4a525b", ("poly", 4)),
    (13, 16, "lightblue", "#2f9ccc", "#a6e2f8", "#15506b", ("poly", 5)),
    (17, 20, "green", "#2f9446", "#9ee0a8", "#164d22", ("poly", 6)),
    (21, 24, "yellow", "#c9a514", "#f7e481", "#6b540a", ("star", 4)),
    (25, 28, "orange", "#de7012", "#f8b673", "#733605", ("star", 5)),
    (29, 32, "red", "#c22a26", "#f39a94", "#5e0f0d", ("star", 6)),
    (33, 36, "ruler", "#8f2479", "#e895d8", "#440c39", ("star", 7)),
    (37, 40, "blue", "#2449c4", "#98aef7", "#0f2063", ("star", 8)),
    (41, 42, "purple", "#6526c4", "#bb98f7", "#2f0f63", ("star", 10)),
    (43, 46, "gold", "#cf9a12", "#ffe58a", "#614606", ("star", 12)),
]
OMEGA = 46                          # the top rank: a black plate with a gold rim


def group(tier):
    for g in GROUPS:
        if g[0] <= tier <= g[1]:
            return g
    return GROUPS[0]


def spec(tier):
    """Everything the badge of `tier` is made of (also the C++ header's row)."""
    lo, hi, key, plate, light, dark, (kind, n) = group(tier)
    pips = tier - lo + 1 if hi > lo else 0
    if tier == OMEGA:
        plate, dark = "#16130c", "#000000"
    return dict(tier=tier, name=NAMES[tier], group=key, plate=plate, light=light, dark=dark, kind=kind, n=n,
                pips=pips, of=hi - lo + 1)


# ---------------------------------------------------------------------------------------------- geometry (shared)
def plate_points():
    """The plate: a long hexagon with pointed ends."""
    return [(14, 6), (186, 6), (198, 50), (186, 94), (14, 94), (2, 50)]


def emblem_points(kind, n, cx=50.0, cy=50.0, r=30.0):
    """The emblem's outline: a regular polygon (n sides; 0 = None, a circle) or an n-pointed star."""
    if kind == "poly":
        if n == 0:
            return None
        start = -math.pi / 2 if n % 2 else -math.pi / 2 + math.pi / n
        if n == 4:
            start = -math.pi / 2                       # a diamond, point up
        return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n))
                for i in range(n)]
    inner = r * (0.42 if n <= 6 else 0.55 if n <= 8 else 0.68)
    pts = []
    for i in range(2 * n):
        a = -math.pi / 2 + math.pi * i / n
        rr = r if i % 2 == 0 else inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def pip_points(pips, of):
    """Pip centres along the plate's lower edge, right of the emblem."""
    if not pips:
        return []
    step = 11.0 if of > 4 else 14.0
    x0 = 96.0
    return [(x0 + i * step, 80.0) for i in range(pips)]


def name_lines(name):
    """One line, or two at the space nearest the middle for long names."""
    if len(name) <= 9 or " " not in name:
        return [name.upper()]
    spaces = [i for i, c in enumerate(name) if c == " "]
    i = min(spaces, key=lambda k: abs(k - len(name) / 2))
    return [name[:i].upper(), name[i + 1:].upper()]


def name_size(lines):
    """Font size that fits the longest line into the plate's text area (about 92 units; bold caps ~0.7 em)."""
    return min(22.0, round(92.0 / (0.7 * max(len(x) for x in lines)), 1))


# ---------------------------------------------------------------------------------------------- SVG
def _pts(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def svg(tier):
    s = spec(tier)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
           f"<!-- Tekken 4 Online rank badge {tier}: {s['name']} (our own drawing, tools/make_rank_badges.py) -->",
           f'<polygon points="{_pts(plate_points())}" fill="{s["plate"]}" stroke="{s["light"]}" stroke-width="5" '
           'stroke-linejoin="round"/>',
           f'<polygon points="{_pts([(14, 10), (186, 10), (195, 44), (5, 44)])}" fill="{s["light"]}" '
           'fill-opacity="0.22"/>',
           f'<circle cx="50" cy="50" r="36" fill="{s["dark"]}" stroke="{s["light"]}" stroke-width="3"/>']
    em = emblem_points(s["kind"], s["n"])
    if em is None:
        out.append(f'<circle cx="50" cy="50" r="22" fill="{s["light"]}"/>')
    else:
        out.append(f'<polygon points="{_pts(em)}" fill="{s["light"]}" stroke="{s["dark"]}" stroke-width="1.5" '
                   'stroke-linejoin="round"/>')
    for x, y in pip_points(s["pips"], s["of"]):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{s["light"]}" stroke="{s["dark"]}" '
                   'stroke-width="1.5"/>')
    lines = name_lines(s["name"])
    size = name_size(lines)
    ys = [50] if len(lines) == 1 else [38, 60]
    ys = [y - (6 if s["pips"] else 0) for y in ys]
    for text, y in zip(lines, ys):
        out.append(f'<text x="141" y="{y}" text-anchor="middle" dominant-baseline="middle" font-family="Arial, '
                   f'Helvetica, sans-serif" font-weight="bold" font-size="{size}" fill="#ffffff" stroke="{s["dark"]}" '
                   f'stroke-width="3" paint-order="stroke">{text}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def file_name(tier):
    return "t4_rank_%02d.svg" % tier


def write_svgs(folder=OUT):
    os.makedirs(folder, exist_ok=True)
    for tier in range(len(NAMES)):
        with open(os.path.join(folder, file_name(tier)), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg(tier))
    return len(NAMES)


def check(folder=OUT):
    bad = []
    for tier in range(len(NAMES)):
        try:
            with open(os.path.join(folder, file_name(tier)), encoding="utf-8") as f:
                if f.read() != svg(tier):
                    bad.append(file_name(tier))
        except OSError:
            bad.append(file_name(tier))
    return bad


def sheet(path):
    cols = 6
    rows = (len(NAMES) + cols - 1) // cols
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cols * 220} {rows * 130}">',
             f'<rect width="{cols * 220}" height="{rows * 130}" fill="#1b1d22"/>']
    for tier in range(len(NAMES)):
        x, y = (tier % cols) * 220 + 10, (tier // cols) * 130 + 10
        inner = svg(tier).split("\n", 2)[2].rsplit("</svg>", 1)[0]
        parts.append(f'<g transform="translate({x},{y})">{inner}</g>')
        parts.append(f'<text x="{x + 100}" y="{y + 114}" text-anchor="middle" font-family="Arial" font-size="12" '
                     f'fill="#aab">{tier}</text>')
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def pngs(folder, height=100):
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    _app = QGuiApplication.instance() or QGuiApplication(["badges"])
    os.makedirs(folder, exist_ok=True)
    for tier in range(len(NAMES)):
        r = QSvgRenderer(QByteArray(svg(tier).encode("utf-8")))
        img = QImage(height * 2, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
        img.save(os.path.join(folder, "t4_rank_%02d.png" % tier))
    return len(NAMES)


# ---------------------------------------------------------------------------------------------- C++ header
def _rgb(h):
    return "0x%s" % h.lstrip("#").upper()


def header(path):
    rows = []
    for tier in range(len(NAMES)):
        s = spec(tier)
        rows.append('    {"%s", %s, %s, %s, %d, %d, %d, %d},' % (
            s["name"], _rgb(s["plate"]), _rgb(s["light"]), _rgb(s["dark"]), 1 if s["kind"] == "star" else 0, s["n"],
            s["pips"], s["of"]))
    text = f"""// GENERATED by OpenRecomp-FGC tools/make_rank_badges.py --header (do not edit by hand): Tekken 4 Online's rank
// badges -- our own drawing, Tekken 7's rank NAMES (tier = index, the T4 lobby's t4lobby/ranks.py). The game's name
// plates (tekken4_hud_overrides.cpp) draw the same elements as the launcher's SVG badges: a {W}x{H} plate, an emblem
// (polygon with `n` sides, 0 = circle, or an n-pointed star), `pips` dots of `of`, the rank's name.
#pragma once
#include <cstdint>

namespace tekken4_rank_badges
{{
    struct Badge
    {{
        const char *name;
        uint32_t plate, light, dark;   // 0xRRGGBB
        int star;                      // 1 = star with n points, 0 = polygon with n sides (0 = circle)
        int n;
        int pips, of;
    }};
    constexpr int kWidth = {W}, kHeight = {H};
    constexpr int kCount = {len(NAMES)};
    constexpr Badge kBadges[kCount] = {{
{chr(10).join(rows)}
    }};
}}
"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--png", metavar="DIR")
    ap.add_argument("--height", type=int, default=100)
    ap.add_argument("--header", metavar="FILE")
    ap.add_argument("--sheet", metavar="FILE")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        bad = check()
        print("badges up to date" if not bad else "out of date: " + ", ".join(bad))
        return 1 if bad else 0
    if a.png:
        print(pngs(a.png, a.height), "PNG badges in", a.png)
    if a.header:
        header(a.header)
        print("header", a.header)
    if a.sheet:
        sheet(a.sheet)
        print("sheet", a.sheet)
    if not (a.png or a.header or a.sheet):
        print(write_svgs(), "SVG badges in", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""Draws the X/Twitter banner (1500x500) and the profile picture (400x400). No game art in them.

    python tools\make_banner.py <folder>

X covers the banner's lower left with the profile picture and crops top and bottom on phones: everything that must
be read stays in the middle.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter, QPolygonF  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "openrecomp", "ui")
RED, BLUE, BONE, INK, TICK, MUTED = "#F0414E", "#5B93FF", "#F2EFE6", "#0E0F11", "#1A1C20", "#A3A5AB"
W, H = 1500, 500


def polygon(painter, points, color):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def bracket(x_edge, inner_dir):
    """A bracket reaching past the top and bottom of the picture would lose its arms: this one stays inside."""
    t, arm, top, bottom = 46, 150, 56, H - 56
    x0, x1, x2 = x_edge, x_edge + inner_dir * t, x_edge + inner_dir * arm
    return ((x0, top), (x2, top), (x2, top + t), (x1, top + t), (x1, bottom - t), (x2, bottom - t), (x2, bottom), (x0, bottom))


def font(family, pixels, weight):
    f = QFont(family)
    f.setPixelSize(pixels)
    f.setWeight(weight)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def banner(path):
    image = QImage(W, H, QImage.Format_RGB32)
    image.fill(QColor(INK))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    polygon(p, ((560, H + 40), (760, H + 40), (940, -40), (740, -40)), TICK)     # the hit, huge and quiet
    polygon(p, bracket(64, 1), RED)
    polygon(p, bracket(W - 64, -1), BLUE)

    name, tag = "OPENRECOMP", "-FGC"
    title = font("Big Shoulders", 146, QFont.Black)
    m = QFontMetricsF(title)
    width = m.horizontalAdvance(name) + m.horizontalAdvance(tag)
    x = (W - width) / 2
    base = H / 2 + 26
    p.setFont(title)
    p.setPen(QColor(BONE))
    p.drawText(QPointF(x, base), name)
    p.setPen(QColor(RED))
    p.drawText(QPointF(x + m.horizontalAdvance(name), base), tag)

    line = font("IBM Plex Mono", 30, QFont.Medium)
    p.setFont(line)
    p.setPen(QColor(BONE))
    text = "One launcher for fighting game recomps"
    p.drawText(QPointF((W - QFontMetricsF(line).horizontalAdvance(text)) / 2, base + 58), text)
    p.end()
    image.save(path)
    return width


def profile(path):
    image = QImage(400, 400, QImage.Format_RGB32)
    image.fill(QColor(INK))
    p = QPainter(image)
    QSvgRenderer(os.path.join(UI, "assets", "icon.svg")).render(p, QRectF(0, 0, 400, 400))
    p.end()
    image.save(path)


def main():
    folder = sys.argv[1]
    os.makedirs(folder, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    for name in os.listdir(os.path.join(UI, "fonts")):
        if name.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(UI, "fonts", name))
    width = banner(os.path.join(folder, "openrecomp_fgc_x_banner.png"))
    profile(os.path.join(folder, "openrecomp_fgc_x_profile.png"))
    print(f"title width {width:.0f} of {W}")
    del app


if __name__ == "__main__":
    main()

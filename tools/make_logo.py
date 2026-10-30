r"""Draws the logo files in openrecomp\ui\assets. The mark is plain polygons; the wordmark's letters become outlines, so
the SVGs need no font.

    python tools\make_logo.py [folder for PNG previews]

The mark reads [ / ]: brackets for code, red and blue for P1 and P2, the bone slash for the hit between them.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "openrecomp", "ui", "assets")
FONTS = os.path.join(ROOT, "openrecomp", "ui", "fonts")
RED, BLUE, BONE, INK = "#F0414E", "#5B93FF", "#F2EFE6", "#0E0F11"
SIZE = 512
LEFT = ((48, 72), (176, 72), (176, 136), (112, 136), (112, 376), (176, 376), (176, 440), (48, 440))
RIGHT = tuple((SIZE - x, y) for x, y in LEFT)
SLASH = ((176, 488), (252, 488), (336, 24), (260, 24))


def poly(points, fill):
    return f'<polygon fill="{fill}" points="' + " ".join(f"{x},{y}" for x, y in points) + '"/>'


def mark_shapes(slash=BONE):
    return poly(LEFT, RED) + poly(RIGHT, BLUE) + poly(SLASH, slash)


def svg(width, height, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}" height="{height:g}">{body}</svg>\n'


def text_path(text, pixel_size, spacing=0.0):
    """SVG path data of `text` in Big Shoulders Black, baseline at y=0. -> (data, advance width)."""
    font = QFont("Big Shoulders")
    font.setWeight(QFont.Black)
    font.setPixelSize(pixel_size)
    font.setHintingPreference(QFont.PreferNoHinting)
    font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    path = QPainterPath()
    path.addText(0, 0, font, text)
    parts = []
    i = 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.type == QPainterPath.MoveToElement:
            parts.append(f"M{e.x:.2f} {e.y:.2f}")
            i += 1
        elif e.type == QPainterPath.LineToElement:
            parts.append(f"L{e.x:.2f} {e.y:.2f}")
            i += 1
        else:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            parts.append(f"C{e.x:.2f} {e.y:.2f} {c2.x:.2f} {c2.y:.2f} {end.x:.2f} {end.y:.2f}")
            i += 3
    return "".join(parts) + "Z", path.boundingRect().right()


def wordmark(name_fill, slash):
    """Mark on the left, the name beside it."""
    height = 160
    scale = height / SIZE
    data1, width1 = text_path("OPENRECOMP", 132, 1.5)
    data2, width2 = text_path("-FGC", 132, 1.5)
    x = height + 28
    baseline = 128
    body = (f'<g transform="scale({scale:.5f})">{mark_shapes(slash)}</g>'
            f'<path fill="{name_fill}" transform="translate({x} {baseline})" d="{data1}"/>'
            f'<path fill="{RED}" transform="translate({x + width1 + 4:.2f} {baseline})" d="{data2}"/>')
    return svg(x + width1 + 4 + width2 + 8, height, body)


def app_icon():
    """The mark on the launcher's near-black ground, for small sizes."""
    inset = 36
    scale = (SIZE - 2 * inset) / SIZE
    return svg(SIZE, SIZE, f'<rect width="{SIZE}" height="{SIZE}" fill="{INK}"/><g transform="translate({inset} {inset}) scale({scale:.5f})">{mark_shapes()}</g>')


def render(svg_text, width, height, background=None):
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    image = QImage(QSize(width, height), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent if background is None else background)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def preview(path, files):
    """One sheet: the logo on dark and light, the icon at the sizes it will really be used at."""
    sheet = QImage(1600, 900, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(INK)
    painter = QPainter(sheet)
    painter.fillRect(0, 450, 1600, 450, BONE)
    dark, light, mark, icon = (files[n] for n in ("logo-wordmark.svg", "logo-wordmark-light.svg", "logo-mark.svg", "icon.svg"))
    for svg_text, y in ((dark, 60), (light, 510)):
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        size = renderer.defaultSize()
        width = 1100
        renderer.render(painter, QRectF(70, y, width, width * size.height() / size.width()))
    QSvgRenderer(QByteArray(mark.encode("utf-8"))).render(painter, QRectF(1240, 60, 300, 300))
    x = 70
    for s in (256, 128, 64, 48, 32, 24, 16):
        QSvgRenderer(QByteArray(icon.encode("utf-8"))).render(painter, QRectF(x, 260 + (128 - min(s, 128)) / 2 if s <= 128 else 200, min(s, 160), min(s, 160)))
        x += min(s, 160) + 40
    x = 70
    for s in (160, 96, 48, 32, 24):
        QSvgRenderer(QByteArray(mark.replace(BONE, INK).encode("utf-8"))).render(painter, QRectF(x, 700, s, s))
        x += s + 40
    painter.end()
    sheet.save(path)


def main():
    app = QGuiApplication(sys.argv[:1])
    for name in os.listdir(FONTS):
        if name.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(FONTS, name))
    os.makedirs(ASSETS, exist_ok=True)
    files = {
        "logo-mark.svg": svg(SIZE, SIZE, mark_shapes()),
        "logo-mark-light.svg": svg(SIZE, SIZE, mark_shapes(INK)),
        "logo-wordmark.svg": wordmark(BONE, BONE),
        "logo-wordmark-light.svg": wordmark(INK, INK),
        "icon.svg": app_icon(),
    }
    for name, text in files.items():
        with open(os.path.join(ASSETS, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    render(files["icon.svg"], 256, 256).save(os.path.join(ASSETS, "icon.ico"))
    if len(sys.argv) > 1:
        preview(sys.argv[1], files)
    print("written:", ", ".join(sorted(os.listdir(ASSETS))))
    del app


if __name__ == "__main__":
    main()

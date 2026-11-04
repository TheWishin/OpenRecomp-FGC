"""Large VS cut-outs from the installed game's decoder; no game art is shipped."""
import inspect
import os
import tempfile

from .t4_art import png_bytes

RENDER_SIZE = 768


def t4_cache_token(key, render=False, mirrored=False):
    return key + (("_render_p2" if mirrored else "_render_p1") if render else "")


def t5_cache_name(gid, mirrored=False):
    return f"render_{gid:02d}_{'p2' if mirrored else 'p1'}.png"


def mirror_rgba(rgba, width, height):
    return b"".join(b"".join(rgba[(y * width + x) * 4:(y * width + x + 1) * 4]
                            for x in range(width - 1, -1, -1)) for y in range(height))


def t5_cutout(decoder, sources, gid, mirrored=False):
    """Keep the select render's upper body and alpha, independently of the small face cache."""
    side = min(RENDER_SIZE, decoder.TEX_W)
    side -= side % 4
    if side < 512:
        raise ValueError("select render is too small")
    options = dict(rows=side)
    # Newer installed decoders can select the game's own opposite-side render.
    parameters = inspect.signature(decoder.render_dxt).parameters
    native_mirror = "mirrored" in parameters
    if native_mirror:
        options["mirrored"] = mirrored
    dxt = decoder.render_dxt(*sources, gid, **options)
    left = ((decoder.TEX_W - side) // 2) // 4 * 4
    rgba = decoder.dxt5_square(dxt, decoder.TEX_W, left, 0, side)
    if len(rgba) != side * side * 4:
        raise ValueError("select render ends early")
    if mirrored and not native_mirror:
        rgba = mirror_rgba(rgba, side, side)
    return side, side, rgba


def write_render(path, width, height, rgba):
    """Publish only a complete PNG, without writing beside the game data."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".render-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(png_bytes(width, height, rgba))
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return path

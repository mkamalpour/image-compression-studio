"""Bounded image I/O, reproducible examples, quality metrics and safe exports."""

from io import BytesIO
from pathlib import Path
import json
import math
import warnings

import numpy as np
from PIL import Image, ImageOps

MAX_PIXELS = 2_000_000
MAX_SOURCE_PIXELS = 50_000_000
MAX_FILE_BYTES = 64 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def fit_size(width, height, limit):
    scale = min(1.0, math.sqrt(limit / (width * height)))
    w, h = max(1, int(width*scale)), max(1, int(height*scale))
    if w*h > limit:
        if w >= h:
            w = max(1, limit//h)
        else:
            h = max(1, limit//w)
    return w, h


def rgb_array(value):
    array = np.asarray(value)
    if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("Expected an RGB image with 8-bit channels.")
    h, w = array.shape[:2]
    if h < 1 or w < 1 or h * w > MAX_PIXELS:
        raise ValueError(f"Use an image between 1 and {MAX_PIXELS:,} pixels. Resize a copy first.")
    return np.ascontiguousarray(array)


def read_image(path, background="white", max_pixels=MAX_PIXELS, resize=True):
    if type(max_pixels) is not int or not 1 <= max_pixels <= MAX_PIXELS:
        raise ValueError(f"Working pixel limit must be an integer from 1 to {MAX_PIXELS:,}.")
    if background not in {"white", "black", "ignore"}:
        raise ValueError("Choose white, black, or ignore for transparency.")
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Image file exceeds the 64 MiB input limit.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            original_size = source.size
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError(f"Image exceeds {MAX_SOURCE_PIXELS:,} source pixels. Resize a copy first.")
            if not resize and source.width * source.height > max_pixels:
                raise ValueError(f"Exact processing exceeds {max_pixels:,} pixels. Use Adaptive for high-resolution folders.")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Use a still image; animated or multi-page files are not supported.")
            ratio = min(1.0, math.sqrt(max_pixels / (source.width * source.height)))
            target = fit_size(source.width, source.height, max_pixels)
            # JPEG draft reduces decode work before constructing large pixel arrays.
            if ratio < 1:
                source.draft("RGB", target)
            oriented = ImageOps.exif_transpose(source)
            if oriented.width * oriented.height > max_pixels:
                oriented.thumbnail(fit_size(oriented.width, oriented.height, max_pixels), Image.Resampling.LANCZOS)
            if background == "ignore":
                image = oriented.convert("RGB")
            else:
                rgba = oriented.convert("RGBA")
                canvas = Image.new("RGBA", rgba.size, background)
                image = Image.alpha_composite(canvas, rgba).convert("RGB")
            # Returning only pixels intentionally drops EXIF/GPS and other source metadata.
            return {"rgb": rgb_array(np.array(image)), "original_size": list(original_size),
                    "resized": ratio < 1, "background": background}


def load_rgb(path, background="white", max_pixels=MAX_PIXELS, resize=True):
    return read_image(path, background, max_pixels, resize)["rgb"]


def metrics(original, reconstructed):
    a, b = rgb_array(original), rgb_array(reconstructed)
    if a.shape != b.shape:
        raise ValueError("Images must have matching dimensions for quality comparison.")
    error = a.astype(np.float64) - b
    mse = float(np.mean(error * error))
    # JSON-safe: null PSNR means identical pixels (positive infinity).
    return {"mse": mse, "psnr_db": None if mse == 0 else 10 * math.log10(255**2 / mse)}


def metric_text(values):
    psnr = values["psnr_db"]
    return f"MSE {values['mse']:.3f} | PSNR " + ("identical pixels" if psnr is None else f"{psnr:.2f} dB")


def pixel_fingerprint(image):
    """Identify exact RGB working pixels independent of source filename/codec."""
    import hashlib
    array = rgb_array(image)
    digest = hashlib.sha256()
    digest.update(f'RGB:{array.shape[1]}x{array.shape[0]}:uint8:'.encode('ascii'))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def png_bytes(array, palette=None):
    if palette is None:
        image = Image.fromarray(rgb_array(array))
    else:
        from .palettes import validate_palette
        palette = validate_palette(palette)
        indices = np.asarray(array)
        if indices.dtype != np.uint8 or indices.ndim != 2 or indices.size < 1 or indices.size > MAX_PIXELS:
            raise ValueError("Invalid index image.")
        if int(indices.max()) >= len(palette):
            raise ValueError("Index exceeds palette size.")
        image = Image.frombytes("P", (indices.shape[1], indices.shape[0]), indices.tobytes())
        image.putpalette(palette.reshape(-1).tolist() + [0] * (768 - palette.size))
    data = BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def write_new(path, data):
    """Never overwrite an input or previous export, including hard links."""
    path = Path(path)
    with path.open("xb") as file:
        try:
            file.write(data)
        except BaseException:
            file.close()
            path.unlink(missing_ok=True)
            raise
    return path


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def demo_image(kind="Color & detail", width=384, height=256):
    if kind not in {"Color & detail", "Gradients", "Geometric shapes"}:
        raise ValueError("Unknown example.")
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise ValueError("Invalid example size.")
    y, x = np.mgrid[:height, :width]
    r = x * 255 // max(1, width - 1)
    g = y * 255 // max(1, height - 1)
    b = (r + g) // 2
    out = np.stack([r, g, b], axis=-1).astype(np.uint8)
    if kind == "Color & detail":
        mask = ((x // 12 + y // 12) % 2 == 0) & (y > height // 2)
        out[mask] = (35, 55, 100)
        circle = (x - width * .72)**2 + (y - height * .3)**2 < (height * .2)**2
        out[circle] = (242, 116, 65)
    elif kind == "Geometric shapes":
        out[:] = (238, 243, 250)
        out[(x > width // 8) & (x < width // 2) & (y > height // 5) & (y < height * 4 // 5)] = (38, 94, 197)
        out[(x-width*.7)**2+(y-height*.5)**2 < (height*.3)**2] = (232, 108, 67)
    return out

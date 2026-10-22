"""Exact top-frequency RGB palettes and bounded nearest-color mapping."""

from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from .images import IMAGE_EXTENSIONS, load_rgb, rgb_array, metrics, png_bytes

MAX_DATASET_PIXELS = 60_000_000
MAX_DATASET_IMAGES = 200


def validate_palette(value):
    a = np.asarray(value)
    if a.ndim != 2 or a.shape[1] != 3 or not 1 <= len(a) <= 256:
        raise ValueError("A palette needs 1 to 256 RGB rows.")
    if not np.issubdtype(a.dtype, np.integer) or np.any(a < 0) or np.any(a > 255):
        raise ValueError("Palette channels must be integers from 0 to 255.")
    return a.astype(np.uint8)


def palette_size(k):
    if type(k) is not int or not 1 <= k <= 256:
        raise ValueError("Choose a palette size from 1 to 256.")
    return k


def histogram(rgb):
    a = rgb_array(rgb).reshape(-1, 3).astype(np.uint32)
    packed = (a[:, 0] << 16) | (a[:, 1] << 8) | a[:, 2]
    keys, counts = np.unique(packed, return_counts=True)
    return keys, counts


def top_palette(counts, k):
    palette_size(k)
    # Stable RGB tie-breaking makes palettes independent of input enumeration order.
    keys = np.flatnonzero(counts)
    if not len(keys):
        raise ValueError("No pixels available to build a palette.")
    n = min(k, len(keys))
    frequencies = counts[keys]
    cutoff = np.partition(frequencies, len(keys) - n)[len(keys) - n]
    above = keys[frequencies > cutoff]
    tied = keys[frequencies == cutoff][:n - len(above)]
    chosen = np.concatenate([above, tied])
    chosen = chosen[np.lexsort((chosen, -counts[chosen].astype(np.int64)))]
    return np.stack([(chosen >> 16) & 255, (chosen >> 8) & 255, chosen & 255], axis=1).astype(np.uint8)


def selected_palette(rgb, k=256, strategy="adaptive"):
    palette_size(k)
    rgb = rgb_array(rgb)
    if strategy == "adaptive":
        indexed = Image.fromarray(rgb).quantize(colors=k, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        used = sorted(index for _, index in indexed.getcolors())
        full = np.asarray(indexed.getpalette(), dtype=np.uint8).reshape(-1, 3)
        return full[used]
    if strategy != "frequency":
        raise ValueError("Unknown palette strategy.")
    keys, values = histogram(rgb)
    counts = np.zeros(1 << 24, dtype=np.uint32)
    counts[keys] = values
    return top_palette(counts, k)


def dataset_palette(folder, k=256, background="white", strategy="adaptive", progress=lambda value, text: None):
    palette_size(k)
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("Choose an existing image folder.")
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS), key=lambda p: p.name.casefold())
    if not files:
        raise ValueError("The folder has no supported image files.")
    if len(files) > MAX_DATASET_IMAGES:
        raise ValueError(f"Choose a dataset with at most {MAX_DATASET_IMAGES} images.")
    if strategy not in {"adaptive", "frequency"}:
        raise ValueError("Unknown palette strategy.")
    counts = np.zeros(1 << 24, dtype=np.uint32) if strategy == "frequency" else None
    samples = []
    total = 0
    # Fail clearly, rather than silently producing a palette from a partial dataset.
    for index, path in enumerate(files):
        try:
            rgb = load_rgb(path, background, max_pixels=65_536 if strategy == "adaptive" else 2_000_000,
                           resize=strategy == "adaptive")
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read dataset image {path.name}: {exc}") from exc
        total += rgb.shape[0] * rgb.shape[1]
        if total > MAX_DATASET_PIXELS:
            raise ValueError("Dataset exceeds the 60-million-pixel total limit.")
        if counts is not None:
            keys, values = histogram(rgb)
            counts[keys] += values.astype(np.uint32)
        else:
            flat = rgb.reshape(-1, 3)
            # Deterministic, bounded sampling gives every image a contribution.
            positions = np.linspace(0, len(flat)-1, min(4096, len(flat)), dtype=np.int64)
            samples.append(flat[positions])
        progress((index + 1) / len(files), f"Counted image {index + 1} of {len(files)}")
    palette = top_palette(counts, k) if counts is not None else selected_palette(np.concatenate(samples).reshape(1, -1, 3), k)
    return {"palette": palette, "images": len(files), "pixels": total, "strategy": strategy,
            "sample_pixels": total if counts is not None else sum(len(s) for s in samples)}


def map_colors(rgb, palette, mode="fast", progress=lambda value, text: None):
    rgb, palette = rgb_array(rgb), validate_palette(palette)
    if mode not in {"fast", "unique", "direct", "reference"}:
        raise ValueError("Unknown mapping method.")
    flat = rgb.reshape(-1, 3)
    if mode == "fast":
        fixed = Image.new("P", (1, 1))
        padded = np.concatenate([palette, np.repeat(palette[:1], 256-len(palette), axis=0)])
        fixed.putpalette(padded.reshape(-1).tolist())
        out = Image.fromarray(rgb).quantize(palette=fixed, dither=Image.Dither.NONE)
        indices = np.array(out)
        indices[indices >= len(palette)] = 0
        return indices
    if mode == "reference":
        if len(flat) > 65_536:
            raise ValueError("Reference loops are for images up to 65,536 pixels; choose a fast method.")
        pal = palette.tolist()
        indices = np.empty(len(flat), dtype=np.uint8)
        for i, color in enumerate(flat):
            px = [int(c) for c in color]
            indices[i] = min(range(len(pal)), key=lambda j: sum((px[c] - pal[j][c])**2 for c in range(3)))
            if i % 1024 == 0:
                progress(i / len(flat), "Mapping pixels with reference loops")
    else:
        if mode == "unique":
            values, inverse = np.unique(flat, axis=0, return_inverse=True)
        else:
            values, inverse = flat, None
        pal = palette.astype(np.int32)
        norms = np.sum(pal * pal, axis=1)
        nearest = np.empty(len(values), dtype=np.uint8)
        for start in range(0, len(values), 4096):
            block = values[start:start + 4096].astype(np.int32)
            # int32 avoids the int16 squared-distance overflow in naive implementations.
            distances = np.sum(block * block, axis=1)[:, None] + norms - 2 * (block @ pal.T)
            nearest[start:start + len(block)] = distances.argmin(axis=1)
            progress((start + len(block)) / len(values), "Mapping nearest palette colors")
        indices = nearest[inverse] if inverse is not None else nearest
    return indices.reshape(rgb.shape[:2])


def quantize(rgb, k=256, palette=None, mode="fast", strategy="adaptive", progress=lambda value, text: None):
    started = perf_counter()
    rgb = rgb_array(rgb)
    selected = palette is None
    palette = selected_palette(rgb, k, strategy) if selected else validate_palette(palette)
    progress(.1, "Palette ready; mapping image")
    indices = map_colors(rgb, palette, mode, lambda v, text: progress(.1 + .8*v, text))
    reconstructed = palette[indices]
    png = png_bytes(indices, palette)
    raw = int(rgb.size)
    return {"image": reconstructed, "palette": palette, "indices": indices, "png": png,
            "metrics": metrics(rgb, reconstructed), "settings": {"colors": len(palette), "mapping": mode, "strategy": strategy if selected else "shared"},
            "stats": {"raw_rgb_bytes": raw, "index_bytes": int(indices.size), "palette_rgb_bytes": int(palette.size),
                      "indexed_payload_bytes": int(indices.size + palette.size), "png_file_bytes": len(png),
                      "raw_to_png_ratio": raw / len(png), "elapsed_ms": (perf_counter()-started)*1000},
            "steps": [("Adaptive median-cut palette" if strategy == "adaptive" else "Exact RGB histogram; top-frequency palette") if selected else "Loaded shared dataset palette",
                      "Fast Pillow fixed-palette mapping (approximate RGB lookup)" if mode == "fast" else "Exact squared RGB distance; first palette row wins ties",
                      "8-bit index image reconstructed through its palette", "MSE and PSNR measured against original RGB pixels"]}


def palette_text(palette):
    return "".join(f"{i}\t{r}\t{g}\t{b}\n" for i, (r, g, b) in enumerate(validate_palette(palette)))


def read_palette(path):
    path = Path(path)
    if path.stat().st_size > 32_768:
        raise ValueError("Palette text file is too large.")
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            values = [int(v) for v in line.split()]
        except ValueError as exc:
            raise ValueError("Palette rows must contain integer RGB or index/RGB columns.") from exc
        if len(values) == 4:
            if values[0] != len(rows):
                raise ValueError("Palette indices must start at 0 and be consecutive.")
            values = values[1:]
        if len(values) != 3:
            raise ValueError("Use three RGB columns, optionally preceded by an index.")
        rows.append(values)
    return validate_palette(rows)

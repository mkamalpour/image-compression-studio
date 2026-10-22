"""Self-contained educational JPEG-style stream; deliberately not a JPEG file."""

import hashlib
import json
import struct
from time import perf_counter
from io import BytesIO

import numpy as np
from PIL import Image

from .images import MAX_PIXELS, MAX_FILE_BYTES, rgb_array, metrics, png_bytes
from .transforms import (ZIGZAG, rgb_to_ycbcr, ycbcr_to_rgb, blocks, merge,
                         dct, idct, subsample, quant_tables)
from .entropy import encode_channels, BitReader, decode_channel

MAGIC = b"MCS1"
MAX_HEADER = 32_768


def standard_jpeg(rgb, quality=80, sampling=True, progress=lambda value, text: None):
    """Practical interoperable JPEG using Pillow's native codec, measured after decode."""
    started = perf_counter()
    rgb = rgb_array(rgb)
    quant_tables(quality)
    if type(sampling) is not bool:
        raise ValueError("Chroma subsampling must be on or off.")
    data = BytesIO()
    progress(.1, "Encoding a standard JPEG file")
    Image.fromarray(rgb).save(data, format="JPEG", quality=quality, subsampling=2 if sampling else 0, optimize=True)
    encoded = data.getvalue()
    with Image.open(BytesIO(encoded)) as image:
        reconstructed = np.array(image.convert("RGB"))
    return {"image": reconstructed, "jpeg": encoded, "png": png_bytes(reconstructed),
            "metrics": metrics(rgb, reconstructed), "settings": {"quality": quality, "chroma": "4:2:0" if sampling else "4:4:4", "codec": "Standard JPEG (Pillow)"},
            "stats": {"raw_rgb_bytes": int(rgb.size), "jpeg_file_bytes": len(encoded), "raw_to_jpeg_ratio": rgb.size/len(encoded), "elapsed_ms": (perf_counter()-started)*1000},
            "steps": ["Pillow native JPEG encoder; optimized entropy tables",
                      "Encoded JPEG decoded again before preview and MSE/PSNR measurement",
                      "JPEG export saves these exact encoded bytes; PNG saves the decoded pixels without another lossy encode",
                      "Ratio compares raw RGB bytes with the complete JPEG file, not with the source image file"]}


def channel_shapes(h, w, sampling):
    return [(h, w)] + ([((h+1)//2, (w+1)//2)] * 2 if sampling else [(h, w)] * 2)


def unzigzag(vectors):
    out = np.empty_like(vectors)
    out[:, ZIGZAG] = vectors
    return out.reshape(-1, 8, 8)


def encode(rgb, quality=50, sampling=False, progress=lambda value, text: None):
    rgb = rgb_array(rgb)
    qy, qc = quant_tables(quality)
    if type(sampling) is not bool:
        raise ValueError("Chroma subsampling must be on or off.")
    ycc = rgb_to_ycbcr(rgb)
    vectors = []
    for i in range(3):
        channel = ycc[:, :, i]
        if i and sampling:
            channel = subsample(channel)
        # The assignment explicitly rounds transformed coefficients before quantization.
        coefficients = np.rint(dct(blocks(channel - 128)))
        quantized = np.rint(coefficients / (qy if i == 0 else qc)).astype(np.int32)
        vectors.append(quantized.reshape(-1, 64)[:, ZIGZAG])
        progress(.15 * (i+1), "Color conversion, 8x8 DCT and quantization")
    payload, bit_count, lengths = encode_channels(vectors, lambda v, t: progress(.45+.5*v, t))
    header = {"height": rgb.shape[0], "width": rgb.shape[1], "quality": quality,
              "sampling": sampling, "bit_count": bit_count, "huffman": lengths}
    raw_header = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = MAGIC + struct.pack(">I", len(raw_header)) + raw_header + payload
    stream = body + hashlib.sha256(body).digest()
    return stream, {"payload_bits": bit_count, "payload_bytes": len(payload),
                    "metadata_and_checksum_bytes": len(stream)-len(payload), "stream_file_bytes": len(stream),
                    "blocks": sum(len(v) for v in vectors), "huffman_symbols": len(lengths)}


def parse_stream(data):
    if not isinstance(data, bytes) or not 40 <= len(data) <= MAX_FILE_BYTES or data[:4] != MAGIC:
        raise ValueError("Not a supported MCS1 educational stream, or file exceeds 64 MiB.")
    if hashlib.sha256(data[:-32]).digest() != data[-32:]:
        raise ValueError("Stream integrity check failed. The file is truncated or changed.")
    size = struct.unpack(">I", data[4:8])[0]
    if not 1 <= size <= MAX_HEADER or 8 + size >= len(data)-32:
        raise ValueError("Invalid stream header size.")
    try:
        header = json.loads(data[8:8+size])
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid stream metadata.") from exc
    if not isinstance(header, dict) or set(header) != {"height", "width", "quality", "sampling", "bit_count", "huffman"}:
        raise ValueError("Unsupported stream metadata.")
    h, w = header["height"], header["width"]
    if type(h) is not int or type(w) is not int or h < 1 or w < 1 or h*w > MAX_PIXELS:
        raise ValueError("Stream dimensions exceed the image limit.")
    if type(header["sampling"]) is not bool:
        raise ValueError("Invalid sampling mode.")
    quant_tables(header["quality"])
    payload = data[8+size:-32]
    return header, payload


def decode(data, progress=lambda value, text: None):
    header, payload = parse_stream(data)
    h, w, sampling = header["height"], header["width"], header["sampling"]
    reader = BitReader(payload, header["bit_count"], header["huffman"])
    qy, qc = quant_tables(header["quality"])
    channels = []
    for i, shape in enumerate(channel_shapes(h, w, sampling)):
        n = ((shape[0]+7)//8) * ((shape[1]+7)//8)
        vectors = decode_channel(reader, n, lambda v, t: progress((i+v)/3, t))
        coefficients = unzigzag(vectors) * (qy if i == 0 else qc)
        channel = merge(idct(coefficients), shape) + 128
        if i and sampling:
            channel = np.repeat(np.repeat(channel, 2, axis=0), 2, axis=1)[:h, :w]
        channels.append(channel)
    if reader.position != reader.total:
        raise ValueError("Unexpected trailing coefficient data.")
    return ycbcr_to_rgb(np.stack(channels, axis=-1))


def compress(rgb, quality=50, sampling=False, progress=lambda value, text: None):
    started = perf_counter()
    stream, stats = encode(rgb, quality, sampling, lambda v, t: progress(v*.6, t))
    reconstructed = decode(stream, lambda v, t: progress(.6+v*.35, t))
    stats.update(raw_rgb_bytes=int(rgb.size), raw_to_stream_ratio=rgb.size/len(stream))
    result = {"image": reconstructed, "stream": stream, "png": png_bytes(reconstructed),
            "metrics": metrics(rgb, reconstructed), "stats": stats,
            "settings": {"quality": quality, "chroma": "4:2:0" if sampling else "4:4:4"},
            "steps": ["RGB to YCbCr; optional 2x2 chroma averaging (4:2:0)",
                      "Edge padding; level shift; orthonormal 8x8 DCT; coefficient rounding",
                      "Luminance/chrominance quantization; zigzag; DC differences; AC zero-run coding",
                      "Canonical Huffman bits packed into an MCS1 stream with metadata and checksum",
                      "Decode only from stream bytes; undo entropy coding, quantization and DCT",
                      "Crop padding; upsample chroma when needed; YCbCr to RGB; measure quality"]}
    stats["elapsed_ms"] = (perf_counter()-started)*1000
    return result


def coefficient_study(rgb, keep=(4, 7, 8, 16), progress=lambda value, text: None):
    rgb = rgb_array(rgb)
    if not isinstance(keep, (list, tuple)) or not 1 <= len(keep) <= 8 or any(type(k) is not int or not 1 <= k <= 64 for k in keep) or len(set(keep)) != len(keep):
        raise ValueError("Choose 1 to 8 distinct coefficient counts between 1 and 64.")
    started = perf_counter()
    ycc = rgb_to_ycbcr(rgb)
    transformed = [dct(blocks(ycc[:, :, i]-128)) for i in range(3)]
    results = []
    for index, k in enumerate(keep):
        channels = []
        for coefficients in transformed:
            vec = coefficients.reshape(-1, 64)[:, ZIGZAG].copy()
            vec[:, k:] = 0
            channels.append(merge(idct(unzigzag(vec)), rgb.shape[:2]) + 128)
        image = ycbcr_to_rgb(np.stack(channels, axis=-1))
        results.append({"image": image, "png": png_bytes(image), "metrics": metrics(rgb, image),
                        "settings": {"kept_coefficients": k, "quantization": False, "chroma": "4:4:4"},
                        "stats": {"coefficients_kept_percent": 100*k/64, "coefficient_count_ratio": 64/k,
                                  "timing_scope": "Cumulative study time, including shared DCT and earlier reconstructions",
                                  "elapsed_ms": (perf_counter()-started)*1000},
                        "steps": ["RGB to YCbCr; level shift; edge-padded 8x8 blocks",
                                  f"DCT computed once; first {k} zigzag coefficients retained per block",
                                  "No coefficient rounding, quantization or entropy coding in this experiment",
                                  "Inverse DCT; crop; RGB reconstruction; MSE/PSNR measured",
                                  "64/k is a coefficient-count ratio, not an encoded file compression ratio"]})
        progress((index+1)/len(keep), f"Reconstructed with {k} of 64 coefficients")
    return results

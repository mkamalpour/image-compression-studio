"""Manual color conversion, orthonormal 8x8 DCT, padding and sampling."""

import numpy as np

QY = np.array([
    [16,11,10,16,24,40,51,61], [12,12,14,19,26,58,60,55],
    [14,13,16,24,40,57,69,56], [14,17,22,29,51,87,80,62],
    [18,22,37,56,68,109,103,77], [24,35,55,64,81,104,113,92],
    [49,64,78,87,103,121,120,101], [72,92,95,98,112,100,103,99]], dtype=np.float64)
QC = np.array([
    [17,18,24,47,99,99,99,99], [18,21,26,66,99,99,99,99],
    [24,26,56,99,99,99,99,99], [47,66,99,99,99,99,99,99],
    [99]*8, [99]*8, [99]*8, [99]*8], dtype=np.float64)

ZIGZAG = np.array([r*8+c for diagonal in range(15)
                   for r, c in ([(r, diagonal-r) for r in range(8) if 0 <= diagonal-r < 8][::(-1 if diagonal % 2 == 0 else 1)])])
_positions = np.arange(8)
DCT = np.cos(np.pi * (2*_positions[None, :] + 1) * _positions[:, None] / 16) * .5
DCT[0] /= np.sqrt(2)


def rgb_to_ycbcr(rgb):
    a = rgb.astype(np.float64)
    return a @ np.array([[.299, -.168736, .5], [.587, -.331264, -.418688], [.114, .5, -.081312]]) + [0, 128, 128]


def ycbcr_to_rgb(a):
    a = a - [0, 128, 128]
    rgb = a @ np.array([[1,1,1], [0,-.344136,1.772], [1.402,-.714136,0]])
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def blocks(channel):
    h, w = channel.shape
    a = np.pad(channel, ((0, (-h) % 8), (0, (-w) % 8)), mode="edge")
    return a.reshape(a.shape[0]//8, 8, a.shape[1]//8, 8).transpose(0, 2, 1, 3).reshape(-1, 8, 8)


def merge(block_array, shape):
    h, w = shape
    rows, cols = (h+7)//8, (w+7)//8
    return block_array.reshape(rows, cols, 8, 8).transpose(0, 2, 1, 3).reshape(rows*8, cols*8)[:h, :w]


def dct(block_array):
    return DCT @ block_array @ DCT.T


def idct(coefficients):
    return DCT.T @ coefficients @ DCT


def subsample(channel):
    h, w = channel.shape
    a = np.pad(channel, ((0, h % 2), (0, w % 2)), mode="edge")
    return a.reshape(a.shape[0]//2, 2, a.shape[1]//2, 2).mean(axis=(1, 3))


def quant_tables(quality):
    if type(quality) is not int or not 1 <= quality <= 100:
        raise ValueError("JPEG-style quality must be an integer from 1 to 100.")
    scale = 5000 / quality if quality < 50 else 200 - quality * 2
    return tuple(np.clip(np.floor((q * scale + 50) / 100), 1, 255) for q in (QY, QC))


def block_details(rgb, block_x=0, block_y=0):
    y = rgb_to_ycbcr(rgb)[:, :, 0]
    rows, cols = (len(y)+7)//8, (y.shape[1]+7)//8
    if type(block_x) is not int or type(block_y) is not int or not 0 <= block_x < cols or not 0 <= block_y < rows:
        raise ValueError(f"Block coordinates must be x=0..{cols-1}, y=0..{rows-1}.")
    block = blocks(y - 128)[block_y * cols + block_x]
    return block, dct(block)

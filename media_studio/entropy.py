"""Deterministic canonical Huffman coding and JPEG-style DC/AC events."""

from collections import Counter
import heapq
from itertools import count

import numpy as np

EOB, ZRL = 16, 256


def category(value):
    return abs(int(value)).bit_length()


def amplitude(value, size):
    return int(value) if value >= 0 else (1 << size) - 1 + int(value)


def signed(value, size):
    return value if not size or value >= 1 << (size - 1) else value - (1 << size) + 1


def events(vectors):
    previous = 0
    for vector in vectors:
        dc = int(vector[0])
        diff = dc - previous
        previous = dc
        yield category(diff), diff, category(diff)
        run = 0
        for value in vector[1:]:
            value = int(value)
            if value == 0:
                run += 1
                continue
            while run >= 16:
                yield ZRL, 0, 0
                run -= 16
            size = category(value)
            yield 16 + run * 16 + size, value, size
            run = 0
        if run:
            yield EOB, 0, 0


def huffman_lengths(frequencies):
    if not frequencies:
        raise ValueError("Cannot encode an empty symbol stream.")
    serial = count()
    heap = [(int(n), next(serial), symbol) for symbol, n in sorted(frequencies.items())]
    heapq.heapify(heap)
    while len(heap) > 1:
        a, _, left = heapq.heappop(heap)
        b, _, right = heapq.heappop(heap)
        heapq.heappush(heap, (a + b, next(serial), (left, right)))
    lengths = []
    stack = [(heap[0][2], 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, int):
            lengths.append([node, max(1, depth)])
        else:
            stack.extend([(node[0], depth + 1), (node[1], depth + 1)])
    return sorted(lengths)


def canonical(lengths):
    if not isinstance(lengths, list) or not 1 <= len(lengths) <= 272:
        raise ValueError("Invalid Huffman table size.")
    seen = set()
    pairs = []
    for pair in lengths:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Invalid Huffman entry.")
        symbol, size = pair
        if type(symbol) is not int or type(size) is not int or not 0 <= symbol <= 271 or not 1 <= size <= 32 or symbol in seen:
            raise ValueError("Invalid Huffman symbol or length.")
        if 12 < symbol < 16 or (symbol >= 16 and symbol not in {EOB, ZRL} and not 1 <= (symbol-16) % 16 <= 12):
            raise ValueError("Unknown coefficient symbol.")
        seen.add(symbol)
        pairs.append((size, symbol))
    codes = {}
    code, previous = 0, 0
    for size, symbol in sorted(pairs):
        code <<= size - previous
        if code >= 1 << size:
            raise ValueError("Oversubscribed Huffman table.")
        codes[symbol] = (code, size)
        code += 1
        previous = size
    return codes


class BitWriter:
    def __init__(self):
        self.data = bytearray()
        self.buffer = self.pending = self.total = 0

    def write(self, value, size):
        if not 0 <= value < 1 << size:
            raise ValueError("Invalid amplitude.")
        self.buffer = (self.buffer << size) | value
        self.pending += size
        self.total += size
        while self.pending >= 8:
            self.pending -= 8
            self.data.append((self.buffer >> self.pending) & 255)
        self.buffer &= (1 << self.pending) - 1

    def finish(self):
        return bytes(self.data) + (bytes([self.buffer << (8 - self.pending)]) if self.pending else b"")


class BitReader:
    def __init__(self, data, bit_count, lengths):
        if type(bit_count) is not int or bit_count < 1 or (bit_count + 7)//8 != len(data):
            raise ValueError("Invalid bit count.")
        if bit_count % 8 and data[-1] & ((1 << (8 - bit_count % 8)) - 1):
            raise ValueError("Nonzero padding bits.")
        self.data, self.total, self.position = data, bit_count, 0
        codes = canonical(lengths)
        self.lookup = {(size, code): symbol for symbol, (code, size) in codes.items()}
        self.max_code = max(size for _, size in codes.values())

    def read(self, size):
        if self.position + size > self.total:
            raise ValueError("Truncated coefficient stream.")
        value = 0
        for _ in range(size):
            value = (value << 1) | ((self.data[self.position >> 3] >> (7 - self.position % 8)) & 1)
            self.position += 1
        return value

    def symbol(self):
        code = 0
        for size in range(1, self.max_code + 1):
            code = (code << 1) | self.read(1)
            found = self.lookup.get((size, code))
            if found is not None:
                return found
        raise ValueError("Invalid Huffman code.")


def encode_channels(channels, progress=lambda value, text: None):
    frequencies = Counter()
    for channel in channels:
        frequencies.update(symbol for symbol, _, _ in events(channel))
    lengths = huffman_lengths(frequencies)
    codes = canonical(lengths)
    writer = BitWriter()
    total = sum(len(channel) for channel in channels)
    done = 0
    for channel in channels:
        # DPCM state must span all blocks in a channel, not restart per batch.
        for index, (symbol, value, size) in enumerate(events(channel)):
            writer.write(*codes[symbol])
            if size:
                writer.write(amplitude(value, size), size)
            if index % 8192 == 0:
                progress(done / total, "Huffman encoding coefficients")
        done += len(channel)
    return writer.finish(), writer.total, lengths


def decode_channel(reader, blocks, progress=lambda value, text: None):
    vectors = np.zeros((blocks, 64), dtype=np.int32)
    previous = 0
    for row in range(blocks):
        symbol = reader.symbol()
        if not 0 <= symbol <= 12:
            raise ValueError("Expected a DC category.")
        previous += signed(reader.read(symbol), symbol)
        if abs(previous) > 4096:
            raise ValueError("DC coefficient exceeds supported range.")
        vectors[row, 0] = previous
        index = 1
        while index < 64:
            symbol = reader.symbol()
            if symbol == EOB:
                break
            if symbol == ZRL:
                index += 16
                if index > 64:
                    raise ValueError("Zero run exceeds block boundary.")
                continue
            if symbol < 16:
                raise ValueError("Expected an AC symbol.")
            run, size = divmod(symbol - 16, 16)
            index += run
            if index >= 64 or not 1 <= size <= 12:
                raise ValueError("Invalid AC coefficient run.")
            vectors[row, index] = signed(reader.read(size), size)
            index += 1
        if row % 256 == 0:
            progress(row / blocks, "Huffman decoding coefficients")
    return vectors

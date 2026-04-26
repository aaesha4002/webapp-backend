#!/usr/bin/env python3
import argparse
import struct
from hashlib import sha256
from pathlib import Path
from typing import Iterable, List

MAGIC = b"STEG1\x00"          # 6 bytes marker
HEADER_SIZE = len(MAGIC) + 8  # magic + uint64 payload length
BITS_IN_BYTE = 8

def _key_stream(key: bytes) -> Iterable[int]:
    counter = 0
    while True:
        block = sha256(key + counter.to_bytes(4, "big")).digest()
        for b in block:
            yield b
        counter += 1

def _xor_bytes(data: bytes, key: str) -> bytes:
    if not key:
        return data
    ks = _key_stream(key.encode())
    return bytes(b ^ next(ks) for b in data)

def _bytes_to_bits(data: bytes) -> List[int]:
    return [(byte >> i) & 1 for byte in data for i in range(7, -1, -1)]

def _bits_to_bytes(bits: List[int]) -> bytes:
    if len(bits) % 8:
        bits = bits + [0] * (8 - len(bits) % 8)
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i:i+8]:
            byte = (byte << 1) | bit
        out.append(byte)
    return bytes(out)

def _flatten_channels(img):
    pixels = list(img.getdata())
    flat = []
    for p in pixels:
        flat.extend(p[:3])  # drop alpha if present
    return flat

def _channels_to_image(channels: List[int], size):
    from PIL import Image
    pixels = [tuple(channels[i:i+3]) for i in range(0, len(channels), 3)]
    img = Image.new("RGB", size)
    img.putdata(pixels)
    return img

def _embed_bits(channels: List[int], bits: List[int]) -> List[int]:
    if len(bits) > len(channels):
        raise ValueError("Not enough capacity in cover image")
    out = channels[:]
    for idx, bit in enumerate(bits):
        out[idx] = (out[idx] & ~1) | bit
    return out

def _extract_bits(channels: List[int], bit_count: int) -> List[int]:
    return [channels[i] & 1 for i in range(bit_count)]

def hide(cover_path: Path, payload: bytes, alias: str, out_path: Path, key: str):
    from PIL import Image
    img = Image.open(cover_path).convert("RGB")
    flat = _flatten_channels(img)

    alias_bytes = alias.encode()
    if len(alias_bytes) > 65535:
        raise ValueError("Alias/filename too long (max 65535 bytes)")

    inner = struct.pack(">H", len(alias_bytes)) + alias_bytes + payload
    cipher = _xor_bytes(inner, key)
    blob = MAGIC + struct.pack(">Q", len(cipher)) + cipher

    bits = _bytes_to_bits(blob)
    embedded = _embed_bits(flat, bits)
    out_img = _channels_to_image(embedded, img.size)
    out_img.save(out_path, format="PNG")

def reveal(stego_path: Path, out_path: Path | None, key: str):
    from PIL import Image
    img = Image.open(stego_path).convert("RGB")
    flat = _flatten_channels(img)

    header_bits = _extract_bits(flat, HEADER_SIZE * BITS_IN_BYTE)
    header = _bits_to_bytes(header_bits)
    if not header.startswith(MAGIC):
        raise ValueError("No valid stego signature found")

    cipher_len = struct.unpack(">Q", header[len(MAGIC):len(MAGIC)+8])[0]
    total_bits = (HEADER_SIZE + cipher_len) * BITS_IN_BYTE
    bits = _extract_bits(flat, total_bits)
    data = _bits_to_bytes(bits)
    cipher = data[HEADER_SIZE:]
    inner = _xor_bytes(cipher, key)

    alias_len = struct.unpack(">H", inner[:2])[0]
    alias = inner[2:2+alias_len].decode(errors="replace")
    payload = inner[2+alias_len:]

    out_file = out_path or Path(alias or "recovered.bin")
    out_file.write_bytes(payload)
    return out_file, alias

def main():
    parser = argparse.ArgumentParser(description="LSB image steganography (hide/extract files).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    hide_p = sub.add_parser("hide", help="Embed a file/text into a PNG")
    hide_p.add_argument("--cover", required=True, type=Path, help="Cover image (PNG/BMP recommended)")
    hide_p.add_argument("--payload", type=Path, help="File to hide")
    hide_p.add_argument("--text", help="Inline text to hide (alternative to --payload)")
    hide_p.add_argument("--alias", help="Name to store for the hidden file")
    hide_p.add_argument("--out", required=True, type=Path, help="Output stego PNG")
    hide_p.add_argument("--key", default="", help="Optional passphrase for light XOR (leave empty for none)")

    rev_p = sub.add_parser("retrieve", help="Extract a hidden file from a stego PNG")
    rev_p.add_argument("--stego", required=True, type=Path, help="Stego image")
    rev_p.add_argument("--out", type=Path, help="Where to save recovered payload (defaults to stored alias)")
    rev_p.add_argument("--key", default="", help="Passphrase used during hide (leave empty if none)")

    args = parser.parse_args()
    if args.cmd == "hide":
        if (args.payload is None) == (args.text is None):
            raise SystemExit("Provide exactly one of --payload or --text")
        if args.text is not None:
            payload = args.text.encode("utf-8")
            alias = args.alias or "message.txt"
        else:
            payload = args.payload.read_bytes()
            alias = args.alias or args.payload.name
        hide(args.cover, payload, alias, args.out, args.key)
    elif args.cmd == "retrieve":
        out_file, alias = reveal(args.stego, args.out, args.key)
        print(f"Retrieved to {out_file} (alias stored: {alias})")

if __name__ == "__main__":
    main()

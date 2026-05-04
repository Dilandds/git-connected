#!/usr/bin/env python3
"""
One-time helper to encode the Lemon Squeezy API key into XORed/base64 chunks.

USAGE (run locally, NEVER commit the raw key):
    python scripts/encode_ls_key.py

It will prompt for the key, print three encoded chunks, and you paste them
into core/_keystore.py. Then DELETE this script's output from your terminal
history. The raw key is never written to disk.
"""
import base64
import getpass

# Must match the pads in core/_keystore.py
_A = b'k7Hq9mPx2nR4tY8w'
_B = b'L3vF6jB1cN5dG0aZ'
_C = b'eW8sQ4uI7oA2pM9x'


def _xor(data: bytes, pad: bytes) -> bytes:
    return bytes(b ^ pad[i % len(pad)] for i, b in enumerate(data))


def encode_chunk(chunk: bytes, pad: bytes) -> str:
    return base64.b64encode(_xor(chunk, pad)).decode('ascii')


def main():
    print("Paste your Lemon Squeezy API key (input hidden):")
    key = getpass.getpass("Key: ").strip()
    if not key:
        print("No key entered, aborting.")
        return

    data = key.encode('utf-8')
    n = len(data)
    # Split roughly into thirds
    s1 = n // 3
    s2 = 2 * n // 3
    p1, p2, p3 = data[:s1], data[s1:s2], data[s2:]

    e1 = encode_chunk(p1, _A)
    e2 = encode_chunk(p2, _B)
    e3 = encode_chunk(p3, _C)

    print("\n" + "=" * 60)
    print("Paste these three values into core/_keystore.py:")
    print("=" * 60)
    print(f'_P1 = "{e1}"')
    print(f'_P2 = "{e2}"')
    print(f'_P3 = "{e3}"')
    print("=" * 60)

    # Self-verify
    from importlib import util
    spec = util.spec_from_file_location("_ks_test", None)
    # Quick inline verify
    def _xor_back(s, pad):
        return _xor(base64.b64decode(s), pad)
    recovered = (_xor_back(e1, _A) + _xor_back(e2, _B) + _xor_back(e3, _C)).decode('utf-8')
    assert recovered == key, "Round-trip verification failed!"
    print("✓ Round-trip verified. Safe to paste.")


if __name__ == "__main__":
    main()

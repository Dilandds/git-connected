"""
Internal network configuration helpers.

Do not import from outside core.license_validator.
"""
import base64

# Obfuscation pads (must match scripts/encode_ls_key.py)
_A = b'k7Hq9mPx2nR4tY8w'
_B = b'L3vF6jB1cN5dG0aZ'
_C = b'eW8sQ4uI7oA2pM9x'

# Encoded chunks — replace these by running scripts/encode_ls_key.py locally
_P1 = "REPLACE_ME_CHUNK_1"
_P2 = "REPLACE_ME_CHUNK_2"
_P3 = "REPLACE_ME_CHUNK_3"

# Store ID — not secret, but kept here to centralize config
_STORE_ID = "REPLACE_ME_STORE_ID"


def _xor(data: bytes, pad: bytes) -> bytes:
    return bytes(b ^ pad[i % len(pad)] for i, b in enumerate(data))


def _t() -> str:
    """Reassemble the LS API token at runtime."""
    p1 = _xor(base64.b64decode(_P1), _A)
    p2 = _xor(base64.b64decode(_P2), _B)
    p3 = _xor(base64.b64decode(_P3), _C)
    return (p1 + p2 + p3).decode('utf-8')


def _s() -> str:
    """Return the store identifier."""
    return _STORE_ID

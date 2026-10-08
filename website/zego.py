"""Server-side helpers for issuing short-lived ZEGOCLOUD authentication tokens."""

import base64
import json
import secrets
import struct
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


TOKEN_LIFETIME_SECONDS = 60 * 60


def generate_token04(app_id, user_id, server_secret, room_id, lifetime=TOKEN_LIFETIME_SECONDS):
    """Generate a ZEGOCLOUD Token04 with permissions scoped to one room."""
    try:
        app_id = int(app_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("ZEGOCLOUD App ID must be an integer") from exc

    if not 0 < app_id <= 0xFFFFFFFF:
        raise ValueError("ZEGOCLOUD App ID is outside the supported range")
    if not user_id or not room_id:
        raise ValueError("ZEGOCLOUD user ID and room ID are required")
    if not isinstance(server_secret, str) or len(server_secret.encode("utf-8")) != 32:
        raise ValueError("ZEGOCLOUD Server Secret must be 32 bytes")
    if lifetime <= 0:
        raise ValueError("Token lifetime must be positive")

    created_at = int(time.time())
    expires_at = created_at + lifetime
    payload = json.dumps(
        {
            "room_id": str(room_id),
            "privilege": {"1": 1, "2": 1},
            "stream_id_list": [],
        },
        separators=(",", ":"),
    )
    token_data = json.dumps(
        {
            "app_id": app_id,
            "user_id": str(user_id),
            "ctime": created_at,
            "expire": expires_at,
            "nonce": secrets.randbelow(0x7FFFFFFF),
            "payload": payload,
        },
        separators=(",", ":"),
    ).encode("utf-8")

    iv = secrets.token_bytes(16)
    padder = PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(token_data) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(server_secret.encode("utf-8")), modes.CBC(iv)
    ).encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    packed_token = (
        struct.pack(">QH", expires_at, len(iv))
        + iv
        + struct.pack(">H", len(ciphertext))
        + ciphertext
    )
    return "04" + base64.b64encode(packed_token).decode("ascii")

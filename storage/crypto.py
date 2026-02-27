from __future__ import annotations

from cryptography.fernet import Fernet


class SecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"

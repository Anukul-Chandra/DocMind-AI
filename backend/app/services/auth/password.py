"""Password hashing and verification for DocMind AI."""

import hashlib
import hmac
import secrets

_PREFIX = "scrypt"
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DK_LEN = 32
_SALT_BYTES = 16
_MAX_N = 2 ** 20


class PasswordService:
    """Hash and verify passwords using the memory-hard scrypt KDF.

    Hashes are stored as a self-describing string (``scrypt$N$r$p$salt$hash``)
    so the parameters can evolve over time without breaking existing records.
    """

    def hash(self, password: str) -> str:
        """Hash a plaintext password.

        Args:
            password: The plaintext password to hash.

        Returns:
            A self-describing scrypt hash string.
        """
        salt = secrets.token_bytes(_SALT_BYTES)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_DK_LEN,
        )
        return "$".join(
            [
                _PREFIX,
                str(_SCRYPT_N),
                str(_SCRYPT_R),
                str(_SCRYPT_P),
                salt.hex(),
                derived.hex(),
            ]
        )

    def verify(self, password: str, hashed: str) -> bool:
        """Verify a plaintext password against a stored hash.

        Args:
            password: The plaintext password to check.
            hashed: The stored scrypt hash string.

        Returns:
            True if the password matches, otherwise False.
        """
        try:
            prefix, n_str, r_str, p_str, salt_hex, hash_hex = hashed.split("$")
            if prefix != _PREFIX:
                return False
            n = int(n_str)
            if n > _MAX_N:
                return False
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
        except (ValueError, TypeError):
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=int(r_str),
            p=int(p_str),
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)

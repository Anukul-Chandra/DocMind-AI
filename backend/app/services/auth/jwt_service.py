"""JSON Web Token creation and verification for DocMind AI."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any


class TokenError(Exception):
    """Base class for token processing failures."""


class TokenExpiredError(TokenError):
    """Raised when a token has exceeded its expiry time."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed, mis-signed, or of the wrong type."""


class JWTService:
    """Create and verify HMAC-signed JSON Web Tokens.

    The service is responsible only for token mechanics: issuing access and
    refresh tokens and verifying them. It knows nothing about users or
    credentials; callers supply the subject (typically a user id) and receive
    the subject back on successful verification.

    Configuration (secret, algorithm, and time-to-live values) is injected
    through the constructor so the service has no dependency on the global
    settings object.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_ttl_seconds: int = 900,
        refresh_ttl_seconds: int = 604800,
    ) -> None:
        """Initialize the token service with its configuration.

        Args:
            secret_key: The secret used to sign tokens.
            algorithm: The HMAC algorithm name, currently only ``HS256``.
            access_ttl_seconds: Lifetime of access tokens, in seconds.
            refresh_ttl_seconds: Lifetime of refresh tokens, in seconds.

        Raises:
            ValueError: If the secret key is empty.
        """
        if not secret_key:
            raise ValueError("secret_key must not be empty")
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    @property
    def access_ttl_seconds(self) -> int:
        """Return the access token lifetime in seconds.

        Returns:
            The configured access token time-to-live.
        """
        return self._access_ttl

    def create_access_token(
        self,
        subject: str,
        expires_in: int | None = None,
    ) -> str:
        """Create a signed access token for a subject.

        Args:
            subject: The token subject, typically a user id.
            expires_in: Optional custom lifetime in seconds; defaults to the
                configured access token TTL.

        Returns:
            A signed access token string.
        """
        return self._create_token(subject, "access", expires_in or self._access_ttl)

    def create_refresh_token(
        self,
        subject: str,
        expires_in: int | None = None,
    ) -> str:
        """Create a signed refresh token for a subject.

        Args:
            subject: The token subject, typically a user id.
            expires_in: Optional custom lifetime in seconds; defaults to the
                configured refresh token TTL.

        Returns:
            A signed refresh token string.
        """
        return self._create_token(subject, "refresh", expires_in or self._refresh_ttl)

    def verify_token(self, token: str, expected_type: str) -> str:
        """Verify a token's signature and return its subject.

        Args:
            token: The token to verify.
            expected_type: The token type required (``"access"`` or
                ``"refresh"``).

        Returns:
            The token subject.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed, mis-signed, or of
                the wrong type.
        """
        payload = self._decode(token)
        expires_at = payload.get("exp")
        if expires_at is not None and expires_at < int(time.time()):
            raise TokenExpiredError("Token has expired.")
        if payload.get("type") != expected_type:
            raise InvalidTokenError(f"Expected a {expected_type} token.")
        subject = payload.get("sub")
        if not subject:
            raise InvalidTokenError("Token is missing a subject.")
        return subject

    def _create_token(
        self,
        subject: str,
        token_type: str,
        ttl: int,
    ) -> str:
        """Build and sign a token with the standard claim set.

        Args:
            subject: The token subject.
            token_type: The token type claim (``"access"`` or ``"refresh"``).
            ttl: The token lifetime in seconds.

        Returns:
            A signed JWT string.
        """
        now = int(time.time())
        header: dict[str, Any] = {"alg": self._algorithm, "typ": "JWT"}
        payload: dict[str, Any] = {
            "sub": subject,
            "type": token_type,
            "iat": now,
            "exp": now + ttl,
            "jti": str(uuid.uuid4()),
        }
        signing_input = f"{self._b64url(json.dumps(header, sort_keys=True, separators=(',', ':')).encode('utf-8'))}.{self._b64url(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8'))}"
        signature = self._sign(signing_input)
        return f"{signing_input}.{self._b64url(signature)}"

    def _decode(self, token: str) -> dict[str, Any]:
        """Verify a token's signature and decode its payload.

        Args:
            token: The token to decode.

        Returns:
            The decoded token payload.

        Raises:
            InvalidTokenError: If the token is malformed or mis-signed.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Malformed token.")
        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        try:
            signature = self._unb64url(signature_b64)
            header = json.loads(self._unb64url(header_b64))
            payload = json.loads(self._unb64url(payload_b64))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidTokenError("Malformed token.") from exc
        if header.get("alg") != self._algorithm:
            raise InvalidTokenError("Unexpected token algorithm.")
        if not hmac.compare_digest(signature, self._sign(signing_input)):
            raise InvalidTokenError("Invalid token signature.")
        return payload

    def _sign(self, signing_input: str) -> bytes:
        """Compute the HMAC signature for a signing input.

        Args:
            signing_input: The unsigned token portion to sign.

        Returns:
            The raw signature bytes.
        """
        return hmac.new(
            self._secret_key.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _b64url(raw: bytes) -> str:
        """Encode bytes as unpadded base64url text.

        Args:
            raw: The bytes to encode.

        Returns:
            An unpadded base64url string.
        """
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64url(text: str) -> bytes:
        """Decode unpadded base64url text to bytes.

        Args:
            text: The base64url text to decode.

        Returns:
            The decoded bytes.
        """
        padding = "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(text + padding)

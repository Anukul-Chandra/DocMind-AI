"""User authentication and token issuance for DocMind AI."""

from dataclasses import dataclass
from typing import Protocol

from app.services.auth.jwt_service import (
    InvalidTokenError,
    JWTService,
    TokenExpiredError,
)
from app.services.auth.password import PasswordService


def normalize_email(email: str) -> str:
    """Return a canonical form of an email address.

    Email addresses are case-insensitive by convention, so leading/trailing
    whitespace is trimmed and the address is lowercased. This ensures
    ``User@example.com`` and ``user@example.com`` resolve to the same account.

    Args:
        email: The raw email address.

    Returns:
        The trimmed, lowercased email address.
    """
    return email.strip().lower()


@dataclass(frozen=True)
class User:
    """A registered user account in the authentication domain.

    Attributes:
        user_id: The unique identifier of the user.
        email: The user's email address, used for authentication.
        password_hash: The stored password hash for the user. Plaintext
            passwords are never stored.
        is_active: Whether the account is enabled. Disabled accounts are
            retained but must not be used for authentication.
    """

    user_id: str
    email: str
    password_hash: str
    is_active: bool = True


class UserRepository(Protocol):
    """Abstraction for creating and retrieving users.

    AuthService depends only on this protocol, so the backing store (a JSON
    repository today, a PostgreSQL repository later) can be swapped without
    changing AuthService.
    """

    def create(
        self,
        email: str,
        password_hash: str,
        user_id: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Create a new user and persist it.

        Args:
            email: The user's unique email address.
            password_hash: The pre-hashed password. Plaintext passwords must
                never be passed here.
            user_id: An explicit identifier, or None to generate one.
            is_active: Whether the new account should be active.

        Returns:
            The created user.

        Raises:
            ValueError: If the email is already in use.
        """

    def get_by_email(self, email: str) -> User | None:
        """Return the user with the given email, or None.

        Args:
            email: The email address to look up.
        """

    def get_by_id(self, user_id: str) -> User | None:
        """Return the user with the given id, or None.

        Args:
            user_id: The user identifier to look up.
        """


@dataclass(frozen=True)
class TokenPair:
    """A pair of issued tokens for an authenticated user.

    Attributes:
        access_token: The short-lived bearer token.
        refresh_token: The long-lived token used to obtain new pairs.
        token_type: The token type, always ``"bearer"``.
        expires_in: The access token lifetime in seconds.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


class AuthenticationError(Exception):
    """Base class for authentication failures."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when the supplied credentials do not match a known user."""


class EmailAlreadyRegisteredError(AuthenticationError):
    """Raised when a user tries to register an email that is already in use."""


class AuthService:
    """Authenticate users and issue access and refresh token pairs.

    This service composes a user repository, a password verifier, and a token
    service. It is responsible only for authentication flow and token
    generation; it knows nothing about concrete user stores or JWT internals.
    """

    def __init__(
        self,
        users: UserRepository,
        passwords: PasswordService,
        tokens: JWTService,
    ) -> None:
        """Initialize the authentication service with its collaborators.

        Args:
            users: The repository used to look up users.
            passwords: The service used to verify password hashes.
            tokens: The service used to create and verify tokens.
        """
        self._users = users
        self._passwords = passwords
        self._tokens = tokens

    def register(self, email: str, password: str) -> User:
        """Register a new active user with a hashed password.

        The email is normalized before it is compared or stored, the password
        is hashed with the password service, and the user is persisted through
        the repository. Only the hash is ever stored.

        Args:
            email: The user's email address.
            password: The plaintext password to hash. Never stored verbatim.

        Returns:
            The newly created user.

        Raises:
            EmailAlreadyRegisteredError: If the email is already registered.
        """
        normalized = normalize_email(email)
        if self._users.get_by_email(normalized) is not None:
            raise EmailAlreadyRegisteredError(
                f"Email already registered: {normalized}"
            )
        password_hash = self._passwords.hash(password)
        try:
            return self._users.create(
                email=normalized,
                password_hash=password_hash,
                is_active=True,
            )
        except ValueError as exc:
            raise EmailAlreadyRegisteredError(str(exc)) from exc

    def authenticate(self, email: str, password: str) -> TokenPair:
        """Authenticate a user by email and password.

        Args:
            email: The user's email address.
            password: The plaintext password to verify.

        Returns:
            A token pair for the authenticated user.

        Raises:
            InvalidCredentialsError: If the email is unknown or the password
                does not match.
        """
        user = self._users.get_by_email(normalize_email(email))
        if user is None or not self._passwords.verify(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")
        return self.create_tokens_for_user(user)

    def refresh(self, refresh_token: str) -> TokenPair:
        """Refresh an expired access token using a valid refresh token.

        Args:
            refresh_token: The refresh token to validate and redeem.

        Returns:
            A new token pair for the same user.

        Raises:
            InvalidCredentialsError: If the refresh token is invalid, expired,
                or its subject no longer exists.
        """
        try:
            user_id = self._tokens.verify_token(refresh_token, "refresh")
        except TokenExpiredError as exc:
            raise InvalidCredentialsError("Refresh token has expired.") from exc
        except InvalidTokenError as exc:
            raise InvalidCredentialsError("Invalid refresh token.") from exc
        user = self._users.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("The user for this token no longer exists.")
        return self.create_tokens_for_user(user)

    def create_tokens_for_user(self, user: User) -> TokenPair:
        """Issue a fresh access/refresh token pair for a user.

        Args:
            user: The authenticated user to issue tokens for.

        Returns:
            A token pair for the user.
        """
        access_token = self._tokens.create_access_token(user.user_id)
        refresh_token = self._tokens.create_refresh_token(user.user_id)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._tokens.access_ttl_seconds,
        )

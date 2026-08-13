"""User registration and login endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_auth_service
from app.models.responses import SuccessResponse
from app.services.auth import AuthService, EmailAlreadyRegisteredError, InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_valid_email(value: str) -> None:
    """Raise ValueError if value cannot plausibly be an email address.

    Args:
        value: The raw email value.

    Raises:
        ValueError: If the value is not a plausible email address.
    """
    if value.count("@") != 1:
        raise ValueError("Email must contain exactly one '@'.")
    local, domain = value.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise ValueError("Email must include a valid domain.")


class RegisterRequest(BaseModel):
    """Request payload for user registration.

    Attributes:
        email: The user's email address.
        password: The account password. It is hashed before storage and never
            returned.
    """

    email: str
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        """Reject values that cannot plausibly be an email address.

        Args:
            value: The raw email value.

        Returns:
            The email value if it looks valid.

        Raises:
            ValueError: If the value is not a plausible email address.
        """
        _require_valid_email(value)
        return value


class UserResponse(BaseModel):
    """Safe representation of a registered user.

    Deliberately exposes no password material.

    Attributes:
        user_id: The unique identifier of the user.
        email: The user's normalized email address.
        is_active: Whether the account is currently active.
    """

    user_id: str
    email: str
    is_active: bool


class LoginRequest(BaseModel):
    """Request payload for user login.

    Attributes:
        email: The user's email address.
        password: The account password.
    """

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        """Reject values that cannot plausibly be an email address.

        Args:
            value: The raw email value.

        Returns:
            The email value if it looks valid.

        Raises:
            ValueError: If the value is not a plausible email address.
        """
        _require_valid_email(value)
        return value


class TokenResponse(BaseModel):
    """Token pair issued after a successful login.

    Deliberately exposes no user data or password material.

    Attributes:
        access_token: The short-lived bearer token.
        refresh_token: The long-lived token used to obtain new pairs.
        token_type: The token type, always ``"bearer"``.
    """

    access_token: str
    refresh_token: str
    token_type: str


@router.post(
    "/register",
    response_model=SuccessResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[UserResponse]:
    """Register a new user account.

    The password is hashed by AuthService before it ever reaches the
    repository, and the response exposes only the safe user fields.

    Args:
        request: The registration payload.
        auth_service: The AuthService handling the registration logic.

    Returns:
        A success envelope with the registered user.

    Raises:
        HTTPException: If the email is already registered.
    """
    try:
        user = auth_service.register(request.email, request.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SuccessResponse(
        data=UserResponse(
            user_id=user.user_id,
            email=user.email,
            is_active=user.is_active,
        )
    )


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
)
def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessResponse[TokenResponse]:
    """Authenticate a user and issue an access/refresh token pair.

    All authentication logic lives in AuthService: the email is normalized,
    the user is looked up, the password is verified, and the account's active
    state is checked before tokens are issued. The route only delegates and
    maps authentication failures to the standardized 401 response.

    Args:
        request: The login payload.
        auth_service: The AuthService handling the authentication flow.

    Returns:
        A success envelope with the issued token pair.

    Raises:
        HTTPException: If the email is unknown, the password is incorrect, or
            the account is inactive. The same 401 is returned in every case.
    """
    try:
        pair = auth_service.authenticate(request.email, request.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return SuccessResponse(
        data=TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            token_type=pair.token_type,
        )
    )
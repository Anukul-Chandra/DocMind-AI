"""User registration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_auth_service
from app.models.responses import SuccessResponse
from app.services.auth import AuthService, EmailAlreadyRegisteredError

router = APIRouter(prefix="/auth", tags=["auth"])


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
        if value.count("@") != 1:
            raise ValueError("Email must contain exactly one '@'.")
        local, domain = value.rsplit("@", 1)
        if not local or not domain or "." not in domain:
            raise ValueError("Email must include a valid domain.")
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
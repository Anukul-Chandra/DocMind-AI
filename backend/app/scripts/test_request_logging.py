"""Request-logging middleware tests.

Verifies that the wired request-logging infrastructure records useful API
metadata without ever exposing sensitive data:

    A. Normal requests are logged with method, path, status, duration,
       timestamp, and a generated request id (also echoed in X-Request-ID).
    B. Authenticated requests associate safely with the resolved user id.
    C. Sensitive values (bodies, tokens, passwords) never reach the log.
    D. Failed requests preserve their status codes and are logged as failures.
    E. OPTIONS preflight requests are not logged.
    F. Request logging never changes existing responses or error handling.

Section A-D uses an isolated app writing to a temporary JSONL directory;
Section B additionally drives the real app to verify user association through
the actual auth dependency.

Usage (from backend/, JWT_SECRET required to import the app):
    python -m app.scripts.test_request_logging

Exit status is non-zero if any check fails.
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_auth_service,
    get_document_repository,
)
from app.api.errors import register_exception_handlers
from app.api.middleware.request_logging import RequestLogMiddleware
from app.core.config import settings
from app.main import app as real_app
from app.repositories.json.document_repository import JsonDocumentRepository
from app.repositories.json.log_repository import JsonLogRepository
from app.repositories.json.user_repository import JsonUserRepository
from app.services.auth import AuthService, JWTService, PasswordService
from app.services.document_registry import DocumentRegistry
from app.services.logging.request_logger import RequestLogger

PASSWORD = "super-secret-1"
TOKEN_SECRET = "logging-test-secret"
SECRET_BODY_VALUE = "SUPER-SENSITIVE-TOKEN-ABC"
SECRET_BOOM_DETAIL = "internal secret detail: SELECT * FROM secrets"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_entries(log_dir: Path) -> list[dict]:
    path = log_dir / f"{_today()}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def build_logged_app(log_dir: Path) -> FastAPI:
    """Build an isolated app whose requests are logged to a temp directory.

    Args:
        log_dir: Directory for the JSONL log files.

    Returns:
        A configured test app.
    """
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @test_app.get("/whoami")
    def whoami(request: Request) -> dict:
        request.state.user_id = "user-123"
        return {"ok": True}

    @test_app.post("/echo")
    def echo(payload: dict) -> dict:
        return payload

    @test_app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="Not here.")

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError(SECRET_BOOM_DETAIL)

    test_app.add_middleware(
        RequestLogMiddleware,
        log_repository=JsonLogRepository(RequestLogger(log_dir)),
    )
    return test_app


def _make_auth(tmp: Path) -> AuthService:
    return AuthService(
        users=JsonUserRepository(tmp / "users.json"),
        passwords=PasswordService(),
        tokens=JWTService(secret_key=TOKEN_SECRET),
    )


def _access_token(user) -> str:
    return JWTService(secret_key=TOKEN_SECRET).create_access_token(user.user_id)


def main() -> int:
    """Run all request-logging scenarios and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 60)
    print("Request Logging Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    # --- A. Isolated app: metadata logging -----------------------------
    print("\n[A. Isolated app metadata]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_dir = Path(tmp_dir) / "logs"
        app = build_logged_app(log_dir)

        with TestClient(app) as client:
            response = client.get("/ping")
            entry = _read_entries(log_dir)[-1]
            check(
                "A. normal request is logged",
                response.status_code == 200 and len(_read_entries(log_dir)) == 1,
                f"entries={len(_read_entries(log_dir))}",
            )
            check(
                "A. method and path captured",
                entry.get("method") == "GET" and entry.get("path") == "/ping",
                f"{entry}",
            )
            check(
                "A. status and success captured",
                entry.get("status_code") == 200 and entry.get("success") is True,
            )
            check(
                "A. timestamp and duration captured",
                bool(entry.get("timestamp"))
                and isinstance(entry.get("response_time_ms"), float)
                and entry.get("response_time_ms") > 0,
            )
            check(
                "A. request id captured and echoed in the response",
                bool(entry.get("request_id"))
                and response.headers.get("x-request-id") == entry.get("request_id"),
            )
            check(
                "A. unauthenticated entries omit the user id",
                "user_id" not in entry,
            )

            # B. User association via request state stamping.
            client.get("/whoami")
            entry = _read_entries(log_dir)[-1]
            check(
                "B. authenticated request records the user id",
                entry.get("user_id") == "user-123",
                f"{entry}",
            )

            # C. Sensitive request body values are never logged.
            client.post("/echo", json={"payload": SECRET_BODY_VALUE})
            entry = _read_entries(log_dir)[-1]
            check(
                "C. request body is not logged",
                SECRET_BODY_VALUE not in str(entry),
            )

            # D. 404 failures preserve their status and log as failures.
            client.get("/missing")
            entry = _read_entries(log_dir)[-1]
            check(
                "D. 404 logged with status and success=false",
                entry.get("status_code") == 404 and entry.get("success") is False,
                f"{entry}",
            )

            # D. Unhandled exceptions log a 500 without leaking detail.
            with TestClient(app, raise_server_exceptions=False) as client2:
                response2 = client2.get("/boom")
            entry = _read_entries(log_dir)[-1]
            check(
                "D. unhandled exception logs a safe 500",
                response2.status_code == 500
                and entry.get("status_code") == 500
                and entry.get("success") is False
                and SECRET_BOOM_DETAIL not in str(entry),
                f"status={response2.status_code}",
            )

            # E. OPTIONS preflight requests are not logged.
            before = len(_read_entries(log_dir))
            response = client.options("/ping")
            after = len(_read_entries(log_dir))
            check(
                "E. OPTIONS preflight is not logged",
                response.status_code == 405 and after == before,
                f"before={before} after={after}",
            )

    # --- B. Real app: user association through the auth dependency -----
    print("\n[B. Real app user association]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        auth = _make_auth(tmp)
        repo = JsonDocumentRepository(DocumentRegistry(tmp / "documents.json"))
        user = auth.register("log@example.com", PASSWORD)
        token = _access_token(user)
        wrong_password = "not-the-real-password-42"

        for dependency, value in {
            get_auth_service: auth,
            get_document_repository: repo,
        }.items():
            real_app.dependency_overrides[dependency] = partial(lambda v: v, value)
        try:
            with TestClient(real_app) as client:
                response = client.get(
                    "/documents",
                    headers={"Authorization": f"Bearer {token}"},
                )
                request_id = response.headers.get("x-request-id")
                login = client.post(
                    "/auth/login",
                    json={"email": "log@example.com", "password": wrong_password},
                )
                login_id = login.headers.get("x-request-id")
        finally:
            real_app.dependency_overrides.clear()

        check(
            "B. protected request returns the user id in its log entry",
            response.status_code == 200 and bool(request_id),
            f"status={response.status_code}",
        )
        entries = _read_entries(Path(settings.logs_dir))
        doc_entry = next((e for e in entries if e.get("request_id") == request_id), None)
        check(
            "B. documents entry associates the user id",
            doc_entry is not None
            and doc_entry.get("user_id") == user.user_id
            and doc_entry.get("method") == "GET"
            and doc_entry.get("path") == "/documents"
            and doc_entry.get("status_code") == 200,
            f"{doc_entry}",
        )
        check(
            "B. auth failure is logged without a user id",
            login.status_code == 401 and bool(login_id),
            f"status={login.status_code}",
        )
        login_entry = next(
            (e for e in entries if e.get("request_id") == login_id), None
        )
        check(
            "B. login failure entry has no user id",
            login_entry is not None
            and login_entry.get("status_code") == 401
            and "user_id" not in login_entry,
            f"{login_entry}",
        )

        all_lines = "\n".join(str(e) for e in entries)
        check(
            "C. tokens and passwords never reach the log",
            token not in all_lines and wrong_password not in all_lines,
        )

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Request Logging Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
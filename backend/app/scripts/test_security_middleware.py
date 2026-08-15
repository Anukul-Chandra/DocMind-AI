"""Security middleware integration tests (CORS + rate limiting).

Exercises, through the real FastAPI app and an isolated app:

    1. CORS preflight and simple-request behavior for allowed vs disallowed
       origins on the real app.
    2. Rate-limit enforcement with the standard error envelope on an isolated
       app with tight limits (path-specific buckets, per-key independence,
       window expiry, OPTIONS preflight passthrough).
    3. Configuration parsing of CORS_ORIGINS and the rate-limit defaults.
    4. FixedWindowLimiter unit behavior and argument validation.

The isolated app is used for rate limiting so the checks are deterministic and
do not depend on (or drain) the real app's production limits.

Usage (from backend/, JWT_SECRET required to import the app):
    python -m app.scripts.test_security_middleware

Exit status is non-zero if any check fails.
"""

import sys
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.api.middleware.rate_limit import (
    FixedWindowLimiter,
    RateLimitMiddleware,
    TOO_MANY_REQUESTS_MESSAGE,
)
from app.core.config import Settings
from app.main import app as real_app

ALLOWED_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "http://evil.example"


def build_rate_limited_app() -> FastAPI:
    """Build an isolated app with tight, deterministic rate limits.

    Returns:
        An app with /ping (general limit 3/min), /auth/ping (auth limit
        5/min) and an OPTIONS /ping route.
    """
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @test_app.post("/auth/ping")
    def auth_ping() -> dict:
        return {"ok": True}

    @test_app.options("/ping")
    def ping_options() -> dict:
        return {"ok": True}

    test_app.add_middleware(
        RateLimitMiddleware,
        general_limiter=FixedWindowLimiter(3),
        auth_limiter=FixedWindowLimiter(5),
        auth_paths=("/auth",),
    )
    return test_app


def main() -> int:
    """Run all security middleware scenarios and return the exit code.

    Returns:
        0 when all checks pass, otherwise 1.
    """
    print("=" * 60)
    print("Security Middleware Test (CORS + Rate Limit)")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    # --- 1. CORS behavior on the real app -------------------------------
    print("\n[CORS on the real app]")
    with TestClient(real_app) as client:
        # Allowed-origin preflight is accepted and advertises CORS.
        response = client.options(
            "/health",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        check(
            "1. allowed-origin preflight returns 200",
            response.status_code == 200,
            f"status={response.status_code}",
        )
        check(
            "1. preflight echoes the allowed origin",
            response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN,
        )
        allow_methods = response.headers.get("access-control-allow-methods", "")
        check(
            "1. preflight advertises the API methods",
            "GET" in allow_methods and "POST" in allow_methods
            and "DELETE" in allow_methods,
            allow_methods,
        )
        check(
            "1. preflight advertises credentials",
            response.headers.get("access-control-allow-credentials") == "true",
        )

        # Disallowed-origin preflight is rejected by the CORS middleware.
        response = client.options(
            "/health",
            headers={
                "Origin": DISALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        check(
            "1. disallowed-origin preflight is rejected",
            response.status_code == 400,
            f"status={response.status_code}",
        )

        # Simple request from an allowed origin gets CORS headers.
        response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
        check(
            "1. allowed-origin simple request gets CORS headers",
            response.status_code == 200
            and response.headers.get("access-control-allow-origin")
            == ALLOWED_ORIGIN,
        )

        # Simple request from a disallowed origin gets no CORS headers.
        response = client.get("/health", headers={"Origin": DISALLOWED_ORIGIN})
        check(
            "1. disallowed-origin simple request gets no CORS headers",
            response.status_code == 200
            and response.headers.get("access-control-allow-origin") is None,
            f"status={response.status_code}",
        )

        # Normal request without an Origin header is unaffected.
        response = client.get("/health")
        body = response.json()
        check(
            "1. normal request without Origin still works",
            response.status_code == 200
            and body.get("success") is True
            and body.get("data", {}).get("status") == "healthy",
        )

    # --- 2. Rate limiting on the isolated app ---------------------------
    print("\n[Rate limiting on the isolated app]")
    with TestClient(build_rate_limited_app()) as client:
        statuses = [client.get("/ping").status_code for _ in range(4)]
        check(
            "2. requests under the general limit succeed",
            statuses[:3] == [200, 200, 200],
            f"{statuses}",
        )
        check(
            "2. exceeding the general limit returns 429",
            statuses[3] == 429,
            f"status={statuses[3]}",
        )
        body = client.get("/ping").json()
        check(
            "2. 429 uses the standard error envelope",
            body.get("success") is False
            and body.get("error", {}).get("code") == "too_many_requests"
            and body.get("error", {}).get("message")
            == TOO_MANY_REQUESTS_MESSAGE,
        )

        # Auth bucket is independent: it still allows requests while the
        # general bucket is exhausted.
        auth_statuses = [client.post("/auth/ping").status_code for _ in range(6)]
        check(
            "2. auth bucket is independent of the general bucket",
            auth_statuses[:5] == [200, 200, 200, 200, 200],
            f"{auth_statuses}",
        )
        check(
            "2. exceeding the auth limit returns 429",
            auth_statuses[5] == 429,
            f"status={auth_statuses[5]}",
        )

        # OPTIONS preflight requests are never rate limited.
        preflight = [client.options("/ping").status_code for _ in range(10)]
        check(
            "2. OPTIONS preflight requests bypass the limiter",
            all(code == 200 for code in preflight),
        )

    # Window expiry: a short window allows a fresh request after it elapses.
    short_app = FastAPI()

    @short_app.get("/ping")
    def short_ping() -> dict:
        return {"ok": True}

    short_app.add_middleware(
        RateLimitMiddleware,
        general_limiter=FixedWindowLimiter(1, window_seconds=1),
    )
    with TestClient(short_app) as client:
        first = client.get("/ping").status_code
        second = client.get("/ping").status_code
        time.sleep(1.1)
        third = client.get("/ping").status_code
        check(
            "2. limit resets after the window elapses",
            first == 200 and second == 429 and third == 200,
            f"first={first} second={second} third={third}",
        )

    # --- 3. Configuration -------------------------------------------------
    print("\n[Configuration]")
    check(
        "3. CORS_ORIGINS parses into a trimmed list",
        Settings(cors_origins="http://a.com, http://b.com ,").cors_origin_list
        == ["http://a.com", "http://b.com"],
    )
    check(
        "3. blank CORS_ORIGINS yields an empty list",
        Settings(cors_origins=" , ").cors_origin_list == [],
    )
    defaults = Settings()
    check(
        "3. rate limiting enabled by default with sane limits",
        defaults.rate_limit_enabled is True
        and defaults.rate_limit_per_minute == 300
        and defaults.rate_limit_auth_per_minute == 60,
        f"general={defaults.rate_limit_per_minute} "
        f"auth={defaults.rate_limit_auth_per_minute}",
    )

    # --- 4. FixedWindowLimiter unit behavior -----------------------------
    print("\n[FixedWindowLimiter]")
    limiter = FixedWindowLimiter(2)
    check(
        "4. per-key counting within the limit",
        limiter.allow("a") is True
        and limiter.allow("a") is True
        and limiter.allow("a") is False,
    )
    check(
        "4. keys have independent buckets",
        limiter.allow("b") is True,
    )
    try:
        FixedWindowLimiter(0)
        invalid = True
    except ValueError:
        invalid = False
    check("4. invalid limit is rejected", invalid is False)
    try:
        FixedWindowLimiter(1, window_seconds=0)
        invalid_window = True
    except ValueError:
        invalid_window = False
    check("4. invalid window is rejected", invalid_window is False)

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print(f"Security Middleware Test {'PASSED' if all_passed else 'FAILED'}")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
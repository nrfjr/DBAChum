import pytest

from app.core.http_security import SecurityHeadersMiddleware


async def run_request(
    path: str,
    *,
    hsts_enabled: bool,
):
    captured = []

    async def inner_app(
        scope,
        receive,
        send,
    ):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"ok",
            }
        )

    middleware = SecurityHeadersMiddleware(
        inner_app,
        api_prefix="/api/v1",
        hsts_enabled=hsts_enabled,
    )

    async def receive():
        return {
            "type": "http.request",
            "body": b"",
            "more_body": False,
        }

    async def send(message):
        captured.append(message)

    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
        },
        receive,
        send,
    )

    response_start = captured[0]
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in response_start["headers"]
    }


@pytest.mark.asyncio
async def test_api_responses_get_security_and_no_store_headers():
    headers = await run_request(
        "/api/v1/databases",
        hsts_enabled=False,
    )

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store, max-age=0"
    assert headers["pragma"] == "no-cache"
    assert "frame-ancestors 'none'" in headers[
        "content-security-policy"
    ]
    assert "strict-transport-security" not in headers


@pytest.mark.asyncio
async def test_hsts_is_only_added_when_https_cookie_mode_is_enabled():
    headers = await run_request(
        "/",
        hsts_enabled=True,
    )

    assert headers["strict-transport-security"] == (
        "max-age=31536000"
    )
    assert "cache-control" not in headers

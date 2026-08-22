from starlette.datastructures import MutableHeaders


class SecurityHeadersMiddleware:
    """Apply conservative browser security headers to every response."""

    def __init__(
        self,
        app,
        *,
        api_prefix: str,
        hsts_enabled: bool = False,
    ):
        self.app = app
        self.api_prefix = api_prefix.rstrip("/")
        self.hsts_enabled = hsts_enabled

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        async def send_with_security_headers(
            message,
        ):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(
                    scope=message
                )

                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                headers["Content-Security-Policy"] = (
                    "frame-ancestors 'none'; "
                    "base-uri 'self'; "
                    "object-src 'none'"
                )

                path = scope.get("path", "")
                if (
                    path == self.api_prefix
                    or path.startswith(
                        f"{self.api_prefix}/"
                    )
                ):
                    headers["Cache-Control"] = (
                        "no-store, max-age=0"
                    )
                    headers["Pragma"] = "no-cache"

                if self.hsts_enabled:
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000"
                    )

            await send(message)

        await self.app(
            scope,
            receive,
            send_with_security_headers,
        )

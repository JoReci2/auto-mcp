"""Small asynchronous Prowlarr API v1 client with credential-safe errors."""

from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import SecretStr

from hmcp import SecretError

JsonObject = dict[str, Any]
Params = dict[str, str | int | bool | list[int]]


class ProwlarrError(ToolError):
    """An expected upstream failure safe to display through MCP."""


def validate_url(value: str) -> str:
    """Validate an instance base URL, including an optional reverse-proxy prefix.

    Args:
        value: Instance URL without credentials, query or API suffix.

    Returns:
        Normalized URL with no trailing slash.

    Raises:
        SecretError: The instance URL is unsuitable for authenticated requests.
    """
    value = value.strip()
    try:
        url = httpx.URL(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.username
            or url.password
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(ord(character) < 33 for character in value)
            or url.path.rstrip("/").lower().endswith("/api/v1")
        ):
            raise ValueError
    except (httpx.InvalidURL, ValueError):
        raise SecretError(
            "Prowlarr url must be an HTTP(S) instance URL without credentials, "
            "query, fragment or /api/v1 suffix"
        ) from None
    return str(url).rstrip("/")


class ProwlarrClient:
    """Issue requests to one configured instance without logging credentials."""

    def __init__(
        self, url: str, api_key: SecretStr, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """Configure the client without contacting the instance.

        Args:
            url: Validated instance base URL.
            api_key: API key sent only in X-Api-Key.
            transport: Optional transport for deterministic network tests.
        """
        self._base_url = validate_url(url) + "/api/v1/"
        self._key = api_key
        self._transport = transport
        value = api_key.get_secret_value()
        if not value or any(not 33 <= ord(character) <= 126 for character in value):
            raise SecretError("Prowlarr api-key must contain nonempty visible ASCII characters")

    async def _request(self, path: str, *, params: Params | None = None) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0 if path == "search" else 15.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    self._base_url + path,
                    params=params,
                    headers={
                        "X-Api-Key": self._key.get_secret_value(),
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException:
            raise ProwlarrError(
                "Prowlarr request timed out; narrow the search or check its indexers"
            ) from None
        except httpx.HTTPError:
            raise ProwlarrError(
                "Cannot reach Prowlarr; check the instance URL, network and TLS certificate"
            ) from None
        if response.is_redirect:
            raise ProwlarrError("Prowlarr returned a redirect; configure the final instance URL")
        if not response.is_success:
            messages = {
                401: "Prowlarr authentication failed; configure its api-key",
                403: "Prowlarr denied access; check its api-key and proxy permissions",
                404: "Prowlarr resource not found; check the identifier and instance URL",
                400: "Prowlarr rejected the request; check its parameters",
                422: "Prowlarr rejected the request; check its parameters",
                429: "Prowlarr rate limit reached; retry later",
            }
            raise ProwlarrError(
                messages.get(response.status_code, f"Prowlarr returned HTTP {response.status_code}")
            )
        try:
            return response.json()
        except ValueError:
            raise ProwlarrError(
                "Prowlarr returned invalid JSON; check the URL and reverse proxy"
            ) from None

    async def object(self, path: str, *, params: Params | None = None) -> JsonObject:
        """Read a single resource using GET.

        Args:
            path: Fixed API-relative route constructed internally by the plugin.
            params: Query parameters without credentials.

        Returns:
            A JSON resource for internal processing.

        Raises:
            ProwlarrError: The API response is not an object or the request fails.
        """
        value = await self._request(path, params=params)
        if not isinstance(value, dict):
            raise ProwlarrError("Prowlarr returned an unexpected resource format")
        return value

    async def array(self, path: str, *, params: Params | None = None) -> list[JsonObject]:
        """Read a list of API resources.

        Args:
            path: Fixed API-relative route, constructed internally by the plugin.
            params: Query parameters without credentials.

        Returns:
            JSON resources for internal processing.

        Raises:
            ProwlarrError: The API response is not an array of objects.
        """
        value = await self._request(path, params=params)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ProwlarrError("Prowlarr returned an unexpected list format")
        return value

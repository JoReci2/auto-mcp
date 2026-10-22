"""Small asynchronous Sonarr API v3 client with credential-safe errors."""

from typing import Any, Literal

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import SecretStr

from yamcps import SecretError

JsonObject = dict[str, Any]
Params = dict[str, str | int | bool]


class SonarrError(ToolError):
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
            or url.path.rstrip("/").lower().endswith("/api/v3")
        ):
            raise ValueError
    except (httpx.InvalidURL, ValueError):
        raise SecretError(
            "Sonarr url must be an HTTP(S) instance URL without credentials, "
            "query, fragment or /api/v3 suffix"
        ) from None
    return str(url).rstrip("/")


class SonarrClient:
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
        self._base_url = validate_url(url) + "/api/v3/"
        self._key = api_key
        self._transport = transport
        value = api_key.get_secret_value()
        if not value or any(not 33 <= ord(character) <= 126 for character in value):
            raise SecretError("Sonarr api-key must contain nonempty visible ASCII characters")

    async def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: Params | None = None,
        payload: JsonObject | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    self._base_url + path,
                    params=params,
                    json=payload,
                    headers={
                        "X-Api-Key": self._key.get_secret_value(),
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException:
            raise SonarrError(
                "Sonarr request timed out; check its state before retrying a write"
            ) from None
        except httpx.HTTPError:
            raise SonarrError(
                "Cannot reach Sonarr; check the instance URL, network and TLS certificate"
            ) from None
        if response.is_redirect:
            raise SonarrError("Sonarr returned a redirect; configure the final instance URL")
        if not response.is_success:
            messages = {
                401: "Sonarr authentication failed; configure its api-key",
                403: "Sonarr denied access; check its api-key and proxy permissions",
                404: "Sonarr resource not found; check the identifier and instance URL",
                400: "Sonarr rejected the request; check its parameters",
                409: "Sonarr reported a conflict; check whether the series already exists",
                422: "Sonarr rejected the request; check its parameters",
                429: "Sonarr rate limit reached; retry later",
            }
            raise SonarrError(
                messages.get(response.status_code, f"Sonarr returned HTTP {response.status_code}")
            )
        try:
            return response.json()
        except ValueError:
            raise SonarrError(
                "Sonarr returned invalid JSON; check the URL and reverse proxy"
            ) from None

    async def object(
        self, path: str, *, params: Params | None = None, payload: JsonObject | None = None
    ) -> JsonObject:
        """Read one resource or submit a mutation returning one resource.

        Args:
            path: Fixed API-relative route, constructed internally by the plugin.
            params: Query parameters without credentials.
            payload: POST body; None selects GET.

        Returns:
            A JSON resource for internal processing.

        Raises:
            SonarrError: The API response is not an object or the request fails.
        """
        value = await self._request(
            "POST" if payload is not None else "GET", path, params=params, payload=payload
        )
        if not isinstance(value, dict):
            raise SonarrError("Sonarr returned an unexpected resource format")
        return value

    async def array(self, path: str, *, params: Params | None = None) -> list[JsonObject]:
        """Read a list of API resources.

        Args:
            path: Fixed API-relative route, constructed internally by the plugin.
            params: Query parameters without credentials.

        Returns:
            JSON resources for internal processing.

        Raises:
            SonarrError: The API response is not an array of objects.
        """
        value = await self._request("GET", path, params=params)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise SonarrError("Sonarr returned an unexpected list format")
        return value

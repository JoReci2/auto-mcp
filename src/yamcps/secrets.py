"""Connector-scoped credentials for outbound API authentication."""

import base64
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr


class SecretError(ValueError):
    """A required secret is missing or invalid; messages never include values."""


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value):
        raise SecretError("Expected a lowercase kebab-case identifier")
    return value.upper().replace("-", "_")


@dataclass(frozen=True)
class TokenAuth:
    """An API token with a configurable Authorization scheme."""

    token: SecretStr
    scheme: str = "Bearer"

    def authorization_header(self) -> SecretStr:
        """Build a masked Authorization header.

        Returns:
            A secret header; explicitly call get_secret_value() to send it.

        Raises:
            SecretError: The token or authentication scheme is invalid.
        """
        token = self.token.get_secret_value()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", self.scheme):
            raise SecretError("Invalid token authentication scheme")
        if not token or any(not 33 <= ord(character) <= 126 for character in token):
            raise SecretError("Invalid API token")
        return SecretStr(f"{self.scheme} {token}")


@dataclass(frozen=True)
class BasicAuth:
    """Username and password for HTTP Basic authentication."""

    username: SecretStr
    password: SecretStr

    def authorization_header(self) -> SecretStr:
        """Build a masked, UTF-8 Basic Authorization header.

        Returns:
            A secret header; explicitly call get_secret_value() to send it.

        Raises:
            SecretError: The username is empty or contains a colon.
        """
        username = self.username.get_secret_value()
        if not username or ":" in username:
            raise SecretError("Invalid Basic authentication username")
        credentials = f"{username}:{self.password.get_secret_value()}".encode("utf-8")
        encoded = base64.b64encode(credentials).decode("ascii")
        return SecretStr(f"Basic {encoded}")


class ConnectorSecrets:
    """Read only the credentials named for one connector."""

    def __init__(self, connector_id: str, values: Mapping[str, str] | None = None) -> None:
        """Create a connector-scoped view over a credential source.

        Args:
            connector_id: Plugin identifier used to derive the environment prefix.
            values: Credential source; defaults to the process environment.
        """
        self._prefix = f"YAMCPS_{_identifier(connector_id)}_"
        self._values = os.environ if values is None else values

    def redact(self, message: str) -> str:
        """Mask this connector's raw secrets in a diagnostic.

        Args:
            message: Diagnostic text supplied by a connector.

        Returns:
            Text with known nonempty credential values replaced.
        """
        values = sorted(
            {
                value
                for name, value in self._values.items()
                if name.startswith(self._prefix) and value
            },
            key=len,
            reverse=True,
        )
        for value in values:
            message = message.replace(value, "[REDACTED]")
        return message

    def get(self, name: str) -> SecretStr | None:
        """Read an optional secret without exposing its raw value.

        Args:
            name: Lowercase kebab-case secret name, such as api-token.

        Returns:
            A masked secret, or None when the variable is unset or empty.
        """
        value = self._values.get(self._prefix + _identifier(name))
        return SecretStr(value) if value else None

    def require(self, name: str) -> SecretStr:
        """Read a required secret.

        Args:
            name: Lowercase kebab-case secret name.

        Returns:
            A masked secret.

        Raises:
            SecretError: The secret is missing or empty.
        """
        value = self.get(name)
        if value is None:
            raise SecretError(f"Missing secret: {self._prefix}{_identifier(name)}")
        return value

    def token_auth(self, name: str = "token", *, scheme: str = "Bearer") -> TokenAuth:
        """Read and validate a token for an outbound API.

        Args:
            name: Secret name holding the token.
            scheme: API authentication scheme, usually Bearer or Token.

        Returns:
            Masked token credentials.
        """
        auth = TokenAuth(self.require(name), scheme)
        auth.authorization_header()
        return auth

    def basic_auth(self) -> BasicAuth:
        """Read and validate username/password secrets.

        Returns:
            Masked HTTP Basic credentials.
        """
        auth = BasicAuth(self.require("username"), self.require("password"))
        auth.authorization_header()
        return auth


@dataclass(frozen=True)
class SecretSpec:
    """Describe one required credential without including any value."""

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        _identifier(self.name)

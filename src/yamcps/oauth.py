"""OAuth resource-server configuration and offline JWT access-token validation."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl, TypeAdapter, UrlConstraints


class OAuthError(ValueError):
    """Indicate invalid OAuth deployment settings without exposing file contents."""


def _https_url(value: object, *, resource: bool = False) -> str:
    if not isinstance(value, str):
        raise OAuthError("OAuth URLs must be HTTPS URLs")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (resource and parsed.path != "/mcp")
    ):
        raise OAuthError("OAuth requires HTTPS URLs; resource_url must end in /mcp")
    try:
        parsed.port
    except ValueError:
        raise OAuthError("Invalid OAuth URL port") from None
    return value


@dataclass(frozen=True)
class OAuthConfig:
    """Hold public deployment settings and a trusted RSA verification key."""

    issuer_url: str
    resource_url: str
    public_key: RSAPublicKey
    required_scopes: tuple[str, ...]

    @classmethod
    def from_file(cls, path: Path) -> "OAuthConfig":
        """Load strict JSON configuration and its PEM public key.

        Args:
            path: JSON file; relative key paths resolve beside this file.

        Returns:
            Validated OAuth resource-server configuration.

        Raises:
            OAuthError: Settings or the public key cannot be loaded.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {
                "issuer_url",
                "resource_url",
                "public_key_file",
                "required_scopes",
            }:
                raise OAuthError(
                    "OAuth config requires issuer_url, resource_url, "
                    "public_key_file and required_scopes only"
                )
            issuer = _https_url(data["issuer_url"])
            resource = _https_url(data["resource_url"], resource=True)
            scopes = data["required_scopes"]
            if (
                not isinstance(scopes, list)
                or not scopes
                or any(
                    not isinstance(scope, str) or not scope or any(c.isspace() for c in scope)
                    for scope in scopes
                )
            ):
                raise OAuthError("required_scopes must be a nonempty list of scope names")
            if not isinstance(data["public_key_file"], str) or not data["public_key_file"]:
                raise OAuthError("public_key_file must name a PEM public key")
            key_path = path.parent / data["public_key_file"]
            key = load_pem_public_key(key_path.read_bytes())
            if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
                raise OAuthError("OAuth requires an RSA public key of at least 2048 bits")
            return cls(issuer, resource, key, tuple(scopes))
        except OAuthError:
            raise
        except (OSError, ValueError, TypeError):
            raise OAuthError("Cannot load OAuth configuration or RSA public key") from None

    def auth_settings(self) -> AuthSettings:
        """Return SDK discovery settings with mandatory resource binding."""
        return AuthSettings(
            issuer_url=TypeAdapter(
                Annotated[AnyHttpUrl, UrlConstraints(preserve_empty_path=True)]
            ).validate_python(self.issuer_url),
            resource_server_url=AnyHttpUrl(self.resource_url),
            required_scopes=list(self.required_scopes),
            validate_token_resource=True,
        )

    def transport_security(self) -> TransportSecuritySettings:
        """Allow the public origin while retaining DNS rebinding protection."""
        parsed = urlsplit(self.resource_url)
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[parsed.netloc],
            allowed_origins=[f"https://{parsed.netloc}"],
        )


class JWTTokenVerifier:
    """Validate RS256 access tokens locally against the configured issuer and resource."""

    def __init__(self, config: OAuthConfig) -> None:
        """Retain trusted configuration; never fetch keys from a token header."""
        self.config = config

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate signature, lifetime, issuer, audience, principal and scopes.

        Args:
            token: Untrusted bearer access token.

        Returns:
            Validated principal or None when any access-token requirement fails.
        """
        try:
            claims = jwt.decode(
                token,
                self.config.public_key,
                algorithms=["RS256"],
                issuer=self.config.issuer_url,
                audience=self.config.resource_url,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "client_id"]},
            )
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                return None
            scopes = scope.split()
            if not set(self.config.required_scopes).issubset(scopes):
                return None
            if any(
                not isinstance(claims[name], str) or not claims[name]
                for name in ("sub", "client_id")
            ):
                return None
            return AccessToken(
                token=token,
                client_id=claims["client_id"],
                subject=claims["sub"],
                scopes=scopes,
                expires_at=int(claims["exp"]),
                resource=self.config.resource_url,
                claims={"iss": self.config.issuer_url},
            )
        except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
            return None

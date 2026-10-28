"""Exercise OAuth configuration, JWT rejection and HTTP discovery/authentication."""

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from yamcps.cli import main
from yamcps.oauth import JWTTokenVerifier, OAuthConfig, OAuthError
from yamcps.server import create_server


class OAuthTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.config = OAuthConfig(
            "https://auth.example.com",
            "https://mcp.example.com/mcp",
            cls.key.public_key(),
            ("mcp:access",),
        )

    def token(self, **changes):
        claims = dict(
            iss=self.config.issuer_url,
            aud=self.config.resource_url,
            sub="alice",
            client_id="client",
            iat=int(time.time()),
            exp=int(time.time()) + 300,
            scope="mcp:access",
        )
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256")

    async def test_valid_token(self):
        result = await JWTTokenVerifier(self.config).verify_token(self.token())
        self.assertEqual(result.subject, "alice")
        self.assertEqual(result.resource, self.config.resource_url)

    async def test_invalid_tokens(self):
        verifier = JWTTokenVerifier(self.config)
        for changes in [
            dict(exp=1),
            dict(iss="https://other.example.com"),
            dict(aud="https://other.example.com/mcp"),
            dict(scope="other"),
            dict(scope=["mcp:access"]),
            dict(sub=""),
            dict(client_id=42),
            dict(iat=int(time.time()) + 3600),
            dict(exp=None),
        ]:
            with self.subTest(changes=changes):
                self.assertIsNone(await verifier.verify_token(self.token(**changes)))
        self.assertIsNone(await verifier.verify_token("invalid"))
        self.assertIsNone(
            await verifier.verify_token(
                jwt.encode({"exp": time.time() + 300}, "x" * 32, algorithm="HS256")
            )
        )
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.assertIsNone(
            await verifier.verify_token(
                jwt.encode(
                    jwt.decode(self.token(), options={"verify_signature": False}),
                    other,
                    algorithm="RS256",
                )
            )
        )

    async def test_required_claims(self):
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        for name in ("exp", "iat", "iss", "aud", "sub", "client_id"):
            with self.subTest(name=name):
                missing = {key: value for key, value in claims.items() if key != name}
                self.assertIsNone(
                    await JWTTokenVerifier(self.config).verify_token(
                        jwt.encode(missing, self.key, algorithm="RS256")
                    )
                )

    def test_cli_oauth_http(self):
        with (
            patch(
                "sys.argv",
                [
                    "yamcps",
                    "serve",
                    "--transport",
                    "http",
                    "--host",
                    "0.0.0.0",
                    "--oauth-config",
                    "oauth.json",
                ],
            ),
            patch("yamcps.cli.OAuthConfig.from_file", return_value=self.config),
            patch("yamcps.cli.create_server") as create,
        ):
            main()
        self.assertIs(create.call_args.kwargs["oauth"], self.config)
        self.assertEqual(create.return_value.run.call_args.kwargs["host"], "0.0.0.0")
        self.assertTrue(
            create.return_value.run.call_args.kwargs[
                "transport_security"
            ].enable_dns_rebinding_protection
        )

    def test_configuration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "key.pem").write_bytes(
                self.key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )
            data = dict(
                issuer_url=self.config.issuer_url,
                resource_url=self.config.resource_url,
                public_key_file="key.pem",
                required_scopes=["mcp:access"],
            )
            path = root / "oauth.json"
            path.write_text(json.dumps(data))
            loaded = OAuthConfig.from_file(path)
            self.assertEqual(loaded.required_scopes, ("mcp:access",))
            self.assertTrue(loaded.auth_settings().validate_token_resource)
            for field, value in [
                ("issuer_url", "http://auth.example.com"),
                ("resource_url", "https://mcp.example.com/other"),
                ("resource_url", "https://user:password@mcp.example.com/mcp"),
                ("required_scopes", []),
                ("required_scopes", ["a b"]),
                ("public_key_file", "missing.pem"),
            ]:
                with self.subTest(field=field, value=value):
                    path.write_text(json.dumps({**data, field: value}))
                    with self.assertRaises(OAuthError):
                        OAuthConfig.from_file(path)
            path.write_text("[]")
            with self.assertRaises(OAuthError):
                OAuthConfig.from_file(path)
            path.write_text("{")
            with self.assertRaises(OAuthError):
                OAuthConfig.from_file(path)

    def test_http_auth_and_discovery(self):
        server = create_server(["demo"], oauth=self.config)
        app = server.streamable_http_app(transport_security=self.config.transport_security())
        with TestClient(app, base_url="https://mcp.example.com") as client:
            response = client.post("/mcp", json={})
            self.assertEqual(response.status_code, 401)
            self.assertIn("resource_metadata=", response.headers["www-authenticate"])
            metadata = client.get("/.well-known/oauth-protected-resource/mcp").json()
            self.assertEqual(metadata["resource"], self.config.resource_url)
            self.assertEqual(metadata["authorization_servers"], [self.config.issuer_url])
            self.assertEqual(
                client.post("/mcp", headers={"Authorization": "Bearer invalid"}).status_code, 401
            )
            response = client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer " + self.token(),
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + self.token(), "Host": "evil.example.com"},
                json={},
            )
            self.assertEqual(response.status_code, 421)

    def test_cli_rejects_unprotected_remote_and_oauth_stdio(self):
        for args in [
            ["serve", "--transport", "http", "--host", "0.0.0.0"],
            ["serve", "--oauth-config", "oauth.json"],
        ]:
            with self.subTest(args=args), patch("sys.argv", ["yamcps", *args]):
                with self.assertRaises(SystemExit) as raised:
                    main()
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

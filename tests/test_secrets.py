"""Credentials, encryption and connector injection regression tests."""

import base64
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import SecretStr

from yamcps.cli import main
from yamcps.connectors import ConnectorError
from yamcps.secrets import BasicAuth, ConnectorSecrets, SecretError, TokenAuth
from yamcps.server import create_server
from yamcps.vault import Vault


class CredentialTests(unittest.TestCase):
    def test_scoping_and_masking(self):
        secrets = ConnectorSecrets(
            "my-api", {"YAMCPS_MY_API_TOKEN": "very-private", "YAMCPS_OTHER_TOKEN": "other-private"}
        )
        self.assertEqual(secrets.require("token").get_secret_value(), "very-private")
        self.assertNotIn("very-private", repr(secrets))
        auth = secrets.token_auth()
        self.assertNotIn("very-private", repr(auth))
        self.assertNotIn("very-private", str(auth.authorization_header()))
        self.assertEqual(auth.authorization_header().get_secret_value(), "Bearer very-private")
        self.assertEqual(secrets.redact("error very-private"), "error [REDACTED]")
        self.assertIsNone(secrets.get("missing"))
        with self.assertRaisesRegex(SecretError, "YAMCPS_MY_API_MISSING"):
            secrets.require("missing")

    def test_environment_and_empty(self):
        with patch.dict(os.environ, {"YAMCPS_API_TOKEN": "example"}, clear=True):
            self.assertEqual(ConnectorSecrets("api").require("token").get_secret_value(), "example")
        self.assertIsNone(ConnectorSecrets("api", {"YAMCPS_API_TOKEN": ""}).get("token"))
        for identifier in ["../api", "api_foo", "a--b", ""]:
            with self.subTest(identifier=identifier), self.assertRaises(SecretError):
                ConnectorSecrets(identifier)

    def test_auth_validation(self):
        for value in ["", "bad\r\nHeader", "a b"]:
            with self.subTest(value=value), self.assertRaises(SecretError):
                TokenAuth(SecretStr(value)).authorization_header()
        with self.assertRaises(SecretError):
            TokenAuth(SecretStr("valid"), "bad\nscheme").authorization_header()
        with self.assertRaises(SecretError):
            BasicAuth(SecretStr("user:name"), SecretStr("pass")).authorization_header()
        secrets = ConnectorSecrets(
            "api", {"YAMCPS_API_USERNAME": "élise", "YAMCPS_API_PASSWORD": "p:ass"}
        )
        auth = secrets.basic_auth()
        encoded = auth.authorization_header().get_secret_value().split(" ")[1]
        self.assertEqual(base64.b64decode(encoded).decode(), "élise:p:ass")
        self.assertNotIn("p:ass", repr(auth))

    def test_injection_before_registration_and_redacted_errors(self):
        calls = []

        class Plugin:
            id = "api"

            def configure(self, secrets):
                self.auth = secrets.token_auth()
                calls.append("configure")

            def register(self, server):
                calls.append("register")
                raise RuntimeError("rejected " + self.auth.token.get_secret_value())

        entry = Mock()
        entry.load.return_value = Plugin
        with patch("yamcps.connectors.discover", return_value={"api": entry}):
            with self.assertRaises(ConnectorError) as error:
                create_server(["api"], secret_values={"YAMCPS_API_TOKEN": "private-token"})
        self.assertEqual(calls, ["configure", "register"])
        self.assertNotIn("private-token", str(error.exception))
        self.assertIn("REDACTED", str(error.exception))

    def test_configuration_errors(self):
        for configure in [
            42,
            Mock(side_effect=RuntimeError("sensitive")),
            Mock(side_effect=SecretError("sensitive")),
        ]:
            plugin = Mock(id="api", configure=configure, spec=["id", "register", "configure"])
            entry = Mock()
            entry.load.return_value = lambda: plugin
            with patch("yamcps.connectors.discover", return_value={"api": entry}):
                with self.assertRaises(ConnectorError) as error:
                    create_server(["api"], secret_values={"YAMCPS_API_TOKEN": "sensitive"})
            self.assertNotIn("sensitive", str(error.exception))


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "test.yamcps-vault"
        self.key = self.root / "test.yamcps-key"
        self.vault = Vault(self.path, self.key)
        self.vault.initialize()

    def test_roundtrip_and_non_deterministic_ciphertext(self):
        self.vault.set("api", "token", "private-token")
        first = self.path.read_bytes()
        self.assertNotIn(b"private-token", first)
        self.assertNotIn(b"YAMCPS_API_TOKEN", first)
        self.vault.set("api", "token", "private-token")
        self.assertNotEqual(first, self.path.read_bytes())
        self.assertEqual(self.vault.names(), ["YAMCPS_API_TOKEN"])
        self.assertEqual(self.vault.values(), {"YAMCPS_API_TOKEN": "private-token"})
        self.vault.delete("api", "token")
        self.assertEqual(self.vault.values(), {})
        if os.name == "posix":
            self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_and_missing_key(self):
        self.key.write_bytes(b"x" * 32)
        with self.assertRaisesRegex(SecretError, "authentication"):
            self.vault.values()
        self.key.write_bytes(b"short")
        with self.assertRaisesRegex(SecretError, "32 bytes"):
            self.vault.values()
        self.key.unlink()
        with self.assertRaisesRegex(SecretError, "read master"):
            self.vault.values()

    def test_tamper_and_format(self):
        data = self.path.read_bytes()
        self.path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaisesRegex(SecretError, "authentication"):
            self.vault.values()
        self.path.write_bytes(b"unknown format")
        with self.assertRaisesRegex(SecretError, "format"):
            self.vault.values()
        self.path.unlink()
        with self.assertRaisesRegex(SecretError, "read vault"):
            self.vault.values()

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_insecure_key_permissions(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(SecretError, "permissions"):
            self.vault.values()

    def test_refuse_overwrite_and_lock(self):
        original = self.key.read_bytes()
        with self.assertRaises(SecretError):
            self.vault.initialize()
        self.assertEqual(self.key.read_bytes(), original)
        with self.assertRaises(SecretError):
            Vault(self.path, self.path)
        lock = self.path.with_name(self.path.name + ".lock")
        lock.touch()
        with self.assertRaisesRegex(SecretError, "locked"):
            self.vault.set("api", "token", "new")
        lock.unlink()
        with self.assertRaises(SecretError):
            self.vault.set("api", "token", "")
        with self.assertRaisesRegex(SecretError, "does not exist"):
            self.vault.delete("api", "missing")
        self.assertFalse(lock.exists())

    def test_failed_write_preserves_vault(self):
        original = self.path.read_bytes()
        with patch("yamcps.vault.os.replace", side_effect=OSError):
            with self.assertRaises(SecretError):
                self.vault.set("api", "token", "value")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".yamcps-vault-*")))
        self.assertFalse(self.path.with_name(self.path.name + ".lock").exists())

    def test_initialization_missing_directory(self):
        key = self.root / "new.yamcps-key"
        vault = Vault(self.root / "missing" / "vault", key)
        with self.assertRaises(SecretError):
            vault.initialize()
        self.assertFalse(key.exists())

    def run_cli(self, *args):
        with patch("sys.argv", ["yamcps", *args]), patch("sys.stdin.isatty", return_value=True):
            main()

    def test_cli_set_list_delete_and_serve(self):
        options = ["--vault", str(self.path), "--key-file", str(self.key)]
        with patch("yamcps.onboarding.getpass.getpass", return_value="hidden-input"):
            self.run_cli("secrets", "set", *options, "--connector", "api", "--name", "token")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("secrets", "list", *options)
        self.assertEqual(output.getvalue(), "YAMCPS_API_TOKEN\n")
        with patch("yamcps.cli.create_server") as create:
            self.run_cli("serve", "--connector", "api", *options)
        self.assertEqual(create.call_args.args, (["api"],))
        self.assertEqual(create.call_args.kwargs["vault"].path, self.vault.path)
        self.assertTrue(create.call_args.kwargs["interactive"])
        self.run_cli("secrets", "delete", *options, "--connector", "api", "--name", "token")
        self.assertEqual(self.vault.names(), [])

    def test_cli_initialization_and_errors(self):
        path, key = self.root / "other.yamcps-vault", self.root / "other.yamcps-key"
        self.run_cli("secrets", "init", "--vault", str(path), "--key-file", str(key))
        self.assertEqual(Vault(path, key).values(), {})
        with contextlib.redirect_stderr(io.StringIO()):
            for args in [
                ("serve", "--connector", "demo", "--vault", str(path)),
                ("serve", "--connector", "demo", "--port", "0"),
            ]:
                with self.assertRaises(SystemExit):
                    self.run_cli(*args)
            with patch("yamcps.onboarding.getpass.getpass", side_effect=EOFError):
                with self.assertRaises(SystemExit):
                    self.run_cli(
                        "secrets",
                        "set",
                        "--vault",
                        str(path),
                        "--key-file",
                        str(key),
                        "--connector",
                        "api",
                        "--name",
                        "token",
                    )


class AuthenticatedConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_vault_credentials_used_inside_handler(self):
        from mcp import Client

        request = Mock(return_value="authenticated")

        class Plugin:
            id = "api"

            def configure(self, secrets):
                self.auth = secrets.basic_auth()

            def register(self, server):
                @server.tool()
                async def api_status() -> str:
                    """Check upstream status using internal API credentials."""
                    return request(
                        headers={
                            "Authorization": self.auth.authorization_header().get_secret_value()
                        }
                    )

        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(
                Path(directory) / "secrets.yamcps-vault", Path(directory) / "master.yamcps-key"
            )
            vault.initialize()
            vault.set("api", "username", "demo-user")
            vault.set("api", "password", "demo-password")
            entry = Mock()
            entry.load.return_value = Plugin
            with patch("yamcps.connectors.discover", return_value={"api": entry}):
                server = create_server(["api"], secret_values=vault.values())
            async with Client(server) as client:
                tools = await client.list_tools()
                self.assertEqual(tools.tools[0].input_schema["properties"], {})
                result = await client.call_tool("api_status", {})
                self.assertEqual(result.structured_content, {"result": "authenticated"})
            encoded = base64.b64encode(b"demo-user:demo-password").decode()
            request.assert_called_once_with(headers={"Authorization": f"Basic {encoded}"})


if __name__ == "__main__":
    unittest.main()

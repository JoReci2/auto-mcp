"""Integration coverage for the packaged secret-management demo."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from mcp.server import MCPServer
from yamcps_demo_secrets import DemoSecretsConnector

from yamcps.cli import main
from yamcps.connectors import discover
from yamcps.secrets import ConnectorSecrets, SecretError
from yamcps.server import create_server
from yamcps.vault import Vault


class DemoSecretsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.vault = Vault(root / "data/demo.yamcps-vault", root / "keys/demo.yamcps-key")
        self.values = ["sentinel-token-934", "sentinel-user-752", "sentinel-password-816"]
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    async def test_interactive_startup_status_skill_and_reuse(self):
        self.assertIn("demo-secrets", discover())
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("yamcps.onboarding.getpass.getpass", side_effect=self.values) as prompt,
        ):
            server = create_server(["demo", "demo-secrets"], vault=self.vault, interactive=True)
        self.assertEqual(prompt.call_count, 3)
        async with Client(server) as client:
            tools = await client.list_tools()
            status = next(tool for tool in tools.tools if tool.name == "demo_secrets_status")
            self.assertEqual(status.input_schema["properties"], {})
            result = await client.call_tool("demo_secrets_status", {})
            self.assertEqual(
                result.structured_content,
                {"configured": True, "token_auth": "Bearer", "basic_auth": "Basic"},
            )
            skill = await client.read_resource("skill://demo-secrets-check/SKILL.md")
            self.assertIn("demo_secrets_status", skill.contents[0].text)
            exposed = repr((tools, result, skill, self.stdout.getvalue(), self.stderr.getvalue()))
            for value in self.values:
                self.assertNotIn(value, exposed)
                self.assertNotIn(value.encode(), self.vault.path.read_bytes())
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("yamcps.onboarding.getpass.getpass") as prompt,
        ):
            create_server(["demo-secrets"], vault=self.vault)
        prompt.assert_not_called()
        self.vault.delete("demo-secrets", "token")
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("yamcps.onboarding.getpass.getpass", return_value="replacement-token") as prompt,
        ):
            create_server(["demo-secrets"], vault=self.vault, interactive=True)
        prompt.assert_called_once()
        self.assertIn("demo-secrets/token", prompt.call_args.args[0])

    async def test_short_cli_wizard(self):
        with (
            patch("sys.argv", ["yamcps", "secrets", "set", "--connector", "demo-secrets"]),
            patch("yamcps.cli.default_vault", return_value=self.vault),
            patch("sys.stdin.isatty", return_value=True),
            patch("yamcps.onboarding.getpass.getpass", side_effect=self.values),
        ):
            main()
        self.assertEqual(len(self.vault.names()), 3)
        create_server(["demo-secrets"], vault=self.vault)

    async def test_noninteractive_missing_credentials(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("yamcps.onboarding.getpass.getpass") as prompt,
        ):
            with self.assertRaisesRegex(SecretError, "yamcps secrets set --connector demo-secrets"):
                create_server(["demo-secrets"], vault=self.vault)
        prompt.assert_not_called()
        self.assertFalse(self.vault.path.exists())

    async def test_registration_requires_configuration(self):
        plugin = DemoSecretsConnector()
        with self.assertRaises(SecretError):
            plugin.register(MCPServer("test"))
        with self.assertRaises(SecretError):
            plugin.configure(ConnectorSecrets("demo-secrets", {}))


if __name__ == "__main__":
    unittest.main()

"""Default discovery and explicit multi-plugin selection regressions."""

import contextlib
import io
import unittest
from importlib.metadata import EntryPoint
from unittest.mock import Mock, patch

from mcp import Client

from yamcps.cli import main
from yamcps.connectors import ConnectorError, load
from yamcps.server import create_server


def plugin_entry(name):
    entry = Mock()
    plugin = Mock(id=name, spec=["id", "register"])
    entry.load.return_value = lambda: plugin
    return entry


class SelectionTests(unittest.TestCase):
    def test_default_loads_every_plugin_in_sorted_order(self):
        entries = {"zeta": plugin_entry("zeta"), "alpha": plugin_entry("alpha")}
        with patch("yamcps.connectors.discover", return_value=entries) as discover:
            plugins = load()
        self.assertEqual([plugin.id for plugin in plugins], ["alpha", "zeta"])
        discover.assert_called_once()
        for entry in entries.values():
            entry.load.assert_called_once()

    def test_explicit_selection_preserves_order_and_skips_other_plugins(self):
        entries = {name: plugin_entry(name) for name in ["alpha", "beta", "unused"]}
        with patch("yamcps.connectors.discover", return_value=entries):
            plugins = load(["beta", "alpha"])
        self.assertEqual([plugin.id for plugin in plugins], ["beta", "alpha"])
        entries["unused"].load.assert_not_called()

    def test_no_installed_plugins_reports_action(self):
        with patch("yamcps.connectors.discover", return_value={}):
            with self.assertRaisesRegex(ConnectorError, "No connectors installed"):
                load()
            self.assertEqual(load([]), [])

    def test_invalid_plugin_does_not_silently_disappear(self):
        entry = Mock()
        entry.load.side_effect = ImportError("broken dependency")
        with patch("yamcps.connectors.discover", return_value={"broken": entry}):
            with self.assertRaisesRegex(ConnectorError, "broken"):
                load()

    def test_cli_default_and_multiple_selection(self):
        for arguments, expected in [
            ([], None),
            (["--connector", "demo", "--connector", "demo-secrets"], ["demo", "demo-secrets"]),
        ]:
            with (
                self.subTest(arguments=arguments),
                patch("sys.argv", ["yamcps", "serve", *arguments]),
                patch("yamcps.cli.create_server") as create,
                patch("yamcps.cli._select_vault"),
            ):
                main()
            self.assertEqual(create.call_args.args, (expected,))
            create.return_value.run.assert_called_once_with(transport="stdio")

    def test_secret_commands_still_require_a_connector(self):
        with (
            patch("sys.argv", ["yamcps", "secrets", "set"]),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit):
                main()


class AllPluginsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_server_registers_both_demo_plugins(self):
        entries = {
            name: EntryPoint(name=name, value=value, group="yamcps.connectors")
            for name, value in [
                ("demo", "yamcps_demo:DemoConnector"),
                ("demo-secrets", "yamcps_demo_secrets:DemoSecretsConnector"),
            ]
        }
        with patch("yamcps.connectors.discover", return_value=entries):
            server = create_server(
                secret_values={
                    "YAMCPS_DEMO_SECRETS_TOKEN": "test-token",
                    "YAMCPS_DEMO_SECRETS_USERNAME": "test-user",
                    "YAMCPS_DEMO_SECRETS_PASSWORD": "test-password",
                }
            )
        async with Client(server) as client:
            tools = await client.list_tools()
            self.assertEqual(
                {tool.name for tool in tools.tools}, {"demo_echo", "demo_secrets_status"}
            )
            result = await client.call_tool("demo_echo", {"message": "both loaded"})
            self.assertEqual(result.structured_content, {"result": "both loaded"})
            result = await client.call_tool("demo_secrets_status", {})
            self.assertTrue(result.structured_content["configured"])
            self.assertEqual(len((await client.list_resources()).resources), 2)


if __name__ == "__main__":
    unittest.main()

"""Configuration-dependent credential selection without external services."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mcp import Client, StdioServerParameters

from yamcps import ConfigError, ConfigSpec, ConfigStore, ConnectorConfigs, SecretSpec
from yamcps.cli import main
from yamcps.connectors import ConnectorError
from yamcps.onboarding import requirements_for_configs
from yamcps.server import create_server
from yamcps.vault import Vault


class Plugin:
    id = "example"

    def __init__(self, default=None):
        self.default = default
        self.calls = []

    def required_configs(self):
        return [ConfigSpec("enabled-services", default=self.default)]

    def required_secrets(self):
        return [SecretSpec("sonarr-token"), SecretSpec("seerr-token")]

    def required_secrets_for_configs(self, configs):
        self.calls.append("requirements")
        names = configs.require("enabled-services").split(",")
        if not names or any(name not in {"sonarr", "seerr"} for name in names):
            raise ValueError("private-invalid-selection")
        return [SecretSpec(f"{name}-token") for name in names]

    def configure(self, secrets):
        self.calls.append("secrets")
        self.secrets = secrets

    def configure_configs(self, configs):
        self.calls.append("configs")
        self.enabled = configs.require("enabled-services").split(",")
        for name in self.enabled:
            self.secrets.require(f"{name}-token")

    def register(self, server):
        self.calls.append("register")
        for name in self.enabled:
            server.tool(name=f"example_{name}")(self.status)

    def status(self) -> str:
        """Return a status without credentials."""
        return "ready"


class ConditionalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = ConfigStore(self.root / "configs.json")
        self.vault = Vault(self.root / "vault", self.root / "key")
        self.prompt = self.enterContext(
            patch("yamcps.onboarding.getpass.getpass", return_value="private-token")
        )
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def start(self, plugin=None, **kwargs):
        plugin = plugin or Plugin()
        with patch("yamcps.server.load", return_value=[plugin]) as load:
            server = create_server(["example"], config_store=self.store, vault=self.vault, **kwargs)
        load.assert_called_once_with(["example"])
        return plugin, server

    def test_file_environment_defaults_and_prompt_only_active(self):
        for source in ("file", "environment", "default"):
            with self.subTest(source=source):
                plugin = Plugin("sonarr" if source == "default" else None)
                if source == "file":
                    self.store.set("example", "enabled-services", "sonarr")
                elif source == "environment":
                    self.store.delete("example", "enabled-services")
                    os.environ["YAMCPS_EXAMPLE_ENABLED_SERVICES"] = "sonarr"
                else:
                    os.environ.clear()
                with patch("sys.stdin.isatty", return_value=True):
                    plugin, _ = self.start(plugin, interactive=True)
                self.assertEqual(plugin.calls, ["requirements", "secrets", "configs", "register"])
        self.prompt.assert_called_once()
        self.assertIn("example/sonarr-token", self.prompt.call_args.args[0])
        self.assertEqual(self.vault.names(), ["YAMCPS_EXAMPLE_SONARR_TOKEN"])

    def test_missing_or_invalid_configuration_precedes_secret_prompts(self):
        with patch("builtins.input") as input_prompt:
            with self.assertRaises(ConfigError):
                self.start(interactive=False)
            input_prompt.assert_not_called()
        for value in ("", "unknown", "sonarr,sonarr"):
            self.store.set("example", "enabled-services", value)
            with self.subTest(value=value), self.assertRaises((ConfigError, ConnectorError)):
                self.start(interactive=True)
        self.prompt.assert_not_called()

    def test_disabled_secrets_retained_and_reused_on_reactivation(self):
        with patch("sys.stdin.isatty", return_value=True):
            for selection in ("sonarr,seerr", "sonarr", "sonarr,seerr"):
                self.store.set("example", "enabled-services", selection)
                self.start(interactive=True)
        self.assertEqual(self.prompt.call_count, 2)
        self.assertEqual(len(self.vault.names()), 2)
        self.start(interactive=False)
        self.assertEqual(self.prompt.call_count, 2)

    def test_explicit_values_and_legacy_catalogue(self):
        plugin = Plugin()
        with patch("yamcps.server.load", return_value=[plugin]):
            create_server(
                ["example"],
                config_values={"YAMCPS_EXAMPLE_ENABLED_SERVICES": "seerr"},
                secret_values={"YAMCPS_EXAMPLE_SEERR_TOKEN": "private-explicit"},
            )
        self.prompt.assert_not_called()
        legacy = Mock(id="legacy", spec=["id", "required_secrets"])
        legacy.required_secrets.return_value = [SecretSpec("token")]
        self.assertEqual(
            requirements_for_configs(legacy, ConnectorConfigs("legacy", {})),
            [SecretSpec("token")],
        )

    def test_skills_are_selected_after_configuration_injection(self):
        plugin = Plugin()
        for name in ("sonarr", "seerr"):
            root = self.root / f"example-{name}"
            root.mkdir()
            (root / "SKILL.md").write_text(
                f"---\nname: example-{name}\ndescription: Selected service\n---\nStatus"
            )

        def skill_roots():
            plugin.calls.append("skills")
            return [self.root / f"example-{name}" for name in plugin.enabled]

        plugin.skill_roots = skill_roots
        self.store.set("example", "enabled-services", "seerr")
        with patch("sys.stdin.isatty", return_value=True):
            self.start(plugin, interactive=True)
        self.assertEqual(plugin.calls, ["requirements", "secrets", "configs", "skills", "register"])

    def test_documented_example_validates_selection_and_catalogue(self):
        text = (Path(__file__).parents[1] / "CONTRIBUTING.md").read_text()
        section = text.split("### Secrets conditionnels", 1)[1]
        code = section.split("```python\n", 1)[1].split("```", 1)[0]
        namespace = {}
        exec(compile(code, "conditional-example", "exec"), namespace)
        plugin = namespace["ArrConnector"]()
        configs = ConnectorConfigs("arr", {"YAMCPS_ARR_ENABLED_SERVICES": "sonarr,seerr"})
        self.assertEqual(
            [spec.name for spec in requirements_for_configs(plugin, configs)],
            ["sonarr-api-key", "seerr-api-key"],
        )
        for selection in ("", "unknown", "sonarr,sonarr"):
            with self.subTest(selection=selection), self.assertRaises(ConnectorError):
                requirements_for_configs(
                    plugin, ConnectorConfigs("arr", {"YAMCPS_ARR_ENABLED_SERVICES": selection})
                )

    def test_all_declarations_checked_before_prompting(self):
        first = Plugin("sonarr")
        second = Plugin("unknown")
        second.id = "other"
        with (
            patch("yamcps.server.load", return_value=[first, second]),
            patch("sys.stdin.isatty", return_value=True),
            self.assertRaises(ConnectorError),
        ):
            create_server(vault=self.vault, config_store=self.store, interactive=True)
        self.prompt.assert_not_called()
        self.assertEqual(first.calls, ["requirements"])

    def test_explicit_configuration_replaces_environment_but_keeps_defaults(self):
        plugin = Plugin("seerr")
        with (
            patch.dict(os.environ, {"YAMCPS_EXAMPLE_ENABLED_SERVICES": "unknown"}),
            patch("yamcps.server.load", return_value=[plugin]),
        ):
            create_server(
                config_values={},
                secret_values={"YAMCPS_EXAMPLE_SEERR_TOKEN": "private-default"},
            )
        self.assertEqual(plugin.enabled, ["seerr"])
        self.prompt.assert_not_called()

    def test_configs_command_needs_no_credentials(self):
        with (
            patch(
                "sys.argv",
                [
                    "yamcps",
                    "configs",
                    "set",
                    "--connector",
                    "example",
                    "--name",
                    "enabled-services",
                    "--value",
                    "sonarr,seerr",
                    "--config-file",
                    str(self.store.path),
                ],
            ),
            patch("yamcps.cli.load") as load,
        ):
            main()
        load.assert_not_called()
        self.prompt.assert_not_called()
        self.assertFalse(self.vault.path.exists())
        self.assertEqual(self.store.values()["YAMCPS_EXAMPLE_ENABLED_SERVICES"], "sonarr,seerr")

    def test_bad_hooks_are_sanitized(self):
        async def asynchronous(configs):
            return []

        for hook in (
            asynchronous,
            False,
            Mock(return_value=None),
            Mock(return_value=["token"]),
            Mock(return_value=[SecretSpec("unknown")]),
            Mock(return_value=[SecretSpec("seerr-token")] * 2),
            Mock(side_effect=ValueError("private-token")),
        ):
            plugin = Plugin()
            plugin.required_secrets_for_configs = hook
            with self.subTest(hook=hook), self.assertRaises(ConnectorError) as error:
                requirements_for_configs(plugin, ConnectorConfigs("example", {}))
            self.assertNotIn("private-token", str(error.exception))

    def cli(self, *options):
        with (
            patch(
                "sys.argv",
                [
                    "yamcps",
                    "secrets",
                    "set",
                    "--connector",
                    "example",
                    "--vault",
                    str(self.vault.path),
                    "--key-file",
                    str(self.vault.key_file),
                    "--config-file",
                    str(self.store.path),
                    *options,
                ],
            ),
            patch("yamcps.cli.load", return_value=[Plugin()]),
        ):
            main()

    def test_cli_config_file_name_and_missing_selection(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit):
                self.cli()
        self.prompt.assert_not_called()
        self.store.set("example", "enabled-services", "seerr")
        # Discovery does not import any factory.
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("yamcps.cli.discover", return_value={"example": Mock()}),
        ):
            with self.assertRaises(SystemExit):
                self.cli("--name", "sonarr-token")
            self.prompt.assert_not_called()
            self.cli("--name", "seerr-token")
        self.assertEqual(self.vault.names(), ["YAMCPS_EXAMPLE_SEERR_TOKEN"])


class ConditionalMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_conditional_stdio(self):
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(Path(__file__).parent)!r}); "
            f"sys.path.insert(0, {str(Path(__file__).parents[1] / 'src')!r}); "
            "from unittest.mock import patch; "
            "from test_conditional_secrets import Plugin; "
            "from yamcps.server import create_server; "
            "patch('yamcps.server.load', return_value=[Plugin()]).start(); "
            "create_server(['example'], "
            "config_values={'YAMCPS_EXAMPLE_ENABLED_SERVICES': 'sonarr'}, "
            "secret_values={'YAMCPS_EXAMPLE_SONARR_TOKEN': 'private-token'})"
            ".run(transport='stdio')"
        )
        async with Client(
            StdioServerParameters(command=sys.executable, args=["-c", script])
        ) as client:
            tools = await client.list_tools()
            self.assertEqual([tool.name for tool in tools.tools], ["example_sonarr"])
            result = await client.call_tool("example_sonarr", {})
            self.assertNotIn("private-token", str(result))

    async def test_only_selected_tools_in_memory(self):
        with patch("yamcps.server.load", return_value=[Plugin()]):
            server = create_server(
                ["example"],
                config_values={"YAMCPS_EXAMPLE_ENABLED_SERVICES": "seerr"},
                secret_values={"YAMCPS_EXAMPLE_SEERR_TOKEN": "private-token"},
            )
        async with Client(server) as client:
            tools = await client.list_tools()
            self.assertEqual([tool.name for tool in tools.tools], ["example_seerr"])
            result = await client.call_tool("example_seerr", {})
            self.assertNotIn("private-token", str(result))


if __name__ == "__main__":
    unittest.main()

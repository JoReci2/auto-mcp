"""Plaintext settings and startup onboarding independent of external plugins."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps import ConfigError, ConfigSpec, ConfigStore, ConnectorConfigs
from yamcps.cli import main
from yamcps.configs import config_requirements, configure_configs, prepare_configs
from yamcps.connectors import ConnectorError
from yamcps.rag import RagConfig
from yamcps.server import create_server


class Plugin:
    id = "example"

    def required_configs(self):
        return [
            ConfigSpec("endpoint", "Nonsecret service URL"),
            ConfigSpec("mode", default="local"),
        ]

    def configure_configs(self, configs):
        self.settings = configs

    def register(self, server):
        pass


class DefaultConfigPlugin(Plugin):
    id = "defaults"

    def required_configs(self):
        return [ConfigSpec("model", default="")]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ConfigStore(self.root / "config.json")

    def test_store_is_plaintext_atomic_and_preserves_other_plugins(self):
        self.assertEqual(self.store.values(), {})
        self.store.set("example", "endpoint", "https://example.test")
        self.store.set("docs", "model", "/local/model")
        self.assertEqual(
            json.loads(self.store.path.read_text())["YAMCPS_DOCS_MODEL"], "/local/model"
        )
        self.store.delete("example", "endpoint")
        self.assertEqual(self.store.values(), {"YAMCPS_DOCS_MODEL": "/local/model"})
        with self.assertRaises(ConfigError):
            self.store.delete("absent", "value")
        self.assertFalse(self.store.path.with_name("config.json.lock").exists())
        self.assertFalse(list(self.root.glob(".yamcps-config-*")))
        lock = self.store.path.with_name("config.json.lock")
        lock.touch()
        with self.assertRaises(ConfigError):
            self.store.set("docs", "model", "changed")
        self.assertEqual(self.store.values()["YAMCPS_DOCS_MODEL"], "/local/model")
        lock.unlink()

    def test_invalid_file_names_and_specs(self):
        for text in ["not-json", "[]", '{"invalid":"value"}', '{"YAMCPS_DOCS_MODEL":7}']:
            self.store.path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ConfigError):
                self.store.values()
            with self.assertRaises(ConfigError):
                self.store.set("docs", "model", "unchanged")
            self.assertEqual(self.store.path.read_text(), text)
        for name in ["../escape", "UPPER", "", "two words"]:
            with self.assertRaises(ConfigError):
                ConfigSpec(name)
        with self.assertRaises(ConfigError):
            ConfigSpec("test", default=1)
        with self.assertRaises(ConfigError):
            self.store.update({"invalid": "x"})

    def test_write_failure_preserves_previous_file(self):
        self.store.set("docs", "model", "original")
        with patch("yamcps.configs.os.replace", side_effect=OSError):
            with self.assertRaises(ConfigError):
                self.store.set("docs", "model", "changed")
        self.assertEqual(self.store.values()["YAMCPS_DOCS_MODEL"], "original")
        self.assertFalse(list(self.root.glob(".yamcps-config-*")))
        self.assertFalse(self.store.path.with_name("config.json.lock").exists())

    def test_cli_wizard_single_declared_field(self):
        with patch(
            "sys.argv",
            [
                "yamcps",
                "configs",
                "set",
                "--connector",
                "defaults",
                "--name",
                "model",
                "--config-file",
                str(self.store.path),
            ],
        ):
            with (
                patch("yamcps.cli.load", return_value=[DefaultConfigPlugin()]),
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", return_value="/local/model"),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                main()
        self.assertEqual(self.store.values(), {"YAMCPS_DEFAULTS_MODEL": "/local/model"})
        with patch("sys.stdin.isatty", return_value=True), self.assertRaises(ConfigError):
            configure_configs(DefaultConfigPlugin(), self.store, name="unknown")

    def test_scope_file_priority_environment_and_defaults(self):
        self.store.set("example", "endpoint", "file")
        self.store.set("other", "endpoint", "other")
        with patch.dict(os.environ, {"YAMCPS_EXAMPLE_ENDPOINT": "environment"}, clear=True):
            values = prepare_configs([Plugin()], self.store)
        view = ConnectorConfigs("example", values)
        self.assertEqual(view.require("endpoint"), "file")
        self.assertEqual(view.get("mode"), "local")
        self.assertIsNone(view.get("missing"))
        with self.assertRaises(ConfigError):
            view.require("missing")
        self.store.delete("example", "endpoint")
        with patch.dict(os.environ, {"YAMCPS_EXAMPLE_ENDPOINT": "environment"}, clear=True):
            self.assertEqual(
                prepare_configs([Plugin()], self.store)["YAMCPS_EXAMPLE_ENDPOINT"], "environment"
            )
            resolved = prepare_configs(
                [Plugin()], self.store, explicit={"YAMCPS_EXAMPLE_ENDPOINT": "memory"}
            )
        self.assertEqual(resolved["YAMCPS_EXAMPLE_ENDPOINT"], "memory")
        self.assertNotIn("YAMCPS_EXAMPLE_MODE", self.store.values())

    def test_missing_noninteractive_never_reads_stdin(self):
        with patch("builtins.input") as prompt:
            with self.assertRaisesRegex(ConfigError, "yamcps configs set --connector example"):
                prepare_configs([Plugin()], self.store)
        prompt.assert_not_called()
        self.assertFalse(self.store.path.exists())
        defaults = prepare_configs([DefaultConfigPlugin()], self.store)
        self.assertEqual(defaults["YAMCPS_DEFAULTS_MODEL"], "")
        self.assertFalse(self.store.path.exists())

    def test_interactive_startup_only_prompts_missing_and_commits_once(self):
        self.store.set("example", "mode", "remote")
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=["", "entered"]) as prompt,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            values = prepare_configs([Plugin()], self.store, interactive=True)
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(values["YAMCPS_EXAMPLE_MODE"], "remote")
        self.assertEqual(self.store.values()["YAMCPS_EXAMPLE_ENDPOINT"], "entered")
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input") as prompt:
            prepare_configs([Plugin()], self.store, interactive=True)
        prompt.assert_not_called()

    def test_wizard_keeps_current_values_and_cancel_does_not_write(self):
        self.store.set("example", "endpoint", "existing")
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=["", ""]),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            configure_configs(Plugin(), self.store)
        self.assertEqual(self.store.values()["YAMCPS_EXAMPLE_ENDPOINT"], "existing")
        self.assertEqual(self.store.values()["YAMCPS_EXAMPLE_MODE"], "local")
        original = self.store.path.read_bytes()
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=["changed", EOFError]),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(ConfigError):
                configure_configs(Plugin(), self.store)
        self.assertEqual(self.store.path.read_bytes(), original)
        with patch("sys.stdin.isatty", return_value=False), self.assertRaises(ConfigError):
            configure_configs(Plugin(), self.store)

    def test_invalid_declarations_and_consumers(self):
        for fields in [[ConfigSpec("same"), ConfigSpec("same")], ["bad"]]:
            plugin = Plugin()
            plugin.required_configs = Mock(return_value=fields)
            with self.assertRaises(ConfigError):
                config_requirements(plugin)

        async def invalid():
            return []

        plugin = Plugin()
        plugin.required_configs = invalid
        with self.assertRaises(ConfigError):
            config_requirements(plugin)
        plugin = Plugin()
        plugin.configure_configs = Mock(side_effect=ValueError("private-value"))
        with patch("yamcps.server.load", return_value=[plugin]):
            with self.assertRaises(ConnectorError) as error:
                create_server(config_values={"YAMCPS_EXAMPLE_ENDPOINT": "value"})
        self.assertNotIn("private-value", str(error.exception))
        with self.assertRaises(ConfigError):
            create_server([], config_store=self.store, config_values={})

    def test_config_injection_precedes_rag_and_old_plugins_need_nothing(self):
        calls = []

        class Configured(Plugin):
            def configure(self, secrets):
                calls.append("secrets")

            def configure_configs(self, configs):
                calls.append("configs")
                super().configure_configs(configs)

            def rag_config(self):
                calls.append("rag")
                self.settings.require("endpoint")
                return RagConfig()

            def configure_rag(self, context):
                self.context = context

            def register(self, server):
                calls.append("register")

        plugin = Configured()
        self.store.set("example", "endpoint", "value")
        with patch("yamcps.server.load", return_value=[plugin]):
            create_server(config_store=self.store)
        self.assertEqual(calls, ["secrets", "configs", "rag", "register"])
        bad = ConfigStore(self.root / "bad.json")
        bad.path.write_text("invalid")
        create_server(["demo"], config_store=bad)

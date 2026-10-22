"""Interactive credential discovery without touching a user's real vault."""

import contextlib
import getpass
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps import ConnectorSecrets, SecretSpec
from yamcps.cli import main
from yamcps.connectors import ConnectorError
from yamcps.onboarding import configure_secrets, default_vault, prepare_secrets, requirements
from yamcps.secrets import SecretError
from yamcps.server import create_server
from yamcps.vault import Vault


class ApiConnector:
    id = "api"

    def required_secrets(self):
        return [SecretSpec("username", "API username"), SecretSpec("password", "API password")]

    def configure(self, secrets):
        self.auth = secrets.basic_auth()

    def register(self, server):
        pass


class InteractiveSecretTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.vault = Vault(
            self.root / "data/secrets.yamcps-vault", self.root / "keys/master.yamcps-key"
        )
        self.terminal = self.enterContext(patch("sys.stdin.isatty", return_value=True))
        self.output = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.errors = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def test_default_paths_and_invalid_spec(self):
        with patch("yamcps.onboarding.Path.home", return_value=self.root):
            vault = default_vault()
        self.assertEqual(vault.path, self.root / ".local/share/yamcps/secrets.yamcps-vault")
        self.assertEqual(vault.key_file, self.root / ".config/yamcps/keys/master.yamcps-key")
        with self.assertRaises(SecretError):
            SecretSpec("../invalid")

    def test_missing_credentials_prompt_and_auto_initialize(self):
        with patch(
            "yamcps.onboarding.getpass.getpass", side_effect=["alice", "private-password"]
        ) as prompt:
            values = prepare_secrets([ApiConnector()], self.vault, interactive=True)
        self.assertEqual(len(prompt.call_args_list), 2)
        self.assertEqual(
            ConnectorSecrets("api", values).basic_auth().username.get_secret_value(), "alice"
        )
        self.assertEqual(values, self.vault.values())
        self.assertNotIn(b"private-password", self.vault.path.read_bytes())
        self.assertEqual(self.output.getvalue(), "")
        self.assertNotIn("private-password", self.errors.getvalue())

    def test_existing_credentials_are_not_prompted(self):
        with patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "original"]):
            prepare_secrets([ApiConnector()], self.vault, interactive=True)
        self.vault.delete("api", "password")
        with patch("yamcps.onboarding.getpass.getpass", return_value="replacement") as prompt:
            values = prepare_secrets([ApiConnector()], self.vault, interactive=True)
        prompt.assert_called_once()
        self.assertIn("api/password", prompt.call_args.args[0])
        self.assertEqual(values["YAMCPS_API_USERNAME"], "alice")
        with patch("yamcps.onboarding.getpass.getpass") as prompt:
            self.terminal.return_value = False
            self.assertEqual(
                prepare_secrets([ApiConnector()], self.vault, interactive=False), values
            )
        prompt.assert_not_called()

    def test_no_requirements_no_disk_changes(self):
        connector = Mock(id="plain", spec=["id", "register"])
        with patch("yamcps.onboarding.getpass.getpass") as prompt:
            self.assertEqual(prepare_secrets([connector], self.vault, interactive=False), {})
        prompt.assert_not_called()
        self.assertFalse(self.vault.path.parent.exists())

    def test_noninteractive_missing_values_never_read_stdin(self):
        for allowed, terminal in [(False, True), (True, False)]:
            with self.subTest(allowed=allowed, terminal=terminal):
                self.terminal.return_value = terminal
                with patch("yamcps.onboarding.getpass.getpass") as prompt:
                    with self.assertRaisesRegex(SecretError, "yamcps secrets set --connector api"):
                        prepare_secrets([ApiConnector()], self.vault, interactive=allowed)
                prompt.assert_not_called()
        self.assertFalse(self.vault.path.exists())

    def test_cancel_keeps_vault_unchanged(self):
        with patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "original"]):
            prepare_secrets([ApiConnector()], self.vault, interactive=True)
        original = self.vault.path.read_bytes()
        for error in [KeyboardInterrupt, EOFError, getpass.GetPassWarning]:
            with (
                self.subTest(error=error),
                patch("yamcps.onboarding.getpass.getpass", side_effect=["changed", error]),
            ):
                with self.assertRaises(SecretError):
                    configure_secrets("api", ApiConnector().required_secrets(), self.vault)
            self.assertEqual(self.vault.path.read_bytes(), original)

    def test_blank_new_value_retries_and_existing_can_be_kept(self):
        specs = ApiConnector().required_secrets()
        with patch("yamcps.onboarding.getpass.getpass", side_effect=["", "alice", "original"]):
            configure_secrets("api", specs, self.vault)
        with patch("yamcps.onboarding.getpass.getpass", side_effect=["", "updated"]):
            configure_secrets("api", specs, self.vault)
        self.assertEqual(
            self.vault.values(), {"YAMCPS_API_USERNAME": "alice", "YAMCPS_API_PASSWORD": "updated"}
        )

    def test_explicit_wizard_without_terminal_or_fields(self):
        self.terminal.return_value = False
        with self.assertRaisesRegex(SecretError, "terminal"):
            configure_secrets("api", ApiConnector().required_secrets(), self.vault)
        with self.assertRaisesRegex(SecretError, "no required secrets"):
            configure_secrets("api", [], self.vault)

    def test_invalid_declarations_are_rejected(self):
        for declaration in [
            42,
            Mock(return_value=["token"]),
            Mock(return_value=[SecretSpec("token"), SecretSpec("token")]),
            Mock(side_effect=RuntimeError("hidden details")),
        ]:
            with self.subTest(declaration=declaration):
                connector = Mock(id="api", required_secrets=declaration)
                with self.assertRaisesRegex(ConnectorError, "invalid required_secrets"):
                    requirements(connector)

    def test_corrupt_or_partial_vault_never_reinitialized(self):
        self.vault.path.parent.mkdir(parents=True)
        self.vault.path.write_bytes(b"existing-but-invalid")
        with patch("yamcps.onboarding.getpass.getpass") as prompt:
            with self.assertRaises(SecretError):
                prepare_secrets([ApiConnector()], self.vault, interactive=True)
        prompt.assert_not_called()
        self.assertEqual(self.vault.path.read_bytes(), b"existing-but-invalid")

    def test_permissions_error_and_invalid_batch(self):
        with patch("yamcps.onboarding.Path.mkdir", side_effect=OSError):
            with patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "password"]):
                with self.assertRaisesRegex(SecretError, "directory"):
                    prepare_secrets([ApiConnector()], self.vault, interactive=True)
        with self.assertRaises(SecretError):
            self.vault.update({"invalid": "value"})

    def test_server_prompts_before_configure_and_loads_once(self):
        plugin = ApiConnector()
        entry = Mock()
        entry.load.return_value = Mock(return_value=plugin)
        with (
            patch("yamcps.connectors.discover", return_value={"api": entry}),
            patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "password"]),
        ):
            create_server(["api"], vault=self.vault, interactive=True)
        entry.load.assert_called_once()
        entry.load.return_value.assert_called_once_with()
        self.assertEqual(plugin.auth.username.get_secret_value(), "alice")
        with self.assertRaises(SecretError):
            create_server(["api"], vault=self.vault, secret_values={})

    def test_short_cli_wizard_and_custom_vault(self):
        entry = Mock()
        entry.load.return_value = ApiConnector
        with (
            patch("yamcps.connectors.discover", return_value={"api": entry}),
            patch("yamcps.cli.default_vault", return_value=self.vault),
            patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "password"]),
            patch("sys.argv", ["yamcps", "secrets", "set", "--connector", "api"]),
        ):
            main()
        self.assertEqual(self.vault.names(), ["YAMCPS_API_PASSWORD", "YAMCPS_API_USERNAME"])
        with (
            patch(
                "sys.argv",
                [
                    "yamcps",
                    "secrets",
                    "set",
                    "--connector",
                    "api",
                    "--name",
                    "token",
                    "--vault",
                    str(self.vault.path),
                    "--key-file",
                    str(self.vault.key_file),
                ],
            ),
            patch("yamcps.onboarding.getpass.getpass", return_value="manual-token"),
        ):
            main()
        self.assertEqual(self.vault.values()["YAMCPS_API_TOKEN"], "manual-token")

    def test_cli_startup_onboards_then_reuses_credentials_without_terminal(self):
        plugin = ApiConnector()
        entry = Mock()
        entry.load.return_value = lambda: plugin
        with (
            patch("yamcps.connectors.discover", return_value={"api": entry}),
            patch("yamcps.cli.default_vault", return_value=self.vault),
            patch("sys.argv", ["yamcps", "serve", "--connector", "api"]),
            patch("yamcps.registry.StrictServer.run") as run,
        ):
            with patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", "password"]):
                main()
            run.assert_called_once_with(transport="stdio")
            self.terminal.return_value = False
            with patch("yamcps.onboarding.getpass.getpass") as prompt:
                main()
            prompt.assert_not_called()
        self.assertEqual(plugin.auth.username.get_secret_value(), "alice")

    def test_cli_missing_secrets_noninteractive_reports_command(self):
        entry = Mock()
        entry.load.return_value = ApiConnector
        self.terminal.return_value = False
        with (
            patch("yamcps.connectors.discover", return_value={"api": entry}),
            patch("yamcps.cli.default_vault", return_value=self.vault),
            patch("sys.argv", ["yamcps", "serve", "--connector", "api"]),
            patch("yamcps.onboarding.getpass.getpass") as prompt,
        ):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("yamcps secrets set --connector api", self.errors.getvalue())
        prompt.assert_not_called()
        self.assertFalse(self.vault.path.exists())

    def test_cancel_first_configuration_does_not_initialize(self):
        with patch("yamcps.onboarding.getpass.getpass", side_effect=["alice", EOFError]):
            with self.assertRaises(SecretError):
                prepare_secrets([ApiConnector()], self.vault, interactive=True)
        self.assertFalse(self.vault.path.exists())
        self.assertFalse(self.vault.key_file.exists())


if __name__ == "__main__":
    unittest.main()

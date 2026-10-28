"""CLI presentation, real editor keystrokes and safe atomic persistence."""

import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from yamcps.cli import main
from yamcps.configs import ConfigError, ConfigSpec, ConfigStore, configure_configs
from yamcps.editor import (
    EditorError,
    SecretMask,
    _parse,
    edit_configs,
    edit_json,
    edit_secrets,
    editor_application,
)
from yamcps.onboarding import configure_secrets, initialize_vault
from yamcps.secrets import SecretError, SecretSpec
from yamcps.terminal import listing
from yamcps.vault import Vault


class Plugin:
    id = "api"

    def required_configs(self):
        return [
            ConfigSpec("endpoint", "Service URL", "https://default.test"),
            ConfigSpec("mode", "Mode"),
        ]

    def required_secrets(self):
        return [SecretSpec("token", "API token")]


class TerminalStream(io.StringIO):
    def isatty(self):
        return True


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = ConfigStore(self.root / "config.json")

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", ["yamcps", *args]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            main()
        return stdout.getvalue(), stderr.getvalue()

    def test_color_table_literal_markup_no_color_and_redirected_tsv(self):
        for no_color in (False, True):
            output = TerminalStream()
            environment = {"TERM": "xterm", "COLUMNS": "160"}
            if no_color:
                environment["NO_COLOR"] = ""
            with (
                patch.dict(os.environ, environment, clear=True),
                contextlib.redirect_stdout(output),
            ):
                listing(["Field", "Description"], [["name", "[red]literal[/red]"]])
            self.assertIn("[red]literal[/red]", output.getvalue())
            self.assertEqual("\x1b[" in output.getvalue(), not no_color)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            listing(["Field", "Value"], [["key", "one\ntwo\tthree\r\x1b"]])
        self.assertEqual(output.getvalue(), "Field\tValue\nkey\tone\\ntwo\\tthree\\r\\x1b\n")

    def test_connector_listing_does_not_import_plugins_and_preserves_plain_output(self):
        entry = Mock(value="module:factory")
        with patch("yamcps.cli.discover", return_value={"api": entry}):
            stdout, _ = self.cli("connectors", "list")
        self.assertEqual(stdout, "api\tmodule:factory\n")
        entry.load.assert_not_called()

    def test_config_listing_metadata_missing_defaults_and_orphan_fields(self):
        self.store.set("api", "endpoint", "")
        self.store.set("orphan", "name", "saved")
        with (
            patch("yamcps.cli.discover", return_value={"api": Mock()}),
            patch("yamcps.cli.load", return_value=[Plugin()]) as load,
        ):
            stdout, _ = self.cli("configs", "list", "--config-file", str(self.store.path))
        load.assert_called_once_with(["api"])
        self.assertIn("Name\tDescription\tDefault\tStored value", stdout)
        self.assertIn("YAMCPS_API_ENDPOINT\tService URL\t'https://default.test'\t''", stdout)
        self.assertIn("YAMCPS_API_MODE\tMode\trequired\tnot configured", stdout)
        self.assertIn("YAMCPS_ORPHAN_NAME", stdout)
        with patch("yamcps.cli.load", return_value=[Plugin()]) as load:
            stdout, _ = self.cli(
                "configs", "list", "--connector", "api", "--config-file", str(self.store.path)
            )
        load.assert_called_once_with(["api"])
        self.assertNotIn("YAMCPS_ORPHAN_NAME", stdout)
        self.assertEqual(self.store.values()["YAMCPS_ORPHAN_NAME"], "saved")

    def test_config_list_without_plugins_keeps_unknown_values(self):
        self.store.set("orphan", "name", "saved")
        with patch("yamcps.cli.discover", return_value={}):
            stdout, _ = self.cli("configs", "list", "--config-file", str(self.store.path))
        self.assertIn("YAMCPS_ORPHAN_NAME", stdout)

    def test_wizard_displays_default_description_and_current_value(self):
        self.store.set("api", "endpoint", "https://current.test")
        errors, output = io.StringIO(), io.StringIO()
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=["", "remote"]),
            contextlib.redirect_stderr(errors),
            contextlib.redirect_stdout(output),
        ):
            configure_configs(Plugin(), self.store)
        for text in ("api/endpoint", "Service URL", "https://default.test", "https://current.test"):
            self.assertIn(text, errors.getvalue())
        self.assertEqual(output.getvalue(), "")

    def test_secret_wizard_and_listing_never_print_values(self):
        vault = Vault(self.root / "vault", self.root / "key")
        errors = io.StringIO()
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("yamcps.onboarding.getpass.getpass", return_value="private-marker"),
            contextlib.redirect_stderr(errors),
        ):
            configure_secrets("api", Plugin().required_secrets(), vault)
        self.assertIn("API token", errors.getvalue())
        self.assertIn("Default: required", errors.getvalue())
        self.assertNotIn("private-marker", errors.getvalue())
        stdout, stderr = self.cli(
            "secrets", "list", "--vault", str(vault.path), "--key-file", str(vault.key_file)
        )
        self.assertEqual(stdout, "YAMCPS_API_TOKEN\n")
        self.assertNotIn("private-marker", stdout + stderr)

    def test_cli_editor_dispatch_custom_paths_and_selected_plugin(self):
        with (
            patch("yamcps.cli.load", return_value=[Plugin()]) as load,
            patch("yamcps.cli.edit_configs", return_value=True) as edit,
        ):
            stdout, stderr = self.cli(
                "configs", "edit", "--connector", "api", "--config-file", str(self.store.path)
            )
        load.assert_called_once_with(["api"])
        self.assertEqual(edit.call_args.args[0].path, self.store.path)
        self.assertIsInstance(edit.call_args.args[1], Plugin)
        self.assertEqual(stdout, "")
        self.assertIn("Saved.", stderr)
        with patch("yamcps.cli.edit_secrets", return_value=False) as edit:
            stdout, stderr = self.cli(
                "secrets",
                "edit",
                "--vault",
                str(self.root / "v"),
                "--key-file",
                str(self.root / "k"),
            )
        self.assertEqual(edit.call_args.args[0].path, self.root / "v")
        self.assertIsNone(edit.call_args.args[1])
        self.assertIn("No changes saved.", stderr)
        with (
            patch("yamcps.cli.load", return_value=[Plugin()]) as load,
            patch("yamcps.cli.edit_secrets", return_value=True),
        ):
            self.cli("secrets", "edit", "--connector", "api")
        load.assert_called_once_with(["api"])

    def test_editor_noninteractive_fails_cleanly_without_reading_stdin(self):
        errors = io.StringIO()
        with (
            patch("sys.argv", ["yamcps", "configs", "edit", "--config-file", str(self.store.path)]),
            patch("sys.stdin.isatty", return_value=False),
            patch("builtins.input") as read,
            contextlib.redirect_stderr(errors),
            self.assertRaises(SystemExit) as exit,
        ):
            main()
        self.assertEqual(exit.exception.code, 2)
        self.assertIn("requires stdin and stderr terminals", errors.getvalue())
        read.assert_not_called()
        self.assertFalse(self.store.path.exists())


class EditorPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = ConfigStore(self.root / "config.json")
        self.vault = Vault(self.root / "vault", self.root / "key")

    def test_parse_validation_never_echoes_input(self):
        for text, allowed, secret in [
            ('{"private-marker"', None, False),
            ('{"YAMCPS_API_TOKEN":"one","YAMCPS_API_TOKEN":"two"}', None, True),
            ("[]", None, False),
            ('{"wrong":"private-marker"}', None, False),
            ('{"YAMCPS_API_TOKEN":3}', None, False),
            ('{"YAMCPS_OTHER_TOKEN":"private-marker"}', {"YAMCPS_API_TOKEN"}, True),
            ('{"YAMCPS_API_TOKEN":""}', None, True),
        ]:
            with self.subTest(text=text), self.assertRaises(EditorError) as error:
                _parse(text, allowed, secret)
            self.assertNotIn("private-marker", str(error.exception))
        self.assertEqual(_parse('{"YAMCPS_API_NAME":"é"}', None, False), {"YAMCPS_API_NAME": "é"})

    def test_scoped_configs_exact_fields_preserve_similar_prefix_and_unknowns(self):
        for key, value in {
            "YAMCPS_API_ENDPOINT": "old",
            "YAMCPS_API_BAR_TOKEN": "other",
            "YAMCPS_API_LEGACY": "kept",
        }.items():
            self.store.update({key: value})
        with patch("yamcps.editor.edit_json", return_value={"YAMCPS_API_ENDPOINT": "new"}) as edit:
            self.assertTrue(edit_configs(self.store, Plugin()))
        self.assertEqual(
            edit.call_args.kwargs["allowed"], {"YAMCPS_API_ENDPOINT", "YAMCPS_API_MODE"}
        )
        self.assertEqual(edit.call_args.args[0]["YAMCPS_API_MODE"], "")
        self.assertEqual(
            self.store.values(),
            {
                "YAMCPS_API_ENDPOINT": "new",
                "YAMCPS_API_BAR_TOKEN": "other",
                "YAMCPS_API_LEGACY": "kept",
            },
        )
        original = self.store.path.read_bytes()
        with patch("yamcps.editor.edit_json", return_value={"YAMCPS_API_BAR_TOKEN": "changed"}):
            with self.assertRaises(EditorError):
                edit_configs(self.store, Plugin())
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_global_edit_can_add_remove_and_cancellation_never_creates_files(self):
        for function, store in ((edit_configs, self.store), (edit_secrets, self.vault)):
            with patch("yamcps.editor.edit_json", return_value=None):
                self.assertFalse(function(store))
        self.assertEqual(list(self.root.iterdir()), [])
        # Removing proposed, never-stored fields is also a no-op.
        for function, store in ((edit_configs, self.store), (edit_secrets, self.vault)):
            with patch("yamcps.editor.edit_json", return_value={}):
                self.assertFalse(function(store, Plugin()))
        self.assertEqual(list(self.root.iterdir()), [])
        self.store.set("api", "endpoint", "old")
        with patch("yamcps.editor.edit_json", return_value={"YAMCPS_NEW_MODE": "local"}):
            self.assertTrue(edit_configs(self.store))
        self.assertEqual(self.store.values(), {"YAMCPS_NEW_MODE": "local"})
        original = self.store.path.read_bytes()
        with patch("yamcps.editor.edit_json", return_value=self.store.values()):
            self.assertFalse(edit_configs(self.store))
        self.assertEqual(original, self.store.path.read_bytes())

    def test_configs_detect_concurrent_writer_and_do_not_clobber(self):
        self.store.set("api", "endpoint", "original")

        def change(*args, **kwargs):
            self.store.set("other", "name", "concurrent")
            return {"YAMCPS_API_ENDPOINT": "edited"}

        with (
            patch("yamcps.editor.edit_json", side_effect=change),
            self.assertRaisesRegex(ConfigError, "changed during editing"),
        ):
            edit_configs(self.store)
        self.assertEqual(
            self.store.values(),
            {"YAMCPS_API_ENDPOINT": "original", "YAMCPS_OTHER_NAME": "concurrent"},
        )
        self.assertFalse(self.store.path.with_suffix(".json.lock").exists())

    def test_secret_edits_stay_encrypted_scoped_and_support_deletion(self):
        initialize_vault(self.vault)
        self.vault.set("api", "token", "old-private")
        self.vault.set("api-bar", "token", "other-private")
        with patch(
            "yamcps.editor.edit_json", return_value={"YAMCPS_API_TOKEN": "new-private"}
        ) as edit:
            self.assertTrue(edit_secrets(self.vault, Plugin()))
        self.assertEqual(edit.call_args.args[0], {"YAMCPS_API_TOKEN": "old-private"})
        self.assertTrue(edit.call_args.kwargs["secret"])
        self.assertEqual(self.vault.values()["YAMCPS_API_BAR_TOKEN"], "other-private")
        self.assertNotIn(b"new-private", self.vault.path.read_bytes())
        with patch("yamcps.editor.edit_json", return_value={}):
            self.assertTrue(edit_secrets(self.vault, Plugin()))
        self.assertEqual(self.vault.values(), {"YAMCPS_API_BAR_TOKEN": "other-private"})
        self.assertEqual({p.name for p in self.root.iterdir()}, {"vault", "key"})

    def test_secret_first_save_validation_cancellation_and_corrupt_vault(self):
        with patch("yamcps.editor.edit_json", return_value={"YAMCPS_API_TOKEN": ""}):
            with self.assertRaises(EditorError):
                edit_secrets(self.vault, Plugin())
        self.assertEqual(list(self.root.iterdir()), [])
        with patch("yamcps.editor.edit_json", return_value={"YAMCPS_API_TOKEN": "private"}):
            self.assertTrue(edit_secrets(self.vault, Plugin()))
        self.assertEqual(self.vault.values(), {"YAMCPS_API_TOKEN": "private"})
        original = self.vault.path.read_bytes()
        with patch("yamcps.editor.edit_json", return_value=self.vault.values()):
            self.assertFalse(edit_secrets(self.vault))
        self.assertEqual(original, self.vault.path.read_bytes())
        self.vault.path.write_bytes(b"corrupt")
        with patch("yamcps.editor.edit_json") as edit, self.assertRaises(SecretError):
            edit_secrets(self.vault)
        edit.assert_not_called()
        self.assertEqual(self.vault.path.read_bytes(), b"corrupt")

    def test_vault_concurrency_lock_and_failed_write_preserve_content(self):
        initialize_vault(self.vault)
        self.vault.set("api", "token", "original")

        def change(*args, **kwargs):
            self.vault.set("other", "token", "concurrent")
            return {"YAMCPS_API_TOKEN": "edited"}

        with (
            patch("yamcps.editor.edit_json", side_effect=change),
            self.assertRaisesRegex(SecretError, "changed during editing"),
        ):
            edit_secrets(self.vault)
        self.assertEqual(self.vault.values()["YAMCPS_API_TOKEN"], "original")
        before = self.vault.path.read_bytes()
        with (
            patch("yamcps.editor.edit_json", return_value={"YAMCPS_API_TOKEN": "edited"}),
            patch("yamcps.vault.os.replace", side_effect=OSError),
            self.assertRaises(SecretError),
        ):
            edit_secrets(self.vault)
        self.assertEqual(before, self.vault.path.read_bytes())
        self.assertFalse(list(self.root.glob("*.lock")))
        self.assertFalse(list(self.root.glob(".yamcps-*")))

    def test_masking_incomplete_json_and_render_fragments(self):
        for line in (
            '  "YAMCPS_API_TOKEN": "private-marker",',
            "private-marker",
            '{"YAMCPS_API_TOKEN": "private-marker"}',
            '  "YAMCPS_API_TOKEN": "private-marker',
            '  "YAMCPS_API_TOKEN": "private-\\"marker"',
        ):
            fragments = [("class:a", line[:10]), ("class:b", line[10:])]
            result = SecretMask().apply_transformation(SimpleNamespace(fragments=fragments))
            rendered = "".join(fragment[1] for fragment in result.fragments)
            self.assertNotIn("private", rendered)
            self.assertEqual(len(rendered), len(line))
        result = SecretMask().apply_transformation(SimpleNamespace(fragments=[("", "}")]))
        self.assertEqual(result.fragments[0][1], "}")

    def test_terminal_guards_interrupts_and_io_errors(self):
        for stdin, stderr in ((False, True), (True, False)):
            with (
                patch("sys.stdin.isatty", return_value=stdin),
                patch("sys.stderr.isatty", return_value=stderr),
                self.assertRaises(EditorError),
            ):
                edit_json({})
        for error in (KeyboardInterrupt, EOFError, OSError):
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("sys.stderr.isatty", return_value=True),
                patch("yamcps.editor.editor_application") as build,
            ):
                build.return_value.run.side_effect = error
                if error is OSError:
                    with self.assertRaises(EditorError):
                        edit_json({})
                else:
                    self.assertIsNone(edit_json({}))


class EditorKeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def run_editor(self, keys, initial=None, text=None, secret=False):
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            with patch("yamcps.editor.create_output", return_value=DummyOutput()):
                app = editor_application(initial or {}, secret=secret)
            if text is not None:
                app.current_buffer.text = text
            return await asyncio.wait_for(app.run_async(pre_run=lambda: pipe.send_text(keys)), 3)

    async def test_save_returns_validated_text(self):
        result = await self.run_editor("\x13", text='{"YAMCPS_API_NAME":"edited"}')
        self.assertEqual(result, {"YAMCPS_API_NAME": "edited"})

    async def test_invalid_json_save_remains_in_editor_then_cancels(self):
        self.assertIsNone(await self.run_editor("\x13\x11", text="invalid-private-marker"))
        for key in ("\x11", "\x03"):
            self.assertIsNone(
                await self.run_editor(key, {"YAMCPS_API_TOKEN": "private"}, secret=True)
            )

    async def test_masked_editor_saves_original_values_not_display_stars(self):
        values = {"YAMCPS_API_TOKEN": "private-marker"}
        self.assertEqual(await self.run_editor("\x13", values, secret=True), values)

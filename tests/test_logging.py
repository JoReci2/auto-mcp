"""CLI verbosity and shared connector logging regressions."""

import contextlib
import io
import logging
import sys
import unittest
from unittest.mock import Mock, patch

from mcp import Client, StdioServerParameters

from yamcps.cli import main
from yamcps.connectors import ConnectorError
from yamcps.server import create_server


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.handlers = self.root.handlers[:]
        self.level = self.root.level
        self.engine_level = logging.getLogger("yamcps").level
        # Keep the test runner's handlers open when the CLI replaces them.
        self.root.handlers = []

    def tearDown(self):
        for handler in self.root.handlers:
            handler.close()
        self.root.handlers = self.handlers
        self.root.setLevel(self.level)
        logging.getLogger("yamcps").setLevel(self.engine_level)

    def run_cli(self, verbose, transport="stdio"):
        stderr, stdout = io.StringIO(), io.StringIO()

        server = Mock()

        def compose(*args, **kwargs):
            logging.getLogger("yamcps.server").debug("engine detail")
            logger = logging.getLogger("yamcps.connectors.external")
            logger.debug("connector detail")
            logger.info("connector event")
            logging.getLogger("httpx").debug("third party payload")
            return server

        argv = ["yamcps", "serve", "--transport", transport]
        if verbose:
            argv.append("--verbose")
        with (
            patch("sys.argv", argv),
            patch("yamcps.cli.create_server", side_effect=compose),
            patch("yamcps.cli._select_vault"),
            contextlib.redirect_stderr(stderr),
            contextlib.redirect_stdout(stdout),
        ):
            main()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("INFO yamcps.connectors.external: connector event", stderr.getvalue())
        self.assertNotIn("third party payload", stderr.getvalue())
        expected = {"transport": "stdio"}
        if transport == "http":
            expected = {"transport": "streamable-http", "host": "127.0.0.1", "port": 8000}
        server.run.assert_called_once_with(**expected)
        return stderr.getvalue()

    def test_verbose_both_transports_and_reset(self):
        for transport in ("stdio", "http"):
            verbose = self.run_cli(True, transport)
            self.assertIn("DEBUG yamcps.server: engine detail", verbose)
            self.assertIn("DEBUG yamcps.connectors.external: connector detail", verbose)
            normal = self.run_cli(False, transport)
            self.assertNotIn("engine detail", normal)
            self.assertNotIn("connector detail", normal)

    def test_startup_logs_do_not_include_config_or_secret_values(self):
        with self.assertLogs("yamcps", level="DEBUG") as captured:
            create_server(
                ["demo"],
                config_values={"demo.endpoint": "private-config-marker"},
                secret_values={"demo.token": "private-secret-marker"},
            )
        output = "\n".join(captured.output)
        for stage in (
            "Loading connector demo",
            "Configuring connector demo",
            "Registering handlers",
        ):
            self.assertIn(stage, output)
        self.assertNotIn("private-config-marker", output)
        self.assertNotIn("private-secret-marker", output)

    def test_failed_hook_identifies_stage_without_logging_exception_payload(self):
        plugin = Mock(id="broken", spec=["id", "register", "configure"])
        plugin.configure.side_effect = RuntimeError("private-exception-marker")
        with (
            patch("yamcps.server.load", return_value=[plugin]),
            self.assertLogs("yamcps", level="DEBUG") as captured,
            self.assertRaisesRegex(ConnectorError, "configuration failed"),
        ):
            create_server(config_values={}, secret_values={})
        output = "\n".join(captured.output)
        self.assertIn("Configuring connector broken", output)
        self.assertNotIn("private-exception-marker", output)


class ConnectorLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_log_reaches_engine_during_tool_call(self):
        server = create_server(["demo"], config_values={})
        with self.assertLogs("yamcps", level="DEBUG") as captured:
            async with Client(server) as client:
                result = await client.call_tool("demo_echo", {"message": "private-tool-marker"})
        self.assertEqual(result.structured_content, {"result": "private-tool-marker"})
        output = "\n".join(captured.output)
        self.assertIn("yamcps.connectors.demo:Handling demo_echo", output)
        self.assertNotIn("private-tool-marker", output)

    async def test_verbose_stdio_preserves_protocol(self):
        target = StdioServerParameters(
            command=sys.executable,
            args=["-m", "yamcps", "serve", "--connector", "demo", "--verbose"],
        )
        async with Client(target) as client:
            result = await client.call_tool("demo_echo", {"message": "stdio payload"})
        self.assertEqual(result.structured_content, {"result": "stdio payload"})

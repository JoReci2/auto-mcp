"""hmcp command line; stdout is reserved for stdio MCP traffic."""

import argparse
import logging
import sys
from pathlib import Path

from hmcp.connectors import ConnectorError, discover, load
from hmcp.onboarding import configure_secrets, default_vault, initialize_vault, requirements
from hmcp.secrets import SecretError, SecretSpec
from hmcp.server import create_server
from hmcp.vault import Vault


def _vault_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--key-file", type=Path)


def _select_vault(args: argparse.Namespace) -> Vault:
    if bool(args.vault) != bool(args.key_file):
        raise SecretError("--vault and --key-file must be supplied together")
    return Vault(args.vault, args.key_file) if args.vault else default_vault()


def _manage_secrets(args: argparse.Namespace) -> None:
    vault = _select_vault(args)
    if args.action == "init":
        initialize_vault(vault)
    elif args.action == "list":
        for name in vault.names():
            print(name)
    elif args.action == "delete":
        vault.delete(args.connector, args.name)
    else:
        specs = [SecretSpec(args.name)] if args.name else requirements(load([args.connector])[0])
        configure_secrets(args.connector, specs, vault)


def main() -> None:
    """Parse CLI commands and start the server or manage an encrypted vault."""
    parser = argparse.ArgumentParser(prog="hmcp")
    commands = parser.add_subparsers(dest="command", required=True)
    connectors = commands.add_parser("connectors").add_subparsers(dest="action", required=True)
    connectors.add_parser("list")
    secrets = commands.add_parser("secrets").add_subparsers(dest="action", required=True)
    for action in ("init", "set", "delete", "list"):
        subcommand = secrets.add_parser(action)
        _vault_options(subcommand)
        if action in ("set", "delete"):
            subcommand.add_argument("--connector", required=True)
            subcommand.add_argument("--name", required=action == "delete")
    serve = commands.add_parser("serve")
    serve.add_argument(
        "--connector",
        action="append",
        help="Load only this connector (repeatable); defaults to all installed plugins",
    )
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument("--port", type=int, default=8000)
    _vault_options(serve)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        if args.command == "connectors":
            for name, entry in sorted(discover().items()):
                print(f"{name}\t{entry.value}")
            return
        if args.command == "secrets":
            _manage_secrets(args)
            return
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        server = create_server(
            args.connector, vault=_select_vault(args), interactive=sys.stdin.isatty()
        )
        if args.transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    except (ConnectorError, SecretError) as exc:
        parser.exit(2, f"hmcp: {exc}\n")

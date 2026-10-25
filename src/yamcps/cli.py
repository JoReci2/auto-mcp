"""yamcps command line; stdout is reserved for stdio MCP traffic."""

import argparse
import logging
import sys
from pathlib import Path

from yamcps.configs import (
    ConfigError,
    ConfigStore,
    ConnectorConfigs,
    configure_configs,
    prepare_configs,
)
from yamcps.connectors import ConnectorError, discover, load
from yamcps.onboarding import (
    configure_secrets,
    default_vault,
    initialize_vault,
    requirements_for_configs,
)
from yamcps.rag.download import ModelDownloadError, download_model
from yamcps.secrets import SecretError, SecretSpec
from yamcps.server import create_server
from yamcps.vault import Vault


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
        if args.name and args.connector not in discover():
            specs = [SecretSpec(args.name)]
        else:
            connector = load([args.connector])[0]
            conditional = getattr(connector, "required_secrets_for_configs", None) is not None
            if args.name and not conditional:
                specs = [SecretSpec(args.name)]
            else:
                configs = (
                    prepare_configs(
                        [connector], ConfigStore(args.config_file), interactive=sys.stdin.isatty()
                    )
                    if conditional
                    else {}
                )
                specs = requirements_for_configs(connector, ConnectorConfigs(connector.id, configs))
                if args.name:
                    specs = [spec for spec in specs if spec.name == args.name]
                    if not specs:
                        raise SecretError(
                            f"Secret {args.name!r} is inactive or undeclared for the "
                            "resolved configuration"
                        )
        configure_secrets(args.connector, specs, vault)


def _manage_configs(args: argparse.Namespace) -> None:
    store = ConfigStore(args.config_file)
    if args.action == "list":
        for name, value in sorted(store.values().items()):
            print(f"{name}={value}")
    elif args.action == "delete":
        store.delete(args.connector, args.name)
    elif args.value is not None:
        if args.name is None:
            raise ConfigError("--value requires --name")
        store.set(args.connector, args.name, args.value)
    else:
        configure_configs(load([args.connector])[0], store, name=args.name)


def main() -> None:
    """Parse CLI commands and start the server or manage an encrypted vault."""
    parser = argparse.ArgumentParser(prog="yamcps")
    commands = parser.add_subparsers(dest="command", required=True)
    connectors = commands.add_parser("connectors").add_subparsers(dest="action", required=True)
    connectors.add_parser("list")
    secrets = commands.add_parser("secrets").add_subparsers(dest="action", required=True)
    for action in ("init", "set", "delete", "list"):
        subcommand = secrets.add_parser(action)
        _vault_options(subcommand)
        if action == "set":
            subcommand.add_argument("--config-file", type=Path)
        if action in ("set", "delete"):
            subcommand.add_argument("--connector", required=True)
            subcommand.add_argument("--name", required=action == "delete")
    configs = commands.add_parser("configs").add_subparsers(dest="action", required=True)
    for action in ("set", "delete", "list"):
        subcommand = configs.add_parser(action)
        subcommand.add_argument("--config-file", type=Path)
        if action in ("set", "delete"):
            subcommand.add_argument("--connector", required=True)
            subcommand.add_argument("--name", required=action == "delete")
        if action == "set":
            subcommand.add_argument("--value")
    models = commands.add_parser("models").add_subparsers(dest="action", required=True)
    download = models.add_parser("download", help="Download a model for local semantic search")
    download.add_argument("repo_id")
    download.add_argument("--revision", default="main")
    download.add_argument("--destination", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument(
        "--connector",
        action="append",
        help="Load only this connector (repeatable); defaults to all installed plugins",
    )
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument("--port", type=int, default=8000)
    _vault_options(serve)
    serve.add_argument("--config-file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        if args.command == "configs":
            _manage_configs(args)
            return
        if args.command == "models":
            print(
                download_model(args.repo_id, revision=args.revision, destination=args.destination)
            )
            return
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
            args.connector,
            vault=_select_vault(args),
            interactive=sys.stdin.isatty(),
            config_store=ConfigStore(args.config_file),
        )
        if args.transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    except (ConnectorError, SecretError, ConfigError, ModelDownloadError) as exc:
        parser.exit(2, f"yamcps: {exc}\n")

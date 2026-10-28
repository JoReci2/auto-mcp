"""yamcps command line; stdout is reserved for stdio MCP traffic."""

import argparse
import logging
import sys
from pathlib import Path

from yamcps.configs import (
    ConfigError,
    ConfigStore,
    ConnectorConfigs,
    _key,
    config_requirements,
    configure_configs,
    prepare_configs,
)
from yamcps.connectors import ConnectorError, discover, load
from yamcps.editor import EditorError, edit_configs, edit_secrets
from yamcps.onboarding import (
    configure_secrets,
    default_vault,
    initialize_vault,
    requirements_for_configs,
)
from yamcps.rag.download import ModelDownloadError, download_model
from yamcps.secrets import SecretError, SecretSpec
from yamcps.server import create_server
from yamcps.terminal import console, listing
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
    if args.action == "edit":
        connector = load([args.connector])[0] if args.connector else None
        changed = edit_secrets(vault, connector)
        console(sys.stderr).print("Saved." if changed else "No changes saved.", style="green")
    elif args.action == "init":
        initialize_vault(vault)
    elif args.action == "list":
        listing(["Secret (values hidden)"], [[name] for name in vault.names()], plain_headers=False)
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


def _list_configs(args: argparse.Namespace, store: ConfigStore) -> None:
    values = store.values()
    names = [args.connector] if args.connector else sorted(discover())
    rows = []
    declared = set()
    for connector in load(names):
        for spec in config_requirements(connector):
            key = _key(connector.id, spec.name)
            declared.add(key)
            rows.append(
                [
                    key,
                    spec.description,
                    repr(spec.default) if spec.default is not None else "required",
                    repr(values[key]) if key in values else "not configured",
                ]
            )
    if not args.connector:
        rows.extend(
            [key, "undeclared / plugin not installed", "—", repr(value)]
            for key, value in sorted(values.items())
            if key not in declared
        )
    listing(["Name", "Description", "Default", "Stored value"], rows)


def _manage_configs(args: argparse.Namespace) -> None:
    store = ConfigStore(args.config_file)
    if args.action == "edit":
        connector = load([args.connector])[0] if args.connector else None
        changed = edit_configs(store, connector)
        console(sys.stderr).print("Saved." if changed else "No changes saved.", style="green")
    elif args.action == "list":
        _list_configs(args, store)
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
    for action in ("init", "set", "delete", "list", "edit"):
        subcommand = secrets.add_parser(action)
        _vault_options(subcommand)
        if action == "set":
            subcommand.add_argument("--config-file", type=Path)
        if action == "edit":
            subcommand.add_argument("--connector")
        if action in ("set", "delete"):
            subcommand.add_argument("--connector", required=True)
            subcommand.add_argument("--name", required=action == "delete")
    configs = commands.add_parser("configs").add_subparsers(dest="action", required=True)
    for action in ("set", "delete", "list", "edit"):
        subcommand = configs.add_parser(action)
        subcommand.add_argument("--config-file", type=Path)
        if action in ("list", "edit"):
            subcommand.add_argument("--connector")
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
    serve.add_argument(
        "--verbose", action="store_true", help="Enable detailed engine and connector logs"
    )
    _vault_options(serve)
    serve.add_argument("--config-file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("yamcps").setLevel(
        logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    )
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
            listing(
                ["Connector", "Entry point"],
                [[name, entry.value] for name, entry in sorted(discover().items())],
                plain_headers=False,
            )
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
        logging.getLogger(__name__).info("Starting %s transport", args.transport)
        if args.transport == "stdio":
            server.run(transport="stdio")
        else:
            server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    except (ConnectorError, SecretError, ConfigError, ModelDownloadError, EditorError) as exc:
        parser.exit(2, f"yamcps: {exc}\n")

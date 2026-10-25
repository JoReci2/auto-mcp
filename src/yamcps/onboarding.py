"""Discover required credentials and collect missing values before MCP starts."""

import getpass
import inspect
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path

from yamcps.configs import ConnectorConfigs
from yamcps.connectors import Connector, ConnectorError
from yamcps.secrets import ConnectorSecrets, SecretError, SecretSpec, _identifier
from yamcps.vault import Vault


def default_vault() -> Vault:
    """Locate the default local vault and separate master key.

    Returns:
        A vault below ~/.local/share/yamcps with a key below ~/.config/yamcps/keys.
    """
    home = Path.home()
    return Vault(
        home / ".local/share/yamcps/secrets.yamcps-vault",
        home / ".config/yamcps/keys/master.yamcps-key",
    )


def requirements(connector: Connector) -> list[SecretSpec]:
    """Read a connector's optional credential declaration.

    Args:
        connector: Loaded connector whose declaration is inspected once.

    Returns:
        Ordered, unique required secret descriptions.

    Raises:
        ConnectorError: The declaration is invalid or cannot be read.
    """
    try:
        declare = getattr(connector, "required_secrets", None)
        if declare is None:
            return []
        if not callable(declare) or inspect.iscoroutinefunction(declare):
            raise TypeError
        specs = list(declare())
        seen: set[str] = set()
        for spec in specs:
            if not isinstance(spec, SecretSpec) or spec.name in seen:
                raise TypeError
            seen.add(spec.name)
        return specs
    except Exception:
        raise ConnectorError(
            f"Connector {connector.id!r}: invalid required_secrets declaration"
        ) from None


def requirements_for_configs(connector: Connector, configs: ConnectorConfigs) -> list[SecretSpec]:
    """Select active credentials from the complete catalogue.

    Args:
        connector: Normally loaded selected connector.
        configs: Resolved settings before injection.

    Returns:
        Unique active catalogue entries in requested order.

    Raises:
        ConnectorError: The synchronous hook or its subset is invalid.
    """
    catalogue = requirements(connector)
    try:
        declare = getattr(connector, "required_secrets_for_configs", None)
        if declare is None:
            return catalogue
        if not callable(declare) or inspect.iscoroutinefunction(declare):
            raise TypeError
        result = declare(configs)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError
        specs = list(result)
        by_name = {spec.name: spec for spec in catalogue}
        seen: set[str] = set()
        for spec in specs:
            if not isinstance(spec, SecretSpec) or spec.name in seen or spec.name not in by_name:
                raise TypeError
            seen.add(spec.name)
        return [by_name[spec.name] for spec in specs]
    except Exception:
        raise ConnectorError(
            f"Connector {connector.id!r}: invalid required_secrets_for_configs declaration; "
            "expected unique secrets from required_secrets() for the resolved configuration"
        ) from None


def initialize_vault(vault: Vault) -> None:
    """Create private parent directories and initialize a new vault.

    Args:
        vault: Vault whose existing files must never be overwritten.
    """
    try:
        vault.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        vault.key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise SecretError("Cannot create vault or key directory") from None
    vault.initialize()


def _read_values(vault: Vault) -> dict[str, str]:
    if vault.path.exists() or vault.key_file.exists():
        return vault.values()
    return {}


def _require_terminal() -> None:
    if not sys.stdin.isatty():
        raise SecretError(
            "Interactive secret configuration requires a terminal; "
            "run 'yamcps secrets set --connector <name>' in a terminal first"
        )


def _prompt(connector: str, spec: SecretSpec, *, existing: bool = False) -> str:
    label = f"{connector}/{spec.name}"
    if spec.description:
        print(f"{label}: {spec.description}", file=sys.stderr)
    suffix = " (empty: keep existing)" if existing else ""
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        while True:
            try:
                value = getpass.getpass(f"{label}{suffix}: ", stream=sys.stderr)
            except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
                raise SecretError(
                    "Secret configuration cancelled or hidden input unavailable"
                ) from None
            if value or existing:
                return value
            print("A nonempty value is required.", file=sys.stderr)


def _persist(vault: Vault, updates: dict[str, str]) -> dict[str, str]:
    if updates:
        if not vault.path.exists() and not vault.key_file.exists():
            initialize_vault(vault)
        vault.update(updates)
    return _read_values(vault)


def prepare_secrets(
    connectors: Sequence[Connector],
    vault: Vault,
    *,
    interactive: bool,
    declared: Sequence[tuple[str, Sequence[SecretSpec]]] | None = None,
) -> dict[str, str]:
    """Collect only missing declared credentials before connector configuration.

    Args:
        connectors: Selected connector instances; no other plugins are loaded.
        vault: Credential store, initialized only when values need to be saved.
        interactive: Whether terminal prompting is allowed.
        declared: Resolved requirements, or None for the legacy catalogue.

    Returns:
        Decrypted credentials to inject into connector configuration.

    Raises:
        SecretError: Credentials are missing without a terminal, or vault access fails.
    """
    if declared is None:
        declared = [(connector.id, requirements(connector)) for connector in connectors]
    values = _read_values(vault)
    missing = [
        (identifier, spec)
        for identifier, specs in declared
        for spec in specs
        if ConnectorSecrets(identifier, values).get(spec.name) is None
    ]
    if not missing:
        return values
    if not interactive or not sys.stdin.isatty():
        commands = "; ".join(
            f"yamcps secrets set --connector {identifier}"
            for identifier in dict.fromkeys(item[0] for item in missing)
        )
        raise SecretError(f"Missing required secrets; configure them in a terminal: {commands}")
    _require_terminal()
    updates = {
        _variable(identifier, spec.name): _prompt(identifier, spec) for identifier, spec in missing
    }
    return _persist(vault, updates)


def _variable(connector: str, name: str) -> str:
    return f"YAMCPS_{_identifier(connector)}_{_identifier(name)}"


def configure_secrets(connector: str, specs: Sequence[SecretSpec], vault: Vault) -> None:
    """Run the explicit configuration wizard for one connector.

    Args:
        connector: Connector identifier.
        specs: Required fields, or one explicitly selected secret.
        vault: Credential store to update after all prompts succeed.

    Raises:
        SecretError: No fields are declared or hidden terminal input is unavailable.
    """
    if not specs:
        raise SecretError(
            f"Connector {connector!r} declares no required secrets; "
            "use --name to configure a specific secret"
        )
    _require_terminal()
    values = _read_values(vault)
    updates = {}
    for spec in specs:
        value = _prompt(
            connector, spec, existing=ConnectorSecrets(connector, values).get(spec.name) is not None
        )
        if value:
            updates[_variable(connector, spec.name)] = value
    _persist(vault, updates)

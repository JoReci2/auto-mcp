"""Plaintext, connector-scoped configuration, separate from the encrypted vault."""

import inspect
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yamcps.terminal import console, field_header


class ConfigError(ValueError):
    """Configuration is missing, invalid or cannot be persisted."""


def _key(connector: str, name: str) -> str:
    for part in (connector, name):
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", part):
            raise ConfigError("Expected lowercase kebab-case configuration identifiers")
    return f"YAMCPS_{connector.upper().replace('-', '_')}_{name.upper().replace('-', '_')}"


@dataclass(frozen=True)
class ConfigSpec:
    """Declare a nonsecret string; None means required, a string supplies a default."""

    name: str
    description: str = ""
    default: str | None = None

    def __post_init__(self) -> None:
        """Validate declarations without accessing the filesystem."""
        _key("config", self.name)
        if self.default is not None and not isinstance(self.default, str):
            raise ConfigError("Configuration defaults must be strings or None")


class ConnectorConfigs:
    """View over one connector's resolved nonsecret values."""

    def __init__(self, connector_id: str, values: Mapping[str, str]) -> None:
        """Keep a scoped view over explicit resolved configuration.

        Args:
            connector_id: Connector identifier.
            values: Resolved values keyed by normalized YAMCPS names.
        """
        self._id = connector_id
        self._values = values

    def get(self, name: str) -> str | None:
        """Return a value, including an explicitly stored empty string.

        Args:
            name: Configuration field name in kebab-case.

        Returns:
            Plaintext value or None if absent.
        """
        return self._values.get(_key(self._id, name))

    def require(self, name: str) -> str:
        """Return a nonempty required value.

        Args:
            name: Required field name.

        Returns:
            The nonempty configured value.

        Raises:
            ConfigError: The value is absent or empty.
        """
        value = self.get(name)
        if not value:
            raise ConfigError(f"Missing configuration: {self._id}/{name}")
        return value


class ConfigStore:
    """JSON string mapping with atomic replacement and an exclusive writer lock."""

    def __init__(self, path: Path | None = None) -> None:
        """Select a config file without reading or creating it.

        Args:
            path: Explicit path, or ~/.config/yamcps/config.json.
        """
        self.path = (
            (path if path is not None else Path.home() / ".config/yamcps/config.json")
            .expanduser()
            .absolute()
        )

    def values(self) -> dict[str, str]:
        """Read nonsecret values, returning an empty mapping for a missing file.

        Returns:
            Validated configuration mapping.

        Raises:
            ConfigError: The file cannot be read or its schema is invalid.
        """
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise ConfigError("Cannot read configuration JSON") from None
        if not isinstance(values, dict) or any(
            not isinstance(k, str)
            or not re.fullmatch(r"YAMCPS_[A-Z0-9]+(?:_[A-Z0-9]+)*", k)
            or not isinstance(v, str)
            for k, v in values.items()
        ):
            raise ConfigError("Configuration must map YAMCPS names to plaintext strings")
        return values

    def update(
        self,
        updates: Mapping[str, str],
        *,
        delete: str | None = None,
        remove: Sequence[str] = (),
        expected: Mapping[str, str] | None = None,
    ) -> None:
        """Atomically merge values or remove a field, retaining other connectors.

        Args:
            updates: Normalized configuration names and plaintext string values.
            delete: Optional normalized field to remove.
            remove: Fields removed by an editor in the same atomic operation.
            expected: Original snapshot; reject concurrent modifications when supplied.

        Raises:
            ConfigError: Data is invalid, a field is absent or the store is locked.
        """
        if any(
            not isinstance(v, str) or not re.fullmatch(r"YAMCPS_[A-Z0-9]+(?:_[A-Z0-9]+)*", k)
            for k, v in updates.items()
        ):
            raise ConfigError("Invalid configuration updates")
        temporary = None
        lock = self.path.with_name(self.path.name + ".lock")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            raise ConfigError("Configuration is locked or not writable") from None
        os.close(descriptor)
        try:
            values = self.values()
            if expected is not None and values != expected:
                raise ConfigError("Configuration changed during editing; reopen the editor")
            for key in remove:
                values.pop(key, None)
            if delete is not None:
                if delete not in values:
                    raise ConfigError("Configuration field does not exist")
                del values[delete]
            values.update(updates)
            descriptor, temporary = tempfile.mkstemp(prefix=".yamcps-config-", dir=self.path.parent)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(values, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ConfigError("Cannot write configuration JSON") from None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            lock.unlink(missing_ok=True)

    def set(self, connector: str, name: str, value: str) -> None:
        """Persist one plaintext field.

        Args:
            connector: Connector identifier.
            name: Field identifier.
            value: Nonsecret text, including empty text for an optional setting.
        """
        self.update({_key(connector, name): value})

    def delete(self, connector: str, name: str) -> None:
        """Remove one stored field.

        Args:
            connector: Connector identifier.
            name: Field identifier.
        """
        self.update({}, delete=_key(connector, name))


def config_requirements(connector: Any) -> list[ConfigSpec]:
    """Read and validate a connector's optional config declarations.

    Args:
        connector: Selected connector instance.

    Returns:
        Ordered unique field declarations.

    Raises:
        ConfigError: The declaration is invalid.
    """
    declare = getattr(connector, "required_configs", None)
    if declare is None:
        return []
    try:
        if not callable(declare) or inspect.iscoroutinefunction(declare):
            raise TypeError
        specs = list(declare())
        if any(not isinstance(s, ConfigSpec) for s in specs) or len({s.name for s in specs}) != len(
            specs
        ):
            raise TypeError
        return specs
    except Exception:
        raise ConfigError(
            f"Connector {connector.id!r}: invalid required_configs declaration"
        ) from None


def _prompt(connector: str, spec: ConfigSpec, existing: str | None) -> str:
    field_header(f"{connector}/{spec.name}", spec.description, default=spec.default)
    print("Plaintext configuration; do not enter credentials.", file=sys.stderr)
    if existing is not None:
        console(sys.stderr).print("Current/default: ", repr(existing))
    suffix = " (empty: keep current/default)" if existing is not None else ""
    while True:
        print(f"{connector}/{spec.name}{suffix}: ", end="", file=sys.stderr, flush=True)
        try:
            value = input()
        except (EOFError, KeyboardInterrupt):
            raise ConfigError("Configuration cancelled") from None
        if value or existing is not None:
            return value if value else existing or ""
        print("A nonempty value is required.", file=sys.stderr)


def prepare_configs(
    connectors: Sequence[Any],
    store: ConfigStore,
    *,
    interactive: bool = False,
    explicit: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve file, environment fallback and defaults; prompt only missing required fields.

    Args:
        connectors: Selected instances only.
        store: Plaintext JSON store.
        interactive: Allow prompting only when stdin is a terminal.
        explicit: Optional in-memory values replacing file/environment sources.

    Returns:
        Values resolved for the selected connectors.

    Raises:
        ConfigError: Invalid declarations or missing fields without a terminal.
    """
    declarations = [(c.id, config_requirements(c)) for c in connectors]
    if not any(specs for _, specs in declarations):
        return {}
    values = dict(explicit) if explicit is not None else store.values()
    updates = {}
    for identifier, specs in declarations:
        for spec in specs:
            key = _key(identifier, spec.name)
            value = values.get(key)
            if value is None and explicit is None:
                value = os.environ.get(key)
            if value is None:
                value = spec.default
            if value is None or (value == "" and spec.default is None):
                if not interactive or not sys.stdin.isatty():
                    raise ConfigError(
                        f"Missing configuration; run yamcps configs set --connector {identifier} in a terminal"
                    )
                value = _prompt(identifier, spec, None)
                updates[key] = value
            values[key] = value
    if updates and explicit is None:
        store.update(updates)
    return values


def configure_configs(connector: Any, store: ConfigStore, *, name: str | None = None) -> None:
    """Run the explicit terminal wizard for declared nonsecret fields.

    Args:
        connector: Connector whose declarations provide fields and defaults.
        store: Plaintext store to update after all prompts succeed.
        name: Optional single declared field to configure.

    Raises:
        ConfigError: No fields match or a terminal is unavailable.
    """
    specs = config_requirements(connector)
    if name is not None:
        specs = [s for s in specs if s.name == name]
    if not specs or not sys.stdin.isatty():
        raise ConfigError(
            "Configuring declared fields requires a terminal and a matching declaration"
        )
    values = store.values()
    updates = {}
    for spec in specs:
        key = _key(connector.id, spec.name)
        existing = values.get(key, os.environ.get(key, spec.default))
        updates[key] = _prompt(connector.id, spec, existing)
    store.update(updates)

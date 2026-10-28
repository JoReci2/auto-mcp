"""Authenticated local credential storage with a separately supplied random key."""

import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from yamcps.secrets import SecretError, _identifier

_HEADER = b"HMCPVAULT\x01"


def _write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class Vault:
    """AES-256-GCM vault; no keyring, password derivation or plaintext export."""

    def __init__(self, path: Path, key_file: Path) -> None:
        """Locate a vault and its separate master key.

        Args:
            path: Encrypted vault file.
            key_file: File containing exactly 32 random key bytes.

        Raises:
            SecretError: The vault and key point to the same file.
        """
        self.path = path.resolve()
        self.key_file = key_file.resolve()
        if self.path == self.key_file:
            raise SecretError("Vault and key must be separate files")

    def initialize(self) -> None:
        """Create a new key and empty vault without overwriting existing files.

        Raises:
            SecretError: Files already exist or cannot be created.
        """
        if self.path.exists() or self.key_file.exists():
            raise SecretError("Vault initialization requires two new file paths")
        key = AESGCM.generate_key(bit_length=256)
        created_key = False
        try:
            _write_new(self.key_file, key)
            created_key = True
            _write_new(self.path, self._encrypt({}, key))
        except OSError:
            if created_key:
                self.key_file.unlink(missing_ok=True)
            raise SecretError(
                "Cannot initialize vault; check directories and permissions"
            ) from None

    def _key(self) -> bytes:
        try:
            with self.key_file.open("rb") as stream:
                if os.name == "posix" and stat.S_IMODE(os.fstat(stream.fileno()).st_mode) & 0o077:
                    raise SecretError("Master key permissions must restrict access to its owner")
                key = stream.read(33)
        except OSError:
            raise SecretError("Cannot read master key") from None
        if len(key) != 32:
            raise SecretError("Master key must contain exactly 32 bytes")
        return key

    @staticmethod
    def _encrypt(values: dict[str, str], key: bytes) -> bytes:
        nonce = os.urandom(12)
        plaintext = json.dumps(values, ensure_ascii=False).encode("utf-8")
        return _HEADER + nonce + AESGCM(key).encrypt(nonce, plaintext, _HEADER)

    def values(self) -> dict[str, str]:
        """Decrypt credentials for server startup.

        Returns:
            Raw credentials for internal injection; never log this mapping.

        Raises:
            SecretError: The key, file, authentication tag or format is invalid.
        """
        key = self._key()
        try:
            data = self.path.read_bytes()
        except OSError:
            raise SecretError("Cannot read vault") from None
        if not data.startswith(_HEADER) or len(data) < len(_HEADER) + 12 + 16:
            raise SecretError("Invalid or unsupported vault format")
        offset = len(_HEADER)
        try:
            plaintext = AESGCM(key).decrypt(
                data[offset : offset + 12], data[offset + 12 :], _HEADER
            )
            values = json.loads(plaintext)
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise SecretError("Vault authentication failed or content is invalid") from None
        if not isinstance(values, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in values.items()
        ):
            raise SecretError("Invalid vault credential format")
        return values

    @contextmanager
    def _edit(self) -> Iterator[dict[str, str]]:
        lock = self.path.with_name(self.path.name + ".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            raise SecretError("Vault is locked or not writable") from None
        os.close(descriptor)
        temporary: str | None = None
        try:
            values = self.values()
            yield values
            data = self._encrypt(values, self._key())
            descriptor, temporary = tempfile.mkstemp(prefix=".yamcps-vault-", dir=self.path.parent)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise SecretError("Cannot update vault") from None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            lock.unlink(missing_ok=True)

    def set(self, connector: str, name: str, value: str) -> None:
        """Add or replace one credential.

        Args:
            connector: Connector identifier.
            name: Secret identifier.
            value: Nonempty raw secret obtained through hidden input.
        """
        variable = f"YAMCPS_{_identifier(connector)}_{_identifier(name)}"
        if not value:
            raise SecretError("Secret cannot be empty")
        with self._edit() as values:
            values[variable] = value

    def update(
        self,
        values: dict[str, str],
        *,
        remove: Sequence[str] = (),
        expected: Mapping[str, str] | None = None,
    ) -> None:
        """Atomically persist a batch collected by the interactive wizard.

        Args:
            values: Nonempty credentials keyed by normalized YAMCPS variable names.
            remove: Credential names to delete in the same encrypted transaction.
            expected: Original snapshot; reject concurrent changes when supplied.

        Raises:
            SecretError: A credential name or value is invalid.
        """
        if any(not name.startswith("YAMCPS_") or not value for name, value in values.items()):
            raise SecretError("Invalid credential batch")
        with self._edit() as stored:
            if expected is not None and stored != expected:
                raise SecretError("Vault changed during editing; reopen the editor")
            for name in remove:
                stored.pop(name, None)
            stored.update(values)

    def delete(self, connector: str, name: str) -> None:
        """Delete one credential, failing if it does not exist.

        Args:
            connector: Connector identifier.
            name: Secret identifier.
        """
        variable = f"YAMCPS_{_identifier(connector)}_{_identifier(name)}"
        with self._edit() as values:
            if variable not in values:
                raise SecretError("Secret does not exist")
            del values[variable]

    def names(self) -> list[str]:
        """Return sorted credential names without their values."""
        return sorted(self.values())

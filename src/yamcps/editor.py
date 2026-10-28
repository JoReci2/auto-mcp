"""In-memory JSON editor with atomic store updates and masked credential values."""

import json
import os
import re
import sys
from collections.abc import Mapping
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.output.defaults import create_output
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Label, TextArea
from pygments.lexers import JsonLexer

from yamcps.configs import ConfigStore, _key, config_requirements
from yamcps.connectors import Connector
from yamcps.onboarding import _read_values, _variable, initialize_vault, requirements
from yamcps.vault import Vault


class EditorError(ValueError):
    """An editor cannot start, validate its content or safely commit its changes."""


def _parse(text: str, allowed: set[str] | None, secret: bool) -> dict[str, str]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise EditorError("Duplicate JSON key; each field must occur once")
            result[key] = value
        return result

    try:
        values = json.loads(text, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise EditorError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from None
    if not isinstance(values, dict):
        raise EditorError("Expected a JSON object mapping YAMCPS names to strings")
    result: dict[str, str] = {}
    for key, value in values.items():
        if not re.fullmatch(r"YAMCPS_[A-Z0-9]+(?:_[A-Z0-9]+)*", key) or not isinstance(value, str):
            raise EditorError("Each field must have a normalized YAMCPS name and a string value")
        if allowed is not None and key not in allowed:
            raise EditorError("Only declared fields of the selected connector may be edited")
        if secret and not value:
            raise EditorError("Secrets cannot be empty; fill or remove missing fields")
        result[key] = value
    return result


class SecretMask(Processor):
    """Mask all editable value text, including incomplete JSON, without changing cursor offsets."""

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        """Replace value characters while retaining key names and syntax styles.

        Args:
            ti: Current rendered line and token fragments.

        Returns:
            Same-length fragments containing no credential value characters.
        """
        text = "".join(fragment[1] for fragment in ti.fragments)
        match = re.match(r'^\s*"YAMCPS_[A-Z0-9_]+"\s*:', text)
        visible = match.end() if match else 0
        structural = text.strip() in ("{", "}", "},", "")
        syntax = set(range(visible))
        if match:
            tail = text[visible:]
            opening = re.match(r'\s*"', tail)
            if opening:
                syntax.update(range(visible, visible + opening.end()))
                closing = re.search(r'"\s*,?\s*$', tail[opening.end() :])
                if closing:
                    syntax.update(range(visible + opening.end() + closing.start(), len(text)))
        fragments: StyleAndTextTuples = []
        offset = 0
        for style, part, *_ in ti.fragments:
            masked = "".join(
                character if structural or offset + index in syntax else "*"
                for index, character in enumerate(part)
            )
            fragments.append((style, masked))
            offset += len(part)
        return Transformation(fragments)


def editor_application(
    initial: Mapping[str, str], *, allowed: set[str] | None = None, secret: bool = False
) -> Application[dict[str, str] | None]:
    """Build the fullscreen editor without running it or creating plaintext files.

    Args:
        initial: Values loaded in memory; secrets are masked during rendering.
        allowed: Optional exact set of declared connector fields.
        secret: Mask credential values and reject empty secrets.

    Returns:
        Application returning validated values on Ctrl-S, None on Ctrl-Q/Ctrl-C.
    """
    status = Label(text="Ctrl-S: save | Ctrl-Q / Ctrl-C: cancel | Remove a key to delete it")
    title = "Secrets — values masked; encrypted on save" if secret else "Configuration — JSON"
    text = TextArea(
        text=json.dumps(dict(initial), indent=2, ensure_ascii=True) + "\n",
        lexer=PygmentsLexer(JsonLexer),
        scrollbar=True,
        line_numbers=True,
        wrap_lines=False,
        input_processors=[SecretMask()] if secret else [],
    )
    bindings = KeyBindings()

    @bindings.add("c-s")
    def save(event: KeyPressEvent) -> None:
        try:
            values = _parse(text.text, allowed, secret)
        except EditorError as exc:
            status.text = str(exc)
        else:
            event.app.exit(result=values)

    @bindings.add("c-q")
    @bindings.add("c-c")
    def cancel(event: KeyPressEvent) -> None:
        event.app.exit(result=None)

    return Application(
        layout=Layout(HSplit([Label(text=title), text, status]), focused_element=text),
        key_bindings=bindings,
        full_screen=True,
        erase_when_done=True,
        output=create_output(stdout=sys.stderr),
        color_depth=ColorDepth.DEPTH_1_BIT if "NO_COLOR" in os.environ else None,
        style=Style.from_dict({"pygments.name.tag": "cyan", "pygments.literal.string": "green"})
        if "NO_COLOR" not in os.environ
        else Style.from_dict({}),
        include_default_pygments_style="NO_COLOR" not in os.environ,
    )


def edit_json(
    initial: Mapping[str, str], *, allowed: set[str] | None = None, secret: bool = False
) -> dict[str, str] | None:
    """Run the JSON editor only with interactive input and output terminals.

    Args:
        initial: Snapshot to edit in memory.
        allowed: Optional connector field whitelist.
        secret: Mask all values and validate nonempty credentials.

    Returns:
        Validated values, or None when cancelled.

    Raises:
        EditorError: Terminal access is unavailable or editing is interrupted.
    """
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise EditorError("The editor requires stdin and stderr terminals; use configs/secrets set")
    try:
        return editor_application(initial, allowed=allowed, secret=secret).run()
    except (EOFError, KeyboardInterrupt):
        return None
    except OSError:
        raise EditorError("Cannot access the editor terminal") from None


def _selection(
    snapshot: dict[str, str], fields: dict[str, str] | None
) -> tuple[dict[str, str], set[str] | None]:
    if fields is None:
        return snapshot, None
    return {key: snapshot.get(key, default) for key, default in fields.items()}, set(fields)


def _changes(
    snapshot: dict[str, str],
    fields: dict[str, str] | None,
    secret: bool,
) -> tuple[dict[str, str], list[str]] | None:
    selected, allowed = _selection(snapshot, fields)
    edited = edit_json(selected, allowed=allowed, secret=secret)
    if edited is None:
        return None
    # Validate again at the persistence boundary, even for an alternative UI.
    edited = _parse(json.dumps(edited), allowed, secret)
    remove = [key for key in snapshot if key in selected and key not in edited]
    updates = {key: value for key, value in edited.items() if snapshot.get(key) != value}
    return (updates, remove) if updates or remove else None


def edit_configs(store: ConfigStore, connector: Connector | None = None) -> bool:
    """Edit stored settings globally or only declared fields of a selected plugin.

    Args:
        store: Plaintext configuration store.
        connector: Optional selected plugin; other fields remain untouched.

    Returns:
        True when changes were committed, False on cancellation or no change.
    """
    snapshot = store.values()
    fields = (
        {
            _key(connector.id, spec.name): spec.default or ""
            for spec in config_requirements(connector)
        }
        if connector is not None
        else None
    )
    changes = _changes(snapshot, fields, False)
    if changes is None:
        return False
    updates, remove = changes
    store.update(updates, remove=remove, expected=snapshot)
    return True


def edit_secrets(vault: Vault, connector: Connector | None = None) -> bool:
    """Edit masked credentials in memory and commit only encrypted changes.

    Args:
        vault: Existing or not-yet-initialized encrypted vault.
        connector: Optional plugin whose complete secret catalogue may be edited.

    Returns:
        True when changes were committed, False on cancellation or no change.
    """
    snapshot = _read_values(vault)
    fields = (
        {_variable(connector.id, spec.name): "" for spec in requirements(connector)}
        if connector is not None
        else None
    )
    changes = _changes(snapshot, fields, True)
    if changes is None:
        return False
    updates, remove = changes
    if not vault.path.exists() and not vault.key_file.exists():
        initialize_vault(vault)
    vault.update(updates, remove=remove, expected=snapshot)
    return True
